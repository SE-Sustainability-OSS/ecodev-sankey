"""
Module implementing all datatpoint retriever methods
"""
from typing import Callable
from typing import Iterator

from sqlalchemy import func
from sqlalchemy import tuple_
from sqlmodel import select
from sqlmodel import Session
from sqlmodel.main import SQLModelMetaclass

from ecodev_sankey.constants import ID
from ecodev_sankey.db_model.node_datapoint_link import NodeDataPointLink
from ecodev_sankey.db_model.tree_node import TreeNode


def _build_subtree_cte(hierarchy_filters: dict[str, list[int]]):
    """
    Build the recursive CTE that expands each hierarchy filter to all descendant node IDs.
    Returns (all_nodes_cte, n_concepts) where n_concepts is the number of distinct hierarchies
    that a DataPoint must match.
    """
    concept_base_pairs = [
        (bc, base_id)
        for bc, base_ids in hierarchy_filters.items()
        for base_id in base_ids
    ]
    anchor = (
        select(
            TreeNode.id.label('node_id'),  # type: ignore[union-attr]
            TreeNode.business_concept.label('business_concept'),  # type: ignore[attr-defined]
        )
        .where(tuple_(TreeNode.business_concept, TreeNode.id).in_(concept_base_pairs))
    )
    cte = anchor.cte('all_subtree_nodes', recursive=True)
    recursive = (
        select(TreeNode.id.label('node_id'), cte.c.business_concept)  # type: ignore[union-attr]
        .where(TreeNode.parent_id == cte.c.node_id)
        .where(TreeNode.business_concept == cte.c.business_concept)
    )
    return cte.union_all(recursive)


def get_sankey_datapoints(project_id: int,
                          filters: dict[str, list[int]],
                          field_adders: Callable,
                          session: Session,
                          DataPoint: SQLModelMetaclass,
                          extra_filters: list | None = None
                          ) -> Iterator[dict]:
    """
    Returns a DataFrame to be used for generating the Sankey diagram.
    """
    for datapoint in retrieve_datapoints_with_filters(project_id, filters, session, DataPoint,
                                                      extra_filters):
        yield {ID: datapoint.id} | field_adders(datapoint, session) | (datapoint.nodes_rep or {})


def retrieve_datapoints_from_hierarchy_node(project_id: int,
                                            base_node_id: int,
                                            session: Session,
                                            DataPoint: SQLModelMetaclass,
                                            extra_filters: list | None = None
                                            ) -> list[SQLModelMetaclass]:
    """
    Return all datapoints where one of their node is in the subtree starting with base_node_id
    """
    ancestor_nodes = (
        select(TreeNode.id)
        .where(TreeNode.id == base_node_id)
        .cte(name='ancestor_nodes', recursive=True)
    )
    ancestor_nodes = ancestor_nodes.union_all(
        select(TreeNode.id)
        .where(TreeNode.parent_id == ancestor_nodes.c.id)
    )

    stmt = (
        select(DataPoint)
        .join(NodeDataPointLink, DataPoint.id == NodeDataPointLink.datapoint_id)
        .join(TreeNode, NodeDataPointLink.node_id == TreeNode.id)
        .where(TreeNode.id.in_(select(ancestor_nodes.c.id)),  # type: ignore[union-attr]
               DataPoint.project_id == project_id,
               *(extra_filters or [])
               )
        .distinct()
    )
    return session.exec(stmt).all()


def retrieve_datapoint(datapoint_id: int,
                       session: Session,
                       DataPoint: SQLModelMetaclass
                       ) -> SQLModelMetaclass:
    """
    Retrieve a single datapoint by id
    """
    return session.exec(select(DataPoint).where(DataPoint.id == datapoint_id)).one()


def retrieve_datapoints(datapoint_ids: list[int],
                        session: Session,
                        DataPoint: SQLModelMetaclass
                        ) -> list[SQLModelMetaclass]:
    """
    Retrieve a list of datapoints  by id
    """
    return session.exec(select(DataPoint).where(DataPoint.id.in_(datapoint_ids))).all()  # type: ignore[union-attr] # noqa: E501


def retrieve_datapoints_with_filters(
    project_id: int,
    hierarchy_filters: dict[str, list[int]],
    session: Session,
    DataPoint: SQLModelMetaclass,
    extra_filters: list | None = None,
    load_options: list | None = None,
) -> list[SQLModelMetaclass]:
    """
    Given a hierarchy_filters giving a list of allowed node for multiple hierarchies,
    return the list of datapoint that satisfy all hierarchies where satisfying a hierarchy
    mean the datapoint node in this hierarchy belong to any subtrees starting from the provided
    node ids.
    With {'Geography' : [1,2],'Activity['3']}
    a datapoint is eligible if his hierarchy node is under 1 or 2  AND its activity node under 3

    NOTE: pass load_options (e.g. selectinload) to eager-load relationships
    """
    if not hierarchy_filters:
        stmt = select(DataPoint).where(DataPoint.project_id == project_id, *(extra_filters or []))
        if load_options:
            stmt = stmt.options(*load_options)
        return session.exec(stmt).all()

    all_nodes_cte = _build_subtree_cte(hierarchy_filters)
    stmt = (
        select(DataPoint)
        .join(NodeDataPointLink, DataPoint.id == NodeDataPointLink.datapoint_id)
        .join(TreeNode, NodeDataPointLink.node_id == TreeNode.id)
        .join(all_nodes_cte, TreeNode.id == all_nodes_cte.c.node_id)
        .where(DataPoint.project_id == project_id, *(extra_filters or []))
        .group_by(DataPoint.id)
        .having(func.count(func.distinct(all_nodes_cte.c.business_concept)) == len(hierarchy_filters))
    )
    if load_options:
        stmt = stmt.options(*load_options)
    return session.exec(stmt).all()


def retrieve_ghg_aggregate_with_filters(
    project_id: int,
    hierarchy_filters: dict[str, list[int]],
    session: Session,
    DataPoint: SQLModelMetaclass,
    group_by_col,
    value_expr,
    extra_filters: list | None = None,
) -> dict:
    """
    Return {group_by_col_value: SUM(value_expr)} for datapoints matching hierarchy_filters.

    Avoids fetching full DataPoint rows when only an aggregated scalar is needed per group
    (e.g. total GHG per year, or per scope). The hierarchy filter uses the same recursive CTE
    as retrieve_datapoints_with_filters.

    NOTE: value_expr and group_by_col must be SQLAlchemy column expressions on DataPoint,
    e.g. group_by_col=DataPoint.year, value_expr=DataPoint.activity_value * DataPoint.ef_value.
    """
    if not hierarchy_filters:
        stmt = (
            select(group_by_col, func.sum(value_expr))
            .where(DataPoint.project_id == project_id, *(extra_filters or []))
            .group_by(group_by_col)
        )
        return dict(session.exec(stmt).all())

    all_nodes_cte = _build_subtree_cte(hierarchy_filters)
    eligible_ids = (
        select(DataPoint.id.label('id'))  # type: ignore[union-attr]
        .join(NodeDataPointLink, DataPoint.id == NodeDataPointLink.datapoint_id)
        .join(TreeNode, NodeDataPointLink.node_id == TreeNode.id)
        .join(all_nodes_cte, TreeNode.id == all_nodes_cte.c.node_id)
        .where(DataPoint.project_id == project_id, *(extra_filters or []))
        .group_by(DataPoint.id)
        .having(func.count(func.distinct(all_nodes_cte.c.business_concept)) == len(hierarchy_filters))
        .subquery()
    )
    stmt = (
        select(group_by_col, func.sum(value_expr))
        .where(DataPoint.id.in_(select(eligible_ids.c.id)))  # type: ignore[union-attr]
        .group_by(group_by_col)
    )
    return dict(session.exec(stmt).all())

"""
Module implementing all datatpoint retriever methods
"""
from typing import Any
from typing import Callable
from typing import Iterator

from sqlalchemy import func
from sqlalchemy import tuple_
from sqlmodel import select
from sqlmodel import Session
from sqlmodel.main import SQLModelMetaclass

from ecodev_sankey.constants import ID
from ecodev_sankey.db_model.empty_datapoint_list_error import EmptyDatapointList
from ecodev_sankey.db_model.node_datapoint_link import NodeDataPointLink
from ecodev_sankey.db_model.retrievers.tree_node_retrievers import get_node_rep
from ecodev_sankey.db_model.tree_node import TreeNode


def get_sankey_datapoints(project_id: int,
                          filters: dict[str, list[int]],
                          field_adders: Callable,
                          session: Session,
                          DataPoint: SQLModelMetaclass
                          ) -> Iterator[dict]:
    """
    Returns a DataFrame to be used for generating the Sankey diagram.
    The data fetch is in two steps:
    - 1) retrieve the required data from (data_point, geography, entity, category) dbs
    - 2) convert each data to a DataFrame records.
    """
    for datapoint in retrieve_datapoints_with_filters(project_id, filters, session, DataPoint):
        nodes_rep: dict[str, Any] = {}
        for node in datapoint.nodes:
            nodes_rep |= get_node_rep(node.id, project_id, session)
        yield {ID: datapoint.id} | field_adders(datapoint, session) | nodes_rep


def retrieve_datapoints_from_hierarchy_node(project_id: int,
                                            base_node_id: int,
                                            session: Session,
                                            DataPoint: SQLModelMetaclass
                                            ) -> list[SQLModelMetaclass]:
    """
    Return all datapoints where one of their node is in the subtree starting with base_node_id
    """
    ancestor_nodes = (
        select(TreeNode.id)
        .where(
            (TreeNode.id == base_node_id))
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
               DataPoint.project_id == project_id
               )
        .distinct()
    )
    return session.exec(stmt).all()


def retrieve_datapoints_from_multi_tree(project_id: int,
                                        base_node_ids: list[int],
                                        session: Session,
                                        DataPoint: SQLModelMetaclass
                                        ) -> list[int]:
    """
    Given a list of tree node, return the list of datapoint that belong to all trees
    """
    eligible_per_node = [set([point.id
                              for point in retrieve_datapoints_from_hierarchy_node(project_id,
                                                                                   base_node_id,
                                                                                   session,
                                                                                   DataPoint)])
                         for base_node_id in base_node_ids]
    if not eligible_per_node:
        raise EmptyDatapointList('no datapoints for provided list')
    return list(set.intersection(*eligible_per_node))  # type: ignore[arg-type]


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
    DataPoint: SQLModelMetaclass
) -> list[SQLModelMetaclass]:
    """
    Given a hierarchy_filters giving a list of allowed node for multiple hierarchies,
    return the list of datapoint that satisfy all hierarchies where satisfying a hierarchy
    mean the datapoint node in this hierarchy belong to any subtrees starting from the provided
    node ids.
    With {'Geography' : [1,2],'Activity['3']}
    a datapoint is eligible if his hierarchy node is under 1 or 2  AND its activity node under 3

    To do so, we build a CTE with all base_node_id and their children, each tagged with their
    business concept, join with datapoint and group, keeping datapoints that match on
    all business_concept
    """

    if not hierarchy_filters:
        return session.exec(select(DataPoint).where(DataPoint.project_id == project_id)).all()

    # Flatten to list of (business_concept, base_id) tuples
    concept_base_pairs = [
        (bc, base_id)
        for bc, base_ids in hierarchy_filters.items()
        for base_id in base_ids
    ]

    # Anchor: all base nodes for all (business_concept, id) pairs
    anchor = (
        select(
            TreeNode.id.label('node_id'),  # type: ignore[union-attr]
            TreeNode.business_concept.label(  # type: ignore[attr-defined]
                'business_concept'),  # type: ignore[union-attr]
        )
        .where(tuple_(TreeNode.business_concept,
                      TreeNode.id).in_(concept_base_pairs))
    )

    # Recursive: children of nodes in the CTE, keeping the business_concept
    cte = anchor.cte('all_subtree_nodes', recursive=True)
    recursive = (
        select(
            TreeNode.id.label('node_id'),  # type: ignore[union-attr]
            cte.c.business_concept,
        )
        .where(TreeNode.parent_id == cte.c.node_id)
        .where(TreeNode.business_concept == cte.c.business_concept)
    )
    all_nodes_cte = cte.union_all(recursive)

    # Join DataPoints to this CTE
    stmt = (
        select(DataPoint)
        .join(NodeDataPointLink, DataPoint.id == NodeDataPointLink.datapoint_id)
        .join(TreeNode, NodeDataPointLink.node_id == TreeNode.id)
        .join(all_nodes_cte, TreeNode.id == all_nodes_cte.c.node_id)
        .where(
            DataPoint.project_id == project_id,
        )
        .group_by(DataPoint.id)
        .having(
            func.count(func.distinct(all_nodes_cte.c.business_concept)) == len(hierarchy_filters)
        )

    )

    return session.exec(stmt).all()

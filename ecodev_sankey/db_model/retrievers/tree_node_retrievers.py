"""
Module implementing all tree node retriever methods
"""
from functools import lru_cache
from typing import Iterable
from typing import Optional

import pandas as pd
from ecodev_core import logger_get
from sqlalchemy import exc
from sqlmodel import func
from sqlmodel import select
from sqlmodel import Session

from ecodev_sankey.db_model.tree_node import TreeNode

log = logger_get(__name__)


@lru_cache
def get_tree_node(project_id: int,
                  business_concept: str,
                  level: int,
                  name: str,
                  session: Session
                  ) -> TreeNode:
    """
    Retrieve a tree node given its name
    """
    try:

        return session.exec(select(TreeNode).where(
            TreeNode.project_id == project_id,
            TreeNode.business_concept == business_concept,
            TreeNode.name == name,
            TreeNode.level == level
        )).one()
    except Exception as e:
        if isinstance(e, exc.NoResultFound):
            error = f'{name} was not found in hierarchy {business_concept} for project ' +\
                    f'{project_id} at level {level}'
        else:
            error = f'{type(e).__name__} {name} appears multiple times in hierarchy '\
                f'{business_concept} for project {project_id} at level {level}'
        log.warning(error)

        raise ValueError(error)


def get_row_tree_nodes(project_id: int,
                       row: pd.Series,
                       hierarchies: dict[str, int],
                       session: Session
                       ) -> Iterable[TreeNode]:
    """
    Given a datapoint row, yields its tree nodes.
    Since some hierarchy can have varying depth, we need to iterate backward over h_size to find the
    first non null column for the given hierarchy.
    For actions, some hierarchies can be completely none and need specific handling
    """
    h_start = 0
    for hierarchy, h_size in hierarchies.items():
        try:
            vals = row.iloc[h_start:h_start+h_size].values
            h_start = h_start + h_size
            vals = [handle_number_col(k) for k in vals if not pd.isnull(k)]
            if not vals:
                continue
            name = '_'.join(vals)
            yield get_tree_node(project_id, hierarchy, len(vals)-1, name, session)
        except Exception as e:
            log.critical(f'{type(e).__name__} {e}')
            raise e


def get_node_by_id(node_id: int, session: Session):
    """
    given a node id, return it
    """
    return session.exec(select(TreeNode).where(TreeNode.id == node_id)).one()


def get_all_parent_nodes_ids(node: TreeNode) -> list[int]:
    """
    Given a tree node, return the list of ids of itself and all its parent
    """
    nodes = [node.id]

    if node.parent:
        nodes.extend(get_all_parent_nodes_ids(node.parent))

    return nodes  # type: ignore[return-value]


def get_all_children_nodes_ids(node: TreeNode) -> list[int]:
    """
    Given a tree node, return the list of ids of itself and all its parent
    """
    nodes = [node.id]

    if node.children:
        for child in node.children:
            nodes.extend(get_all_children_nodes_ids(child))

    return nodes  # type: ignore[return-value]


def get_business_axis(project_id: int, session: Session):
    """
    Return the list of tree hierarchies for the given project
    """
    return session.exec(select(TreeNode.business_concept).where
                        (TreeNode.project_id == project_id).distinct()).all()


@lru_cache(maxsize=None)
def get_node_rep(node_id: int, project_id: int, session: Session) -> dict[str, str | None]:
    """
    Given a node_id, return a dict mapping each level of the tree to its name.

    With geography data like this:
    Continent Country
    NA         USA
    NA         Canada
    Europe     France


    it will return {'continent': 'NA', 'Country': 'USA'} when provided with the node for USA
    and {'continent': 'NA', 'Country': None} when provided with the node for NA

    As this is called repeatedly to construct sankey data, we use cache which impose passing
    hashable arguments, thus calling it with node.id then reselecting node from id
    """

    node = session.exec(select(TreeNode).where(TreeNode.id == node_id)).one()

    business_concept = node.business_concept
    if node.parent:
        parent_rep = get_node_rep(node.parent.id, project_id, session)
    else:
        parent_rep = {}
        for k in get_tree_struct(business_concept, project_id, session):
            parent_rep[k] = None
            parent_rep[k+'_id'] = None
    parent_rep[node.level_name] = node.name
    parent_rep[node.level_name+'_id'] = node.id
    return parent_rep.copy()


@lru_cache
def get_tree_struct(business_concept: str,
                    project_id: int,
                    session: Session,
                    ) -> list[str]:
    """
    Given a business concept, return the list of level name:
    'Geography'=> ['Continent', 'Country']
    'LOB'=>['LOB1', 'LOB2', 'LOB3']
    """

    levels = session.exec(select(TreeNode.level,
                                 TreeNode.level_name).distinct().where(
        TreeNode.business_concept == business_concept,
        TreeNode.project_id == project_id
    ).order_by(TreeNode.level)).all()
    return list(zip(*levels))[1]  # type: ignore[return-value]


def get_tree_node_id(project_id: int,
                     business_concept: str,
                     name: str,
                     session: Session) -> int:
    """
    Given a business concept and a name, return a TreeNode id.

    nb: This won't work if several nodes have the same name in different part of the same tree
    """
    return session.exec(select(TreeNode.id)
                        .where((TreeNode.business_concept == business_concept),
                               (TreeNode.name == name),
                               (TreeNode.project_id == project_id))).one()


def get_flat_hierarchy(project_id: int, business_concept: str, session: Session) -> list[str]:
    """
    Given a hierarchy name, return a flat list of choices, covering all levels.
    It looks like this:
    ['Europe',
     'Europe | France'
     'Europe | Germany',
     'Asia',
     'Asia | Japan'
    ]
    """
    choices = []

    if session.exec(select(func.max(TreeNode.level)).where(
            TreeNode.project_id == project_id,
            TreeNode.business_concept == business_concept)).one() == 0:
        return session.exec(select(TreeNode.name).where(
            TreeNode.project_id == project_id,
            TreeNode.business_concept == business_concept
        ).order_by(TreeNode.name)).all()

    top_levels = session.exec(select(TreeNode).where(
        TreeNode.project_id == project_id,
        TreeNode.level == 0,
        TreeNode.business_concept == business_concept)).all()

    for top_level in top_levels:
        choices.extend(_get_level_choices(top_level))

    return sorted(choices)


def _get_level_choices(node: TreeNode,
                       base: Optional[str] = None
                       ) -> list[str]:
    """
    Given a node, return its all hiearchy as a flat list
    """
    choices = []
    name = node.name if not base else f'{base} | {node.name}'
    choices.append(name)
    for child in node.children:
        choices.extend(_get_level_choices(child, name))
    return choices


def get_node_children_ids(base_node_id: int, session: Session) -> list[int]:
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
    all_childrens = session.exec(select(ancestor_nodes)).all()
    return [k for k in all_childrens if k != base_node_id]


def handle_number_col(val: float | str | int) -> str:
    """
    Handle varying type col to return a str
    """
    if isinstance(val, int) or isinstance(val, float):
        val = str(int(val))
    return val.strip()

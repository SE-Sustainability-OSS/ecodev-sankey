"""
Module implementing al filtering methods
"""
from collections import defaultdict

from sqlmodel import Session

from ecodev_sankey.constants import ID
from ecodev_sankey.db_model.retrievers.tree_node_retrievers import get_node_by_id
from ecodev_sankey.db_model.retrievers.tree_node_retrievers import get_node_children_ids
from ecodev_sankey.db_model.retrievers.tree_node_retrievers import get_tree_node


def get_filter_dict(project_id: int,
                    hierarchies: list[str],
                    filter_values: list[list[str]],
                    session: Session
                    ) -> dict[str, list[int | None]]:
    """
    Given a list of filter values for each hierarchy, possibly overlapping,
    return a dict mapping hierarchy to a list of mutually exclusive node_ids matching the filter.

    To do so we merge overlapping filters by keeping only parent if parent and children are
    simultaneously present

    """
    filter_dict = {}
    for hierarchy, h_filter_values in zip(hierarchies, filter_values):

        if h_filter_values:
            reduced_filters = _get_minimal_filter_list(h_filter_values)
            filter_dict[hierarchy] = _get_filter_nodes(
                project_id, hierarchy, reduced_filters, session)
    return filter_dict


def _get_minimal_filter_list(filters: list[str]) -> dict[int, list[str]]:
    """
    Given a list of filter values at different levels of the hierarchy,
    * remove specifics filters covered by a parent one
    * return a dict mapping each hierarchy level to the list of filters kept

    ['A | B', 'A', 'C | D', 'E | F | G']
    =>
    {0:['A'],1:['D'], 2:['G']

    }
    """
    reduced_filters = defaultdict(list)
    normalized = [k.replace(' | ', '|') for k in filters]
    kept = []
    for label in sorted(normalized, key=lambda x: x.count('|')):
        levels = label.split('|')
        parents = ['|'.join(levels[:i]) for i in range(1, len(levels)+1)]
        if not any(parent in kept for parent in parents):
            kept.append(label)
    for k in kept:
        reduced_filters[k.count('|')].append(k.split('|')[-1])
    return reduced_filters


def _get_filter_nodes(project_id: int,
                      business_concept: str,
                      reduced_filters: dict[int, list[str]],
                      session: Session
                      ) -> list[int | None]:
    """
    Given the dict provided by _get_minimal_filter_list, return a dict with only node ids as values
    for storing in dcc.Store
    """
    return [get_tree_node(project_id, business_concept, level, name, session).id
            for level, names in reduced_filters.items()
            for name in names]


def merge_filter_and_node(node, filters, session):
    """
    Given a list of filters, add the selected node constraint. It implies keeping the intersection
    of the constraint from the filters and the node

    For the business concept of the node there are two cases:
    The node is a parent of some of the filters, in which case we keep all children and remove other
    filters. Otherwise, the node is a child of some filter (or there are no filter for the business
    concept) in which case we keep the node.


    """
    children = get_node_children_ids(node.id, session)
    filters[node.business_concept] = [k for k in filters.get(node.business_concept, [])
                                      if k in children] or [node.id]
    return filters


def get_merged_filter(project_id: int,
                      node_id: int,
                      selectors_ids: list[dict],
                      selector_values: list[list[str]],
                      session: Session):
    """
    Forge a filter out of the passed selector information, then keeps the intersection of
     the constraint from the filters and the node

    For the business concept of the node there are two cases:
    The node is a parent of some of the filters, in which case we keep all children and remove other
    filters. Otherwise, the node is a child of some filter (or there are no filter for the business
    concept) in which case we keep the node.
    """
    filters = get_filter_dict(project_id, [selector_id[ID] for selector_id in selectors_ids],
                              selector_values, session)
    return merge_filter_and_node(get_node_by_id(node_id, session), filters, session)

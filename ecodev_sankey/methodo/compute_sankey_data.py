"""
Module converting a list of data points (at df format to ease the conversion)
 into a networkx DiGraph. This corresponds to a Directed Acyclic Graph (or DAG). networkx provides
 very convenient helper methods to do depth-first searches, shortest path distance computations...
"""
import networkx as nx
import pandas as pd
from networkx.classes.digraph import DiGraph

from ecodev_sankey.constants import COLOR
from ecodev_sankey.constants import LABEL
from ecodev_sankey.constants import NODE_ID
from ecodev_sankey.constants import NUM_CHILDREN
from ecodev_sankey.constants import NUM_DATAPOINTS
from ecodev_sankey.constants import ROOT
from ecodev_sankey.constants import VALUE


def create_graph_from_columns(df: pd.DataFrame,
                              cols: list[str],
                              names: list[str],
                              colors: list[str]) -> DiGraph:
    """
    Create a graph out of the passed dataframe, given a list of cols

    NB: We create a root node to ease the DAG generation
    """
    graph = nx.DiGraph()
    graph.add_nodes_from([(0, {COLOR: colors[0], VALUE: 100, LABEL: ROOT})])
    for depth, column in enumerate(cols):
        _add_nodes_from_column(graph, df, column, depth, names, colors)
    _add_edges_from_columns(graph, df, cols, names, colors)
    _add_colors(graph)
    _add_num_children(graph)
    return graph


def get_node_labels(graph: DiGraph) -> list[dict[str, str]]:
    """
    Get all node labels for sankey node selector
    """
    labels = set([lab for x in graph.nodes if (lab := graph.nodes[x][LABEL]) != ROOT
                  and not lab.endswith(' - Other')])
    return [{LABEL: lab, VALUE: lab} for lab in labels]


def _add_nodes_from_column(graph: DiGraph,
                           raw_df: pd.DataFrame,
                           col: str, depth: int,
                           names: list[str],
                           colors: list[str]
                           ) -> None:
    """
    Add nodes to the passed graph corresponding to column in df.

    NB: subtlety for the higher level depth: in that case we want to create edges between those
       high level nodes and the dag root node.

    NB2: here we do sort in ascending order the nodes wrt to the quantitative column,
     as we color them in this order (and we would rather prefer to have the nodes with the
     highest value wrt to the quantitative column to color their children than the other way around
    """
    df = raw_df[[col, col+'_id', *names]].groupby(col).agg(
        {col+'_id': 'first'} | {x: 'sum' for x in names}
    ).reset_index()
    for jdx, x in df.sort_values(names).iterrows():

        node = _infos(raw_df[raw_df[col] == x[col]], jdx, x,  x[col], x[col+'_id'], names, colors)
        graph.add_nodes_from([(len(graph.nodes), node)])
        if depth == 0:
            edge = {COLOR: colors[0],  LABEL: f'source: root, target: {x[col]}'} | {
                field: x.loc[field] for field in names}
            graph.add_edges_from([(0, len(graph.nodes) - 1, edge)])


def _add_edges_from_columns(graph: DiGraph,
                            df: pd.DataFrame,
                            cols: list[str],
                            names: list,
                            colors: list[str]) -> None:
    """
    Add all edges (not related to root) to the passed graph.
    """
    nodes = {graph.nodes[node][LABEL]: node for node in graph.nodes}
    for first_col, second_col in zip(cols, cols[1:]):
        _add_edges_from_column_pairs(graph, df, first_col, second_col, nodes, names, colors)


def _add_edges_from_column_pairs(
        graph: DiGraph,
        df: pd.DataFrame,
        f_col: str,
        s_col: str,
        nodes: dict[str, int],
        names: list[str],
        colors: list[str]
) -> None:
    """
    Add all edges between nodes of f_col and s_col in the flatten df data.

    NB: Beware, huge subtlety, we forbid here cycles. To be discussed further

    NB2: Beware, huge subtlety number 2: for node who have SEVERAL (not 1, several) children and
    one of them is None, we replace this None with the following node "<node name> - Other".
    """
    dg = df[[f_col, s_col, *names]].groupby([f_col, s_col], dropna=False)[names].sum().reset_index()
    for idx, x in dg.sort_values(names, ascending=False).iterrows():
        edge = {COLOR: colors[0], LABEL: f'source: {x[f_col]} target: {x[s_col]}'} | {
            name: x.loc[name] for name in names}
        graph.add_edges_from([(nodes[x[f_col]], nodes[x[s_col]], edge)])


def _infos(df: pd.DataFrame,
           idx: int,
           x: pd.Series,
           label: str,
           node_id: int,
           names: list[str],
           colors: list[str]) -> dict:
    """
    Get node information. If the EF units are not the same for all data point under this node, only
    returns emission and number of data points under the node. If the EF unit is indeed unique,
    add the number of distinct EF, the unit, the weighted EF mean (weighted by emissions) and std.
    """
    return {
        NUM_DATAPOINTS: len(df),
        LABEL: label,
        COLOR: colors[idx % len(colors)],
        NODE_ID: node_id,
    } | {name: x[name] for name in names}


def _add_colors(graph: DiGraph) -> None:
    """
    Add all edges colors for all edges not related to root.
    """
    for node in [x for x in nx.dfs_preorder_nodes(graph, source=0, depth_limit=1) if x != 0]:
        for edge in [x for x in nx.dfs_edges(graph, source=node)]:
            graph.edges[edge][COLOR] = graph.nodes[node][COLOR]


def _add_num_children(graph: DiGraph) -> None:
    """
    Add the number of children as a node attribute
    """
    for node in graph.nodes:
        graph.nodes[node][NUM_CHILDREN] = len(list(nx.dfs_preorder_nodes(graph, source=node)))

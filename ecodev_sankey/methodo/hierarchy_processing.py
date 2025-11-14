"""
Module implementing all hierarchy processing methods
"""
from typing import Optional

import pandas as pd
from sqlmodel import Session

from ecodev_sankey.constants import DEPTH
from ecodev_sankey.constants import HIERARCHIES_SHEET
from ecodev_sankey.constants import HIERARCHY
from ecodev_sankey.db_model import handle_number_col
from ecodev_sankey.db_model import TreeNode


def get_hierarchies(xl: pd.ExcelFile) -> dict[str, int]:
    """
    Parse the hierarchy sheet to get depth per tree
    """

    return {row[HIERARCHY]: row[DEPTH] for _, row in xl.parse(HIERARCHIES_SHEET).iterrows()}


def create_level(project_id: int,
                 hierarchy_df: pd.DataFrame,
                 business_concept: str,
                 session: Session,
                 parent: Optional[TreeNode] = None,
                 level: int = 0
                 ) -> None:
    """
    Recursively create the tree based on a dataframe.
    The dataframe is expected to look like this
    depth1|depth2|depth3
    Europe|France| Paris
    Europe|France| Toulouse
    Europe| Spain| Madrid
    NA    | USA  | Portland
    NA    | USA  | Salem

    """
    for name, sub_df in hierarchy_df.groupby(hierarchy_df.columns[0]):
        sub_df = sub_df[sub_df.columns[1:]]

        name = handle_number_col(name)
        if parent:
            name = f'{parent.name}_{name}'
        node = TreeNode(business_concept=business_concept,
                        name=name,
                        level=level,
                        level_name=hierarchy_df.columns[0],
                        project_id=project_id,
                        parent=parent
                        )
        session.add(node)
        if sub_df.shape[1] > 0:
            # handle subtree with only None
            create_level(project_id, sub_df, business_concept, session, node, level+1)
        node.parent = parent
    session.commit()


def create_tree_hierarchies(project_id: int,
                            session: Session,
                            data_df: pd.DataFrame,
                            hierarchies: dict[str, int]
                            ) -> None:
    """
    Parse the xl to create the hierarchies.
    """
    col_idx = 0
    for hierarchy, h_size in hierarchies.items():
        hierarchy_df = data_df[data_df.columns[col_idx:col_idx+h_size]].drop_duplicates()
        col_idx += h_size
        create_level(project_id, hierarchy_df, hierarchy, session)

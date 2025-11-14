"""
Module ingesting template to create DataPoint and associated TreeNode
"""
from typing import Any
from typing import Callable

import pandas as pd
import progressbar
from ecodev_core import logger_get
from sqlmodel import Session
from sqlmodel.main import SQLModelMetaclass

from ecodev_sankey.constants import DESCRIPTION
from ecodev_sankey.db_model import get_node_rep
from ecodev_sankey.db_model import get_row_tree_nodes
from ecodev_sankey.db_model import handle_number_col

log = logger_get(__name__)


def process_datapoints(project_id: int,
                       session: Session,
                       df: pd.DataFrame,
                       hierarchies: dict[str, int],
                       DataPoint: SQLModelMetaclass,
                       row_getters: Callable
                       ) -> None:
    """
    Add all datapoints to the project for all provided years
    """
    try:
        process_datapoints_sheet(df, project_id, hierarchies, session, DataPoint, row_getters)
    except Exception as e:
        log.critical(f'{type(e).__name__} {e}')
        raise ValueError(f'Datapoint insertion: {type(e).__name__} {e}')


def process_datapoints_sheet(datapoint_df: pd.DataFrame,
                             project_id: int,
                             hierarchies: dict[str, int],
                             session: Session,
                             DataPoint: SQLModelMetaclass,
                             row_getters: Callable) -> None:
    """
    Given a footprint sheet, create all datapoints.
    For old years, we ignore targets as those datapoints are only provided for historical
    comparisons and not affected by targets
    """

    for _, datapoint_row in progressbar.progressbar(datapoint_df.iterrows(),
                                                    max_value=len(datapoint_df),
                                                    redirect_stdout=False):

        name = '_'.join(handle_number_col(k) for k
                        in datapoint_row.iloc[:sum(hierarchies.values())].values
                        if not pd.isna(k))
        tree_nodes = list(get_row_tree_nodes(project_id, datapoint_row, hierarchies, session))
        nodes_rep: dict[str, Any] = {}
        for node in tree_nodes:
            nodes_rep |= get_node_rep(node.id, project_id, session)
        session.add(DataPoint(name=name, description=datapoint_row.get(DESCRIPTION),
                              project_id=project_id,
                              nodes=tree_nodes,
                              nodes_rep=nodes_rep,
                              **row_getters(datapoint_row)
                              ))

    session.commit()

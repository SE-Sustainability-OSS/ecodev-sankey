"""
Module implementing template processing methods
"""
from typing import Callable

import pandas as pd
from ecodev_core import logger_get
from sqlalchemy import delete
from sqlmodel import Session
from sqlmodel.main import SQLModelMetaclass

from ecodev_sankey.db_model import NodeDataPointLink
from ecodev_sankey.db_model import TreeNode
from ecodev_sankey.methodo.datapoint_processing import process_datapoints
from ecodev_sankey.methodo.hierarchy_processing import create_tree_hierarchies

log = logger_get(__name__)


def process_file(df: pd.DataFrame,
                 project_id: int,
                 hierarchies: dict[str, int],
                 DataPoint: SQLModelMetaclass,
                 row_getters: Callable,
                 session: Session) -> None:
    """
    Process an Excel file to import project data including hierarchies and datapoints.

    Args:
        token: Authentication token for user validation
        xl: Excel file containing project data
        project_id: ID of the project to import data for
        session: Database session for operations
    """
    log.warning(f'importing file for project {project_id}')

    log.info(f'delete {project_id}')
    delete_datapoints(project_id, session, DataPoint)
    log.warning('importing hierarchies')
    create_tree_hierarchies(project_id, session, df, hierarchies)
    log.warning('importing datapoints')
    process_datapoints(project_id, session, df, hierarchies, DataPoint, row_getters)


def delete_datapoints(project_id: int, session: Session, DataPoint: SQLModelMetaclass) -> None:
    """
    Delete all existing data for a project before importing new data.

    Args:
        project_id: ID of the project to delete data for
        session: Database session for operations
    """

    log.info(f'deleting {NodeDataPointLink}')
    session.exec(delete(NodeDataPointLink).where(NodeDataPointLink.node_id == TreeNode.id,
                                                 TreeNode.project_id == project_id))
    for table in [DataPoint, TreeNode]:
        log.info(f'deleting {table}')
        # type: ignore[attr-defined]
        session.exec(delete(table).where(table.project_id == project_id))
    session.commit()

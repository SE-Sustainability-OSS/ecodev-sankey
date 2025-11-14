"""
Module impementing a link table between TreeNode and DataPoint
"""
from typing import Optional

from ecodev_core.sqlmodel_utils import SQLModelWithVal
from sqlmodel import Field


class NodeDataPointLink(SQLModelWithVal, table=True):   # type: ignore
    """
    Table storing many to many link between datapoint and tree nodes as
    one datapoint belong to several hierarchies and a node in the hierarchy can refer to multiple
    datapoints

    """
    __tablename__ = 'node_datapoint_link'
    node_id: Optional[int] = Field(default=None,
                                   foreign_key='tree_node.id',
                                   primary_key=True,
                                   index=True
                                   )
    datapoint_id: Optional[int] = Field(default=None,
                                        foreign_key='datapoint.id',
                                        primary_key=True,
                                        index=True
                                        )

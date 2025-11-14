"""
Module implementing the base data point version
"""
from typing import Optional

from ecodev_core.sqlmodel_utils import SQLModelWithVal
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field


class DataPointBase(SQLModelWithVal):
    """
    A datapoint: a name, an optional description and a representation
    """
    name: Optional[str] = Field(index=True)
    description: Optional[str] = Field(index=False)
    nodes_rep: dict = Field(sa_type=JSONB, nullable=True)

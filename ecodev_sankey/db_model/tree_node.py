"""
Module implementing the tree node class
"""
from typing import Optional

from ecodev_core.sqlmodel_utils import SQLModelWithVal
from sqlalchemy import Index
from sqlmodel import Field
from sqlmodel import Relationship

from ecodev_sankey.db_model.node_datapoint_link import NodeDataPointLink


class TreeNodeBase(SQLModelWithVal):
    """
    Base table for the node hierarchies
    Business_concept: name of the hierarchy
    name: name of the node
    level: depth of the node in the hierarchy
    """
    business_concept: str = Field(index=True)
    name: str = Field(index=True)
    level: int = Field(index=True)
    level_name: str = Field(index=True)


class TreeNode(TreeNodeBase, table=True):  # type: ignore
    """
    db version of TreeNodeBase, in many-to-many relationship with a project specific DataPoint class
    """
    __tablename__ = 'tree_node'
    id: Optional[int] = Field(default=None, primary_key=True)
    parent_id: Optional[int] = Field(default=None, foreign_key='tree_node.id', index=True)
    parent: Optional['TreeNode'] = Relationship(
        back_populates='children',
        sa_relationship_kwargs=dict(
            remote_side='TreeNode.id'  # notice the uppercase to refer to this table class
        )
    )
    children: list['TreeNode'] = Relationship(back_populates='parent',
                                              cascade_delete=True)
    project_id: Optional[int] = Field(default=None, foreign_key='project.id', index=True)
    project: Optional['Project'] = Relationship(  # type: ignore[name-defined]
        back_populates='tree_nodes')
    datapoints: list['DataPoint'] = Relationship(  # type: ignore[name-defined]
        back_populates='nodes', link_model=NodeDataPointLink)

    def __repr__(self) -> str:
        return f'TreeNode: {self.name}({self.business_concept}[{self.level}]) {self.id}'

    __table_args__ = (
        Index('idx_tree_node_composite', 'project_id', 'level', 'business_concept'),
    )

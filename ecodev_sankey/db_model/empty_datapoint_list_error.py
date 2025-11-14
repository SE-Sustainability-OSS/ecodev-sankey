"""
Module implementing a message specific error for empty datapoint associated data
"""


class EmptyDatapointList(Exception):
    """
    message specific error for empty datapoint associated data
    """

    def __init__(self, message):
        self.message = message

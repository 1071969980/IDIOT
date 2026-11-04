class HILMsgStreamMissingError(Exception):
    pass


class HILInterruptCancelled(Exception):
    pass


class HILInterruptTimeout(HILInterruptCancelled):
    """The HIL interaction exceeded its business deadline."""

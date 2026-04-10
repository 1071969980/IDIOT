class ChatProcessingError(Exception):
    """处理待回复消息的基础异常"""

    status_code = 500

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class SessionNotFoundError(ChatProcessingError):
    status_code = 404


class SessionNotOwnedError(ChatProcessingError):
    status_code = 404


class BranchNotFoundError(ChatProcessingError):
    status_code = 404


class NoPendingTaskError(ChatProcessingError):
    status_code = 404


class NoPendingMessagesError(ChatProcessingError):
    status_code = 404


class BranchProcessingConflictError(ChatProcessingError):
    status_code = 409


class SystemPromptNotConfiguredError(ChatProcessingError):
    status_code = 500

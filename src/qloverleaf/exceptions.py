from dataclasses import dataclass

from lark import Token


class QLoverleafError(Exception):
    def __init__(self, message: str, token: Token | None = None) -> None:
        super().__init__(message)
        self.token = token

    def __str__(self) -> str:
        msg = str(self.args[0])
        if self.token is not None:
            return f"Error at line {self.token.line}, column {self.token.column}: {msg}"
        return msg


class ParseError(QLoverleafError):
    pass


class QueryError(QLoverleafError):
    pass


class UnsupportedFeatureError(QueryError):
    """Feature is explicitly out of scope (e.g. [date:], [diff:], timeline)."""

    pass


class UnimplementedFeatureError(QueryError):
    """Feature is in scope but not yet implemented."""

    pass


class TranslationError(QLoverleafError):
    """Translator produced SPARQL that QLever rejected — indicates a translator bug."""

    pass


class ExecutionError(QLoverleafError):
    pass


class BackendError(ExecutionError):
    """QLever returned an error or an unexpected response."""

    pass


class NetworkError(ExecutionError):
    """Transient network failure — could not establish or maintain a connection."""

    pass


class TimeoutError(ExecutionError):
    """Connected to QLever but did not receive a timely response."""

    pass


class QueryLimitError(ExecutionError):
    """Query hit a user-configured global limit ([timeout:N] or [maxsize:N])."""

    pass


class QueryTimeoutError(QueryLimitError):
    """Query exceeded its [timeout:N] limit."""

    pass


class QueryMaxsizeError(QueryLimitError):
    """Query result exceeded its [maxsize:N] limit."""

    pass


@dataclass
class QueryWarning:
    message: str
    token: Token | None

    def __str__(self) -> str:
        if self.token is not None:
            return (
                f"Warning at line {self.token.line}, column {self.token.column}: "
                f"{self.message}"
            )
        return f"Warning: {self.message}"

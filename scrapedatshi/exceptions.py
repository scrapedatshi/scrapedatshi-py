"""
scrapedatshi.exceptions
~~~~~~~~~~~~~~~~~~~~~~~
All exceptions raised by the scrapedatshi SDK.
"""


class ScrapedatshiError(Exception):
    """Base exception for all scrapedatshi SDK errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, status_code={self.status_code})"


class AuthError(ScrapedatshiError):
    """Raised when the API key is missing, invalid, or revoked (HTTP 401/403)."""


class RateLimitError(ScrapedatshiError):
    """Raised when the user has exceeded their tier's rate or monthly limit (HTTP 429)."""


class TierError(ScrapedatshiError):
    """Raised when the requested feature is not available on the user's current tier (HTTP 403)."""


class ValidationError(ScrapedatshiError):
    """Raised when the API returns a 422 Unprocessable Entity (bad request payload)."""


class ServerError(ScrapedatshiError):
    """Raised when the API returns a 5xx server error."""


class TimeoutError(ScrapedatshiError):
    """Raised when the request times out."""

"""custom errors module"""
from time import time
from datetime import datetime


class ClaudeAPIError(Exception):
    """Base class for ClaudeAPIClient exceptions"""


class MessageRateLimitError(ClaudeAPIError):
    """Exception for MessageRateLimit
    Will hold three variables:

    - `reset_timestamp`: Timestamp in seconds at which the rate limit expires.

    - `reset_date`: Formatted datetime string (%Y-%m-%d %H:%M:%S) at which the rate limit expires.

    - `sleep_sec`: Amount of seconds to wait before reaching the expiration timestamp
    (Auto calculated based on reset_timestamp)"""

    def __init__(self, reset_timestamp: int, *args: object) -> None:
        super().__init__(*args)
        self.reset_timestamp: int = reset_timestamp
        """
        The timestamp in seconds when the message rate limit will be reset
        """
        self.reset_date: str = datetime.fromtimestamp(reset_timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        """
        Formatted datetime string of expiration timestamp in the format %Y-%m-%d %H:%M:%S
        """

    @property
    def sleep_sec(self) -> int:
        """
        The amount of seconds to wait before reaching the reset_timestamp
        """
        return int(abs(time() - self.reset_timestamp)) + 1


class OverloadError(ClaudeAPIError):
    """Exception wrapping the Claude's overload_error"""

    def __init__(self, *args: object) -> None:
        super().__init__(*args)

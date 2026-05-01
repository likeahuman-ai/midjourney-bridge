"""midjourney-bridge: drive your own Midjourney subscription from Python, the CLI, or Claude via MCP."""

__version__ = "0.1.0"

from midjourney_bridge.client import MJClient
from midjourney_bridge.errors import (
    CloudflareBlockedError,
    MJError,
    RateLimitedError,
    SessionExpiredError,
)

__all__ = [
    "CloudflareBlockedError",
    "MJClient",
    "MJError",
    "RateLimitedError",
    "SessionExpiredError",
    "__version__",
]

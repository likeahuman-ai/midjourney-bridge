"""Auto-extract Midjourney session cookies from a local browser.

Uses ``browser-cookie3`` to read + decrypt cookies directly from the browser's
SQLite database. Tries Chrome first, falls back through Brave/Arc/Edge/Vivaldi/
Chromium/Firefox/Opera in order. Triggers a one-time OS keychain prompt the
first time a given Python binary accesses Chrome's encrypted cookie store.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar
from typing import TYPE_CHECKING

import browser_cookie3 as bc3

if TYPE_CHECKING:
    pass

# Required cookies for the bridge to work
REQUIRED_AUTH = "__Host-Midjourney.AuthUserTokenV3_i"
REQUIRED_REFRESH = "__Host-Midjourney.AuthUserTokenV3_r"
RECOMMENDED = ("cf_clearance", "__cf_bm", "_cfuvid")

# Browser priority order — Chrome first because it's the most common, then
# other Chromium-derivatives that share the same cookie format, Firefox last.
DEFAULT_FALLBACK_ORDER = (
    "chrome",
    "brave",
    "arc",
    "edge",
    "vivaldi",
    "chromium",
    "opera",
    "firefox",
)


class ExtractionError(Exception):
    """Raised when no usable session could be extracted."""


@dataclass(frozen=True)
class ExtractedSession:
    """A successfully-extracted browser session."""

    cookie: str
    user_agent: str
    browser: str
    cookie_names: tuple[str, ...]


# ---------------------------------------------------------------------------
# Cookie extraction
# ---------------------------------------------------------------------------


def _bc3_loaders() -> dict[str, Callable[..., CookieJar]]:
    """Map browser name → browser_cookie3 loader function."""
    return {
        "chrome": bc3.chrome,
        "brave": bc3.brave,
        "arc": bc3.arc,
        "edge": bc3.edge,
        "vivaldi": bc3.vivaldi,
        "chromium": bc3.chromium,
        "opera": bc3.opera,
        "firefox": bc3.firefox,
    }


def supported_browsers() -> tuple[str, ...]:
    """Browsers we can extract from."""
    return tuple(_bc3_loaders().keys())


def _try_browser(name: str) -> CookieJar | None:
    """Try to load MJ cookies from a single browser. Returns None on any failure."""
    loader = _bc3_loaders().get(name)
    if loader is None:
        return None
    try:
        return loader(domain_name="midjourney.com")
    except Exception:
        # browser-cookie3 raises a wide variety of exceptions:
        # BrowserCookieError if browser not installed, sqlite3.OperationalError if locked,
        # OSError if keychain denied, etc. Treat all as "not available."
        return None


def _jar_to_cookie_string(jar: CookieJar) -> str:
    """Format a CookieJar as a single Cookie header string."""
    parts: list[str] = []
    for c in jar:
        if not isinstance(c, Cookie):
            continue
        # Filter to MJ-related cookies only — jar already filtered by domain,
        # but be paranoid about cross-subdomain leakage.
        if c.domain and "midjourney.com" not in c.domain:
            continue
        parts.append(f"{c.name}={c.value}")
    return "; ".join(parts)


def _cookie_names(jar: CookieJar) -> tuple[str, ...]:
    return tuple(c.name for c in jar if isinstance(c, Cookie))


def _has_required(jar: CookieJar) -> bool:
    names = {c.name for c in jar if isinstance(c, Cookie)}
    return REQUIRED_AUTH in names


# ---------------------------------------------------------------------------
# User-Agent auto-detection
# ---------------------------------------------------------------------------


def detect_chrome_version() -> str | None:
    """Detect the installed Chrome major.minor.build.patch version."""
    candidates: list[str] = []
    sysname = platform.system()
    if sysname == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
    elif sysname == "Linux":
        candidates = [
            p
            for p in (
                shutil.which("google-chrome"),
                shutil.which("google-chrome-stable"),
                shutil.which("chromium"),
                shutil.which("chromium-browser"),
            )
            if p
        ]
    elif sysname == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]

    for path in candidates:
        try:
            out = subprocess.check_output(
                [path, "--version"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode(errors="ignore")
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)", out)
            if match:
                return match.group(1)
        except (subprocess.SubprocessError, OSError):
            continue
    return None


def build_user_agent(version: str | None = None) -> str:
    """Build a Chrome User-Agent string. Auto-detects version if not provided.

    Uses the Reduced UA format that real Chrome ships in 2024+: major.0.0.0 for
    privacy, even though the full version is detectable elsewhere. Matches what
    we observed in real captures.
    """
    detected = version or detect_chrome_version() or "147.0.7727.119"
    major = detected.split(".")[0]
    sysname = platform.system()
    if sysname == "Darwin":
        platform_str = "Macintosh; Intel Mac OS X 10_15_7"
    elif sysname == "Windows":
        platform_str = "Windows NT 10.0; Win64; x64"
    else:
        platform_str = "X11; Linux x86_64"
    return (
        f"Mozilla/5.0 ({platform_str}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract(
    browser: str | None = None,
    *,
    fallback_order: tuple[str, ...] = DEFAULT_FALLBACK_ORDER,
) -> ExtractedSession:
    """Extract MJ session cookies from a local browser.

    If ``browser`` is given, only try that one. Otherwise walk the fallback
    order until one yields a jar with the required auth cookie present.

    Raises ``ExtractionError`` if nothing usable is found.
    """
    candidates: tuple[str, ...] = (browser,) if browser else fallback_order
    attempts: list[tuple[str, str]] = []  # (browser, reason)

    for name in candidates:
        jar = _try_browser(name)
        if jar is None:
            attempts.append((name, "not available or denied"))
            continue
        if not _has_required(jar):
            attempts.append((name, f"no {REQUIRED_AUTH} cookie"))
            continue
        return ExtractedSession(
            cookie=_jar_to_cookie_string(jar),
            user_agent=build_user_agent(),
            browser=name,
            cookie_names=_cookie_names(jar),
        )

    summary = "\n  ".join(f"{n}: {why}" for n, why in attempts)
    raise ExtractionError(
        f"Could not extract MJ session from any browser. Tried:\n  {summary}\n\n"
        f"Make sure you're logged in to midjourney.com in one of: "
        f"{', '.join(supported_browsers())}.\n"
        f"On macOS you may also need to grant Keychain access when prompted."
    )

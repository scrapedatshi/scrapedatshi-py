"""
scrapedatshi.auth — Local Playwright session capture.

Opens a real, headed browser window so you can log in manually through any
authentication flow (Okta, Duo, standard login forms, MFA, etc.).  Once you
press Enter in the terminal the SDK captures the full browser storage state
(cookies + localStorage) and returns it ready to pass to any pipeline method.

Install the optional dependency before use::

    pip install scrapedatshi[auth]
    playwright install chromium

Usage::

    from scrapedatshi.auth import capture_session

    state = capture_session("https://internal.company.com/login")

    result = client.pipeline.crawl(
        "https://internal.company.com",
        storage_state=state,
        max_pages=20,
    )

    # Save for later reuse
    import json
    with open("session.auth.json", "w") as f:
        json.dump(state, f)

    # Load saved state
    with open("session.auth.json") as f:
        state = json.load(f)

.. warning::
    The generated session.auth.json contains live security keys capable of
    impersonating your user profile.  Never commit your .auth.json files to
    Git repositories.  Generated test sandboxes created using
    ``scrapedatshi init`` are automatically pre-configured with .gitignore
    filters tracking ``*.auth.json``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any


def capture_session(
    url: str,
    browser: str = "chromium",
    save_to: str | None = None,
) -> dict[str, Any]:
    """Open a headed browser, let the user log in, then capture the session.

    Parameters
    ----------
    url:
        The login page URL to open.  Navigate to the page that requires
        authentication — the browser will open directly to this URL.
    browser:
        Which browser engine to use.  One of ``"chromium"`` (default),
        ``"firefox"``, or ``"webkit"``.
    save_to:
        Optional file path to save the captured state as JSON (e.g.
        ``"session.auth.json"``).  If *None* the state is only returned,
        not saved.

    Returns
    -------
    dict
        A Playwright ``storage_state`` dict containing ``cookies`` and
        ``origins`` (localStorage).  Pass this directly to any pipeline
        method via the ``storage_state=`` keyword argument.

    Raises
    ------
    ImportError
        If ``playwright`` is not installed.  Run::

            pip install scrapedatshi[auth]
            playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "playwright is required for session capture.\n"
            "Install it with:\n\n"
            "    pip install scrapedatshi[auth]\n"
            "    playwright install chromium\n"
        ) from exc

    return _run_capture(url=url, browser=browser, save_to=save_to)


def _run_capture(
    url: str,
    browser: str,
    save_to: str | None,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright  # type: ignore[import]

    # Stealth user-agent — prevents Cloudflare/Okta bot detection on the
    # local capture step (the login itself, not the subsequent crawl).
    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    print()
    print("━" * 60)
    print("  scrapedatshi — Session Capture")
    print("━" * 60)
    print(f"  Opening browser → {url}")
    print()
    print("  1. Log in to your account in the browser window.")
    print("  2. Complete any MFA / Duo / Okta prompts.")
    print("  3. Once you are fully authenticated, return here")
    print("     and press Enter to capture the session.")
    print()
    print("  ⚠  WARNING: The captured session.auth.json contains live")
    print("     security keys capable of impersonating your user profile.")
    print("     Never commit .auth.json files to Git repositories.")
    print("━" * 60)
    print()

    with sync_playwright() as p:
        launcher = getattr(p, browser)
        b = launcher.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = b.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Unlimited timeout — user may need time for MFA prompts
        page.set_default_timeout(0)

        page.goto(url)

        # Wait for user to finish logging in
        try:
            input("  ✅ Press Enter when you are fully logged in... ")
        except (EOFError, KeyboardInterrupt):
            print("\n  Capture cancelled.")
            b.close()
            sys.exit(0)

        print()
        print("  Capturing session state...")

        state: dict[str, Any] = context.storage_state()
        b.close()

    cookie_count = len(state.get("cookies", []))
    origin_count = len(state.get("origins", []))
    print(f"  ✓ Captured {cookie_count} cookies, {origin_count} localStorage origin(s)")

    if save_to:
        with open(save_to, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        print(f"  ✓ Saved to {save_to}")
        print()
        print("  ⚠  WARNING: The generated session.auth.json contains live")
        print("     security keys capable of impersonating your user profile.")
        print("     Never commit your .auth.json files to Git repositories.")
        print("     Generated test sandboxes created using `scrapedatshi init`")
        print("     are automatically pre-configured with .gitignore filters")
        print("     tracking *.auth.json.")

    print()
    return state

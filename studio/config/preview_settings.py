"""Local Tailscale preview settings for the responsive Studio worktree.

The API binds to loopback and is reached through the same-origin preview server.
The ClickHouse connection remains the one selected by SIGMARAIL_HOME.
"""

from __future__ import annotations

import os
import secrets

from config.settings import *  # noqa: F403

DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or secrets.token_urlsafe(48)

_tailscale_host = os.environ.get("SIGMARAIL_PREVIEW_HOST", "turnip.tail850cb1.ts.net").strip()
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]
if _tailscale_host:
    ALLOWED_HOSTS.append(_tailscale_host)

CSRF_TRUSTED_ORIGINS = [f"https://{_tailscale_host}"] if _tailscale_host else []

# Paper account workflows are in scope for this preview. Live account creation
# and live deployment start remain unavailable, even if a live profile exists.
MIDDLEWARE = [  # noqa: F405
    *MIDDLEWARE,  # noqa: F405
    "config.preview_safety.PaperOnlyPreviewMiddleware",
]

"""Runtime configuration for browser integrations."""

import os


# Chrome extension IDs are installation/profile-specific. Set this in `.env`
# (or the process environment) for the Chrome profile used by Playwright MCP.
SIMPLIFY_EXTENSION_ID = os.environ.get(
    "SIMPLIFY_EXTENSION_ID", "hi"
).strip()

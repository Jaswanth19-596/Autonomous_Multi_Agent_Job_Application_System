import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


load_dotenv()


SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.send",
]


TOKEN_FILE = Path("credentials/gmail_token.json")


def get_gmail_credentials():

    credentials = None

    # Existing token
    if TOKEN_FILE.exists():
        try:
            credentials = Credentials.from_authorized_user_file(
                TOKEN_FILE,
                SCOPES,
            )
            # Verify cached token contains all required scopes
            token_data = json.loads(TOKEN_FILE.read_text())
            granted_scopes = set(token_data.get("scopes", []))
            if not set(SCOPES).issubset(granted_scopes):
                credentials = None
        except Exception:
            credentials = None

    # Refresh existing token
    if credentials and credentials.expired:

        if credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception:
                # Refresh failed (revoked, scope change, etc.)
                # Fall through to fresh auth below.
                credentials = None

    # First-time authentication
    if not credentials or not credentials.valid:

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise RuntimeError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET "
                "must be set in .env"
            )

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [
                    "http://localhost"
                ],
            }
        }

        flow = InstalledAppFlow.from_client_config(
            client_config,
            SCOPES,
        )

        credentials = flow.run_local_server(
            port=0
        )

        TOKEN_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        TOKEN_FILE.write_text(
            credentials.to_json()
        )

    return credentials
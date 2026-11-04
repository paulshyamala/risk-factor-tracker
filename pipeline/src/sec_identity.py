"""SEC contact identity for EDGAR requests, read from pipeline/.env like the API key."""
import os
from pathlib import Path

from dotenv import load_dotenv
from edgar import set_identity

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def use_sec_identity():
    load_dotenv(ENV_PATH, override=True)
    agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not agent:
        raise SystemExit(f'SEC_USER_AGENT is not set. Add SEC_USER_AGENT="Your Name your@email.com" to {ENV_PATH}')
    set_identity(agent)

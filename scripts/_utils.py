"""Shared utilities for Phase 0 validation scripts."""

import os
from pathlib import Path


def load_dotenv():
    """Load .env file from project root into os.environ.
    
    Only sets keys that are not already present in the environment
    (real env vars always win over .env files).
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value

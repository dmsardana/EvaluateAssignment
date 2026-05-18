"""Registers the default set of credentials on import of the package."""
from __future__ import annotations

import os
from pathlib import Path


def register_defaults() -> None:
    """Idempotent — safe to call multiple times."""
    from web.api.services.credentials import REGISTRY
    from web.api.services.credentials.google import GoogleCredentialHandle

    token_path = Path(os.environ.get(
        "GOOGLE_TOKEN_PATH",
        Path(__file__).resolve().parents[4] / "token.json",
    ))

    if "google_oauth" not in {h.name for h in REGISTRY.all()}:
        REGISTRY.register(GoogleCredentialHandle(token_path=token_path))

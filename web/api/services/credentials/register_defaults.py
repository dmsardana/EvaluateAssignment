"""Registers the default set of credentials on import of the package."""
from __future__ import annotations

import os
from pathlib import Path


def register_defaults() -> None:
    """Idempotent — safe to call multiple times."""
    from web.api.services.credentials import REGISTRY
    from web.api.services.credentials.google import GoogleCredentialHandle
    from web.api.services.credentials import store
    from web.api.services.credentials.notifier import StatusEdgeNotifier

    token_path = Path(os.environ.get(
        "GOOGLE_TOKEN_PATH",
        Path(__file__).resolve().parents[4] / "token.json",
    ))

    if "google_oauth" not in {h.name for h in REGISTRY.all()}:
        REGISTRY.register(GoogleCredentialHandle(token_path=token_path))

    if "anthropic_api" not in {h.name for h in REGISTRY.all()}:
        from web.api.services.credentials.anthropic import AnthropicCredentialHandle
        REGISTRY.register(AnthropicCredentialHandle())

    if "gemini_api" not in {h.name for h in REGISTRY.all()}:
        from web.api.services.credentials.gemini import GeminiCredentialHandle
        REGISTRY.register(GeminiCredentialHandle())

    if "openai_api" not in {h.name for h in REGISTRY.all()}:
        from web.api.services.credentials.openai import OpenAICredentialHandle
        REGISTRY.register(OpenAICredentialHandle())

    recipient = os.environ.get("OPS_ALERT_EMAIL", "").strip() or None
    if recipient and not getattr(REGISTRY, "_notifier_attached", False):
        from tools.email_helper import send_email  # late import — avoids circular

        notifier = StatusEdgeNotifier(
            send_email=send_email,
            read_one=store.read_one,
            update_notified_at=store.update_notified_at,
            recipient=recipient,
        )
        REGISTRY.subscribe_transition(notifier.on_transition)
        REGISTRY._notifier_attached = True

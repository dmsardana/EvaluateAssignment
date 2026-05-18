from __future__ import annotations


def test_default_registry_has_google_oauth():
    from web.api.services.credentials import REGISTRY

    h = REGISTRY.get("google_oauth")
    assert h.name == "google_oauth"


def test_default_registry_has_anthropic_api():
    from web.api.services.credentials import REGISTRY

    h = REGISTRY.get("anthropic_api")
    assert h.name == "anthropic_api"

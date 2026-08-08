"""
pharmagpt/providers/factory.py — AI provider selection.

get_ai_client() reads AI_PROVIDER (pharmagpt/config.py, sourced from .env)
and returns a client object duck-typed to google.genai.Client's
`.models.generate_content()` / `.models.generate_content_stream()`
interface. pharmagpt/state.py assigns the result to `gemini_client`, so
every existing route/service module (which all do
`from pharmagpt.state import gemini_client`) keeps working unchanged
regardless of which provider is active.

  AI_PROVIDER=gemini    (default) -> google.genai.Client — identical to
                                      pre-provider-abstraction behavior.
  AI_PROVIDER=nemotron            -> pharmagpt.providers.nemotron_client.NemotronClient
"""

from __future__ import annotations

import logging

from google import genai

logger = logging.getLogger(__name__)


class ProviderConfigError(RuntimeError):
    """Raised at startup when AI_PROVIDER is unsupported, or a required key
    for the selected provider is missing. Fails fast at import time
    (pharmagpt/state.py) rather than surfacing as an opaque error on the
    first AI call — same fail-fast principle config.py already applies to
    FLASK_SECRET_KEY."""


def get_ai_client(
    provider: str,
    gemini_api_key: str | None,
    nvidia_api_key: str | None,
    nvidia_model: str | None,
):
    provider = (provider or "gemini").strip().lower()

    if provider == "gemini":
        logger.info("AI provider: Google Gemini")
        return genai.Client(api_key=gemini_api_key)

    if provider == "nemotron":
        if not nvidia_api_key:
            raise ProviderConfigError(
                "AI_PROVIDER=nemotron requires NVIDIA_API_KEY to be set in .env."
            )
        if not nvidia_model:
            raise ProviderConfigError(
                "AI_PROVIDER=nemotron requires NVIDIA_MODEL to be set in .env "
                "to the exact model catalog slug from build.nvidia.com."
            )
        if not nvidia_api_key.startswith("nvapi-"):
            # Non-blocking: NVIDIA-issued API keys are documented as always
            # starting with "nvapi-" (build.nvidia.com). A key without that
            # prefix isn't necessarily invalid (e.g. a proxy/gateway in
            # front of the real NVIDIA endpoint), so this only warns rather
            # than raising ProviderConfigError.
            logger.warning(
                "NVIDIA_API_KEY does not start with the expected 'nvapi-' "
                "prefix — verify it was copied correctly from build.nvidia.com."
            )
        from pharmagpt.providers.nemotron_client import NemotronClient

        logger.info("AI provider: NVIDIA Nemotron (model=%s)", nvidia_model)
        return NemotronClient(api_key=nvidia_api_key, model=nvidia_model)

    raise ProviderConfigError(
        f"Unknown AI_PROVIDER '{provider}'. Supported values: 'gemini', 'nemotron'."
    )

"""Complete, UI-ready pricing catalogs for every selectable provider.

The database contains explicit price overrides.  Provider clients contain the
models that can actually appear in Imprint's selectors.  Settings needs the
union of both: showing database rows alone made an older install look as if it
only supported Anthropic.

An unpriced model inherits its provider's ``default`` estimate when one exists.
That inheritance is surfaced explicitly; it is never presented as an exact
model price.  A zero rate means unknown, not free.  Ollama is labelled as local
compute because it has no provider API token charge.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.recommendations.catalog import known_text_models


TEXT_PROVIDERS = (
    "openai",
    "anthropic",
    "deepseek",
    "kimi",
    "gemini",
    "qwen",
    "ollama",
)

PROVIDER_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "gemini": "Gemini",
    "qwen": "Qwen",
    "ollama": "Ollama",
}


@dataclass(frozen=True)
class TokenPriceEntry:
    provider: str
    model: str
    input_usd: float | None
    cached_input_usd: float | None
    output_usd: float | None
    source: str

    @property
    def provider_label(self) -> str:
        return PROVIDER_LABELS.get(self.provider, self.provider.title())

    @property
    def status(self) -> str:
        return {
            "exact": "Exact model rate",
            "default": "Uses provider default",
            "unknown": "Price unknown",
            "local": "Local compute",
        }[self.source]


def _positive(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def build_token_price_catalog(conn) -> list[TokenPriceEntry]:
    """Return every known selectable text model plus explicit database rows."""
    rows = conn.execute(
        "SELECT backend, model, input_per_1m_usd, output_per_1m_usd, "
        "cached_input_per_1m_usd FROM pricing ORDER BY backend, model"
    ).fetchall()
    exact = {(r["backend"].casefold(), r["model"]): r for r in rows}

    providers = list(TEXT_PROVIDERS)
    for backend, _model in exact:
        if backend not in providers and backend != "per_unit_usd":
            providers.append(backend)

    catalog: list[TokenPriceEntry] = []
    for provider in providers:
        models = set(known_text_models(provider))
        models.update(model for backend, model in exact if backend == provider)
        # Keep the provider default visible because it controls estimates for
        # any live model the app has not learned by name yet.
        if provider != "ollama" and (provider, "default") in exact:
            models.add("default")

        default = exact.get((provider, "default"))
        for model in sorted(models, key=lambda value: (value != "default", value.casefold())):
            row = exact.get((provider, model))
            if provider == "ollama" and row is None:
                catalog.append(TokenPriceEntry(provider, model, None, None, None, "local"))
                continue

            source = "exact"
            effective = row
            if effective is None:
                effective = default
                source = "default" if default is not None else "unknown"

            if effective is None:
                values = (None, None, None)
            else:
                values = (
                    _positive(effective["input_per_1m_usd"]),
                    _positive(effective["cached_input_per_1m_usd"]),
                    _positive(effective["output_per_1m_usd"]),
                )
                if values[0] is None or values[2] is None:
                    source = "unknown"

            catalog.append(TokenPriceEntry(provider, model, *values, source))
    return catalog


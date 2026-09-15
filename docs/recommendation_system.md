# Provider and model recommendations

Status: deterministic v1, September 2026.

## Contract

Every agent with a provider/model selector owns an immutable requirement
profile in `agents/<key>/recommendations.py`. The umbrella discovers that
profile through `agents/recommendation_profiles.py`; agents never hard-code a
provider or model id as the universal answer.

`services/recommendations/` owns the shared mechanism:

- `models.py` defines profiles, candidates, request context and results.
- `catalog.py` adapts selectable text and media models into comparable,
  conservative capability records. Unknown live text models receive family
  defaults instead of disappearing.
- `engine.py` first removes incompatible, retired, unavailable and over-budget
  choices, then applies the agent's quality, reliability, cost, speed, context
  and privacy weights.

The provider menu marks the provider containing the best eligible model. The
model menu marks the best eligible model inside the provider the user currently
selected. A manual provider choice is therefore still supported with useful
guidance rather than treated as an error.

## Explanation and UI data

Recommendations never change provider/model display text. The GUI stores the
marker, explanation, score, confidence and badge in dedicated Qt item roles
defined by `ui/widgets.py`. This keeps recommendations separate from semantic
foreground colours such as the warning for a local model that is too large for
the current machine.

The explanation names the task, strongest dimensions, normalized fit score,
confidence, and whether the result is merely a setup target because no eligible
provider is configured. Tooltips expose this reasoning on both the field and
the marked menu row.

## Recalculation

The ranker runs again when relevant task/format controls, selected provider,
budget limits, API permissions, video aspect or video duration change. It uses
only local metadata and UI state; opening a dropdown never makes a network or
paid model call.

## Safety and evolution

The current score is deterministic and covered by contract tests. Future
learning may adjust reliability and retry estimates from aggregate completed
runs, but it must not silently optimize for provider usage or gross revenue.
Any income-oriented utility function must subtract generation cost, retry cost,
time and measured risk, and must distinguish observed results from forecasts.

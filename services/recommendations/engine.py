"""Deterministic, explainable recommendation ranking.

Hard constraints are applied before preferences.  The result is a useful
default, not a claim that one vendor is universally superior: each agent owns
its requirement profile and every score can be explained from that profile.
"""

from __future__ import annotations

from .models import AgentProfile, Candidate, RecommendationContext, RecommendationResult


class RecommendationEngine:
    """Rank candidates for one agent and one concrete request context."""

    def recommend(
        self,
        profile: AgentProfile,
        candidates: list[Candidate] | tuple[Candidate, ...],
        context: RecommendationContext,
    ) -> RecommendationResult | None:
        eligible = [item for item in candidates if self._eligible(item, context)]
        if context.selected_provider:
            wanted = context.selected_provider.casefold()
            eligible = [item for item in eligible
                        if item.provider.casefold() == wanted]
        if not eligible:
            return None

        # Availability is a hard constraint when at least one eligible option
        # is known to work.  If none is configured, still return the best setup
        # target and say so instead of leaving every menu without guidance.
        ready = [item for item in eligible if item.available is True]
        fallback = not ready
        pool = ready or [item for item in eligible if item.available is not False]
        if not pool:
            pool = eligible

        ranked = sorted(
            ((self._score(profile, item, context), item) for item in pool),
            key=lambda pair: (pair[0], pair[1].provider.casefold(),
                              pair[1].model_id.casefold()),
            reverse=True,
        )
        score, winner = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        gap = score - runner_up
        confidence = "high" if gap >= 0.10 else "medium" if gap >= 0.035 else "low"
        reason = self._explain(profile, winner, context, score, fallback)
        return RecommendationResult(
            candidate=winner,
            score=score,
            confidence=confidence,
            reason=reason,
            fallback=fallback,
        )

    @staticmethod
    def _eligible(item: Candidate, context: RecommendationContext) -> bool:
        if item.retired or item.modality != context.modality:
            return False
        if context.required_kind and item.kind != context.required_kind:
            return False
        if context.aspect and item.aspects and context.aspect not in item.aspects:
            return False
        if (context.duration is not None and item.kind == "direct_video"
                and item.durations and context.duration not in item.durations):
            return False
        if (context.budget_remaining is not None and item.estimated_cost is not None
                and item.estimated_cost > max(0.0, context.budget_remaining)):
            return False
        return True

    @staticmethod
    def _weights(profile: AgentProfile, priority: str) -> dict[str, float]:
        weights = {
            "quality": profile.quality_weight,
            "reliability": profile.reliability_weight,
            "cost": profile.cost_weight,
            "speed": profile.speed_weight,
            "context": profile.context_weight,
            "privacy": profile.privacy_weight,
        }
        focus = {
            "quality": "quality", "cost": "cost", "speed": "speed",
            "privacy": "privacy",
        }.get(priority)
        if focus:
            weights[focus] *= 1.8
        total = sum(weights.values()) or 1.0
        return {key: value / total for key, value in weights.items()}

    def _score(self, profile: AgentProfile, item: Candidate,
               context: RecommendationContext) -> float:
        tags = list(profile.task_tags)
        if context.task:
            normalized = context.task.casefold().replace("/", " ").replace("-", " ")
            synonyms = {
                "creative": ("write", "scene", "dialogue", "story", "fiction", "hook"),
                "longform": ("chapter", "draft", "outline", "book", "album"),
                "editing": ("revise", "improve", "tighten", "edit", "polish"),
                "analysis": ("analyse", "analyze", "research", "argument", "metrics"),
                "code": ("website", "dashboard", "framework", "component", "code"),
                "marketing": ("campaign", "promo", "sales", "release", "landing"),
                "social": ("social", "caption", "post", "tiktok", "instagram"),
                "planning": ("plan", "strategy", "calendar", "schedule"),
                "structured": ("report", "export", "publish", "format"),
            }
            tags.extend(tag for tag, words in synonyms.items()
                        if any(word in normalized for word in words))
        tag_scores = [item.task_fit.get(tag, item.task_fit.get("general", 0.62))
                      for tag in tags]
        task_fit = sum(tag_scores) / len(tag_scores) if tag_scores else 0.62
        affinity = profile.provider_affinity.get(item.provider.casefold(), 0.72)
        fit = 0.72 * task_fit + 0.28 * affinity

        weights = self._weights(profile, context.priority)
        preference = (
            item.quality * weights["quality"]
            + item.reliability * weights["reliability"]
            + item.cost_efficiency * weights["cost"]
            + item.speed * weights["speed"]
            + item.context * weights["context"]
            + item.privacy * weights["privacy"]
        )
        # Task fit is intentionally outside the preference weights: changing
        # to "cost" must not turn an unsuitable modality/model into the winner.
        return round(0.52 * fit + 0.48 * preference, 6)

    @staticmethod
    def _explain(profile: AgentProfile, item: Candidate,
                 context: RecommendationContext, score: float,
                 fallback: bool) -> str:
        strengths = sorted(
            ((item.quality, "output quality"),
             (item.reliability, "reliability"),
             (item.cost_efficiency, "cost efficiency"),
             (item.speed, "speed"),
             (item.context, "long-context handling"),
             (item.privacy, "local privacy")),
            reverse=True,
        )
        top = " and ".join(label for _value, label in strengths[:2])
        task = context.task.strip() or ", ".join(profile.task_tags[:2])
        setup = (" No eligible configured provider was detected, so this is the "
                 "best setup target; add its API key or local model before running."
                 if fallback else " It is available in the current setup.")
        return (
            f"Best match for {profile.label} ({task}): {top}. "
            f"Fit score {round(score * 100)}/100.{setup}"
        )

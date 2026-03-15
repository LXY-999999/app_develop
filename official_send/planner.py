from __future__ import annotations

from dataclasses import dataclass

from .browser import BrowserElement
from .heuristics import intent_keywords, score_click_target


@dataclass(slots=True)
class PlannedCandidate:
    intent: str
    candidate: BrowserElement
    score: int
    source: str


class SemanticPlanner:
    def rank_candidates(
        self,
        candidates: list[BrowserElement],
        intent: str,
        keyword_hints: list[str],
        source: str = "selector",
    ) -> list[PlannedCandidate]:
        ranked = [
            PlannedCandidate(
                intent=intent,
                candidate=item,
                score=score_click_target(
                    item.text,
                    item.href,
                    item.matched_selector,
                    keyword_hints,
                    intent=intent,
                ),
                source=source,
            )
            for item in candidates
        ]
        return sorted(ranked, key=lambda item: item.score, reverse=True)

    def semantic_keywords(self, intent: str) -> list[str]:
        return intent_keywords(intent)

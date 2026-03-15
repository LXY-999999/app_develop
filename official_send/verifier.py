from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .browser import BrowserSnapshot
from .heuristics import classify_job_page


@dataclass(slots=True)
class PageVerification:
    stage: str
    keyword_hits: int
    is_login: bool
    is_job_detail: bool
    is_job_listing: bool
    looks_like_detail_url: bool
    looks_like_listing_url: bool
    search_inputs: int
    job_card_count: int
    apply_count: int
    login_signal_count: int
    listing_signal_count: int
    detail_signal_count: int
    page_title: str
    raw: dict[str, Any]

    def goal_reached(self, goal: str) -> bool:
        if goal == "job_listing":
            return self.is_job_listing
        if goal == "job_detail":
            return self.is_job_detail and self.keyword_hits > 0
        if goal == "login":
            return self.is_login
        return False


class PageVerifier:
    def verify(self, snapshot: BrowserSnapshot, keywords: list[str]) -> PageVerification:
        raw = classify_job_page(
            url=snapshot.url,
            title=snapshot.title,
            page_text=snapshot.page_text,
            elements=snapshot.elements,
            keywords=keywords,
        )
        return PageVerification(
            stage=str(raw["stage"]),
            keyword_hits=int(raw["keyword_hits"]),
            is_login=bool(raw["is_login"]),
            is_job_detail=bool(raw["is_job_detail"]),
            is_job_listing=bool(raw["is_job_listing"]),
            looks_like_detail_url=bool(raw["looks_like_detail_url"]),
            looks_like_listing_url=bool(raw["looks_like_listing_url"]),
            search_inputs=int(raw["search_inputs"]),
            job_card_count=int(raw["job_card_count"]),
            apply_count=int(raw["apply_count"]),
            login_signal_count=int(raw["login_signal_count"]),
            listing_signal_count=int(raw["listing_signal_count"]),
            detail_signal_count=int(raw["detail_signal_count"]),
            page_title=str(raw["page_title"]),
            raw=raw,
        )

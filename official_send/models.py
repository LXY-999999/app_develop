from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class CompanyRunStatus(str, Enum):
    PENDING = "pending"
    SEARCHED = "searched"
    LOGIN_REQUIRED = "login_required"
    LOGGED_IN = "logged_in"
    NO_OFFICIAL_SITE = "no_official_site"
    NO_MATCHING_JOB = "no_matching_job"
    APPLY_SUBMITTED = "apply_submitted"
    AWAITING_USER = "awaiting_user"
    FAILED = "failed"


@dataclass(slots=True)
class CandidateProfile:
    phone: str
    resume_path: str
    name: str = ""
    email: str = ""
    city: str = ""
    school: str = ""
    extra_fields: dict[str, str] = field(default_factory=dict)

    def resolved_resume_path(self) -> Path:
        return Path(self.resume_path).expanduser().resolve()


@dataclass(slots=True)
class OfficialSendRequest:
    companies: list[str]
    job_keywords: list[str]
    candidate: CandidateProfile
    search_engine: str = "bing"
    headless: bool = False
    keep_open: bool = False
    keep_open_seconds: int = 60
    max_search_results: int = 8
    max_recovery_attempts: int = 6
    max_candidate_trials: int = 6
    per_company_timeout_seconds: int = 240
    otp_timeout_seconds: int = 180
    otp_sender_keywords: list[str] = field(default_factory=list)
    otp_body_keywords: list[str] = field(default_factory=lambda: ["验证码", "code", "verify"])


@dataclass(slots=True)
class CompanyRunResult:
    company: str
    status: CompanyRunStatus = CompanyRunStatus.PENDING
    official_url: str = ""
    matched_keyword: str = ""
    message: str = ""
    login_button_box: dict[str, float] | None = None
    artifacts: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def mark(self, status: CompanyRunStatus, message: str = "") -> None:
        self.status = status
        if message:
            self.message = message
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .models import CandidateProfile, OfficialSendRequest
from .workflow import OfficialCampusAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Computer-use style official campus recruitment sender.",
    )
    parser.add_argument("--company", action="append", default=[], help="Repeatable company keyword.")
    parser.add_argument(
        "--job-keyword",
        action="append",
        default=[],
        help="Repeatable job keyword. Example: 多模态",
    )
    parser.add_argument("--phone", required=True, help="Phone number used for login.")
    parser.add_argument("--resume", required=True, help="Path to resume file.")
    parser.add_argument("--name", default="", help="Candidate name.")
    parser.add_argument("--email", default="", help="Candidate email.")
    parser.add_argument("--city", default="", help="Candidate city.")
    parser.add_argument("--school", default="", help="Candidate school.")
    parser.add_argument(
        "--profile-json",
        default="",
        help="Optional JSON file with extra candidate fields.",
    )
    parser.add_argument(
        "--search-engine",
        choices=["bing", "google", "baidu"],
        default="bing",
        help="Search engine used to find official recruitment sites.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode.")
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep visible browser open for inspection before exiting.",
    )
    parser.add_argument(
        "--keep-open-seconds",
        type=int,
        default=60,
        help="How long to keep browser open when --keep-open is set.",
    )
    parser.add_argument("--otp-timeout", type=int, default=180, help="Seconds to wait for OTP.")
    parser.add_argument(
        "--max-recovery-attempts",
        type=int,
        default=6,
        help="How many verify-and-recover loops to try before giving up.",
    )
    parser.add_argument(
        "--max-candidate-trials",
        type=int,
        default=6,
        help="How many ranked page candidates to try when recovering a job detail page.",
    )
    parser.add_argument(
        "--per-company-timeout",
        type=int,
        default=240,
        help="Maximum seconds allowed for a single company before moving on.",
    )
    parser.add_argument(
        "--otp-sender-keyword",
        action="append",
        default=[],
        help="Optional sender keyword filter for iMessage OTP detection.",
    )
    parser.add_argument(
        "--mcp-command",
        default="",
        help="Optional MCP server command line, for example: 'npx @playwright/mcp@latest'.",
    )
    return parser


def load_extra_fields(profile_json: str) -> dict[str, str]:
    if not profile_json:
        return {}
    payload = json.loads(Path(profile_json).read_text(encoding="utf-8"))
    extra_fields = payload.get("extra_fields", payload)
    if not isinstance(extra_fields, dict):
        raise ValueError("profile-json must contain an object")
    return {str(key): str(value) for key, value in extra_fields.items()}


async def _run(args: argparse.Namespace) -> None:
    if not args.company:
        raise ValueError("At least one --company is required.")
    if not args.job_keyword:
        raise ValueError("At least one --job-keyword is required.")

    candidate = CandidateProfile(
        phone=args.phone,
        resume_path=args.resume,
        name=args.name,
        email=args.email,
        city=args.city,
        school=args.school,
        extra_fields=load_extra_fields(args.profile_json),
    )
    request = OfficialSendRequest(
        companies=args.company,
        job_keywords=args.job_keyword,
        candidate=candidate,
        search_engine=args.search_engine,
        headless=args.headless,
        keep_open=args.keep_open,
        keep_open_seconds=args.keep_open_seconds,
        max_recovery_attempts=args.max_recovery_attempts,
        max_candidate_trials=args.max_candidate_trials,
        per_company_timeout_seconds=args.per_company_timeout,
        otp_timeout_seconds=args.otp_timeout,
        otp_sender_keywords=args.otp_sender_keyword,
    )

    mcp_command = [token for token in args.mcp_command.split(" ") if token]
    agent = OfficialCampusAgent(
        base_dir=Path(__file__).resolve().parent,
        mcp_command=mcp_command,
    )
    results = await agent.run(request)
    print(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

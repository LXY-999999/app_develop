from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from .agent import OfficialSendAgentRuntime
from .browser import BrowserAction, BrowserComputerUse
from .heuristics import (
    APPLY_BUTTON_SELECTORS,
    CODE_INPUT_SELECTORS,
    EXPAND_BUTTON_SELECTORS,
    GENERIC_DETAIL_CANDIDATE_SELECTORS,
    JOB_CARD_SELECTORS,
    JOB_SEARCH_BUTTON_SELECTORS,
    JOB_SEARCH_INPUT_SELECTORS,
    LOGIN_BUTTON_SELECTORS,
    LOGIN_SUBMIT_SELECTORS,
    PHONE_INPUT_SELECTORS,
    POSITION_ENTRY_SELECTORS,
    RECOVERY_BUTTON_SELECTORS,
    RESUME_UPLOAD_SELECTORS,
    SEARCH_RESULT_LINK_SELECTORS,
    SEND_CODE_BUTTON_SELECTORS,
    build_company_query,
    build_search_url,
    intent_keywords,
    is_likely_official_result,
    official_site_hints,
)
from .imessage import IMessageCodeWatcher
from .models import CompanyRunResult, CompanyRunStatus, OfficialSendRequest
from .planner import SemanticPlanner
from .recovery import RecoveryPlanner
from .verifier import PageVerification, PageVerifier

logger = logging.getLogger(__name__)


class OfficialCampusAgent:
    def __init__(self, base_dir: Path, mcp_command: list[str] | None = None) -> None:
        self._base_dir = base_dir
        self._artifact_root = base_dir / "artifacts"
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        self._mcp_command = mcp_command or []
        self._runtime: OfficialSendAgentRuntime | None = None
        self._planner = SemanticPlanner()
        self._verifier = PageVerifier()
        self._recovery = RecoveryPlanner()

    async def run(self, request: OfficialSendRequest) -> list[CompanyRunResult]:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_dir = self._artifact_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        watcher = IMessageCodeWatcher()
        results: list[CompanyRunResult] = []

        async with OfficialSendAgentRuntime(self._mcp_command) as runtime:
            self._runtime = runtime
            async with BrowserComputerUse(run_dir, headless=request.headless) as browser:
                runtime.bind_local_tools(browser, watcher)
                for company in request.companies:
                    result = await self._run_single_company(
                        browser=browser,
                        watcher=watcher,
                        request=request,
                        company=company,
                        company_dir=run_dir,
                    )
                    result.extra["tool_calls"] = runtime.history()
                    results.append(result)

                if request.keep_open and not request.headless:
                    logger.info(
                        "keep-open enabled, holding browser for %ss",
                        request.keep_open_seconds,
                    )
                    await self._wait(float(request.keep_open_seconds))

        summary_path = run_dir / "summary.json"
        summary_path.write_text(
            json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return results

    async def _run_single_company(
        self,
        browser: BrowserComputerUse,
        watcher: IMessageCodeWatcher,
        request: OfficialSendRequest,
        company: str,
        company_dir: Path,
    ) -> CompanyRunResult:
        result = CompanyRunResult(company=company)
        logger.info("company-start company=%s", company)

        try:
            async with asyncio.timeout(request.per_company_timeout_seconds):
                return await self._run_single_company_impl(
                    browser=browser,
                    watcher=watcher,
                    request=request,
                    company=company,
                    company_dir=company_dir,
                    result=result,
                )
        except TimeoutError:
            result.mark(
                CompanyRunStatus.AWAITING_USER,
                f"单家公司超时退出，已进入通用恢复上限：{request.per_company_timeout_seconds}s",
            )
            result.extra["final_url"] = await self._current_url()
            logger.warning("company-timeout company=%s timeout=%ss", company, request.per_company_timeout_seconds)
            return result

    async def _run_single_company_impl(
        self,
        browser: BrowserComputerUse,
        watcher: IMessageCodeWatcher,
        request: OfficialSendRequest,
        company: str,
        company_dir: Path,
        result: CompanyRunResult,
    ) -> CompanyRunResult:
        logger.info("company-start-impl company=%s", company)

        query = build_company_query(company)
        search_url = build_search_url(request.search_engine, query)
        await self._navigate(search_url)
        await self._wait(1.5)
        search_snapshot = await self._snapshot(f"{company}_search")
        result.artifacts.append(search_snapshot.screenshot_path)
        result.mark(CompanyRunStatus.SEARCHED, f"已搜索：{query}")

        official_url = await self._resolve_official_url(
            browser,
            company,
            request.max_search_results,
        )
        if not official_url:
            result.mark(CompanyRunStatus.NO_OFFICIAL_SITE, "未找到可信的官网春招入口")
            return result

        result.official_url = official_url
        landing_snapshot = await self._snapshot(f"{company}_landing")
        result.artifacts.append(landing_snapshot.screenshot_path)

        await self._prepare_company_site(browser, company, request.job_keywords)

        matched_keyword = await self._search_jobs(browser, request)
        if not matched_keyword:
            result.mark(CompanyRunStatus.NO_MATCHING_JOB, "没有搜到目标职位关键词")
            return result

        result.matched_keyword = matched_keyword

        login_box = await self._try_login(browser, watcher, request, force=False)
        if login_box is not None:
            result.login_button_box = login_box
            result.mark(CompanyRunStatus.LOGGED_IN, "已执行手机号验证码登录流程")

        applied = await self._apply_resume(browser, request)
        if applied:
            result.mark(CompanyRunStatus.APPLY_SUBMITTED, f"已尝试投递，关键词：{matched_keyword}")
        else:
            result.mark(CompanyRunStatus.AWAITING_USER, "已找到岗位，但未完成最终投递，等待进一步交互")

        final_snapshot = await self._snapshot(f"{company}_final")
        result.artifacts.append(final_snapshot.screenshot_path)
        result.extra["final_url"] = await self._current_url()
        result.extra["request"] = asdict(request.candidate)
        logger.info("company-end company=%s status=%s", company, result.status.value)
        return result

    async def _resolve_official_url(
        self,
        browser: BrowserComputerUse,
        company: str,
        max_search_results: int,
    ) -> str:
        discovered = await self._open_best_official_result(browser, company, max_search_results)
        if discovered:
            return discovered

        hinted = official_site_hints(company)
        if hinted:
            for url in hinted:
                try:
                    logger.info("company=%s try-official-hint url=%s", company, url)
                    await self._navigate(url, timeout_ms=20_000)
                    await self._wait(1.5)
                    current_url = await self._current_url()
                    if urlparse(current_url).netloc:
                        return current_url
                except Exception as exc:
                    logger.warning("company=%s official-hint-failed url=%s err=%s", company, url, exc)

        return ""

    async def _open_best_official_result(
        self,
        browser: BrowserComputerUse,
        company: str,
        max_search_results: int,
    ) -> str:
        assert browser.page is not None
        for selector in SEARCH_RESULT_LINK_SELECTORS:
            links = browser.page.locator(selector)
            count = await links.count()
            if count == 0:
                continue
            for index in range(min(count, max_search_results)):
                link = links.nth(index)
                href = await link.evaluate(
                    """
                    (node) => {
                      const anchor = node.tagName.toLowerCase() === "a"
                        ? node
                        : node.closest("a");
                      return anchor ? anchor.href || "" : "";
                    }
                    """,
                )
                title = (await link.inner_text()).strip()
                if not is_likely_official_result(company, title, href):
                    continue
                logger.info("company=%s search-result-match title=%s href=%s", company, title, href)
                await link.click()
                await self._wait(2.0)
                current_url = await self._current_url()
                hostname = urlparse(current_url).netloc.lower()
                if hostname and "bing.com" not in hostname and "google.com" not in hostname:
                    return current_url
        return ""

    async def _prepare_company_site(
        self,
        browser: BrowserComputerUse,
        company: str,
        job_keywords: list[str],
    ) -> None:
        await self._click_first_visible(
            browser,
            POSITION_ENTRY_SELECTORS,
            intent="position_entry",
            keyword_hints=job_keywords,
            snapshot_label=f"{company}_generic_position_entry_probe",
            min_score=2,
        )

    async def _try_login(
        self,
        browser: BrowserComputerUse,
        watcher: IMessageCodeWatcher,
        request: OfficialSendRequest,
        force: bool,
    ) -> dict[str, float] | None:
        login_button = await browser.find_first_visible(LOGIN_BUTTON_SELECTORS)
        if not login_button:
            return None

        if not force:
            current_url = await self._current_url()
            if "login" not in current_url.lower():
                return None

        box = await login_button.bounding_box()
        await login_button.click()
        await self._wait(1.5)

        phone_input = await browser.find_first_visible(PHONE_INPUT_SELECTORS)
        if phone_input:
            await phone_input.fill(request.candidate.phone)

        send_code_button = await browser.find_first_visible(SEND_CODE_BUTTON_SELECTORS, timeout_ms=2_000)
        wait_since = datetime.now(timezone.utc)
        if send_code_button:
            await send_code_button.click()
            await self._wait(0.8)

        code_input = await browser.find_first_visible(CODE_INPUT_SELECTORS, timeout_ms=2_000)
        if code_input:
            code = await self._wait_for_code(
                timeout_seconds=request.otp_timeout_seconds,
                sender_keywords=request.otp_sender_keywords,
                body_keywords=request.otp_body_keywords,
                since=wait_since,
            )
            await code_input.fill(code)

        submit_button = await browser.find_first_visible(LOGIN_SUBMIT_SELECTORS, timeout_ms=2_000)
        if submit_button:
            await submit_button.click()
            await self._wait(2.0)

        return box or None

    async def _click_first_visible(
        self,
        browser: BrowserComputerUse,
        selectors: list[str],
        intent: str = "generic",
        keyword_hints: list[str] | None = None,
        snapshot_label: str = "probe",
        min_score: int = 1,
        timeout_ms: int = 1_000,
    ) -> bool:
        keyword_hints = keyword_hints or []
        tried_candidates: set[str] = set()
        low_signal_scans = 0
        await self._scroll_to(0, 0)
        for scan_index, (dx, dy) in enumerate(self._scroll_scan_steps()):
            if dx or dy:
                await self._scroll_by(dx=dx, dy=dy)
                await self._wait(0.6)
            _, page_probe = await self._probe_page(
                browser,
                f"{snapshot_label}_{scan_index}",
                keyword_hints,
            )
            candidates = await self._probe_selectors(selectors, max_per_selector=5)
            if not candidates:
                candidates = await self._probe_keywords_for_intent(intent, max_results=12)
            if not candidates:
                candidates = await self._probe_clickables(max_results=40)
            if not candidates:
                locator = await browser.find_first_visible(selectors, timeout_ms=timeout_ms)
                if locator:
                    try:
                        await locator.click()
                        await self._wait(2.0)
                        return True
                    except Exception:
                        continue
                continue

            ranked = self._planner.rank_candidates(candidates, intent, keyword_hints)
            best = ranked[0]
            logger.info(
                "probe-click intent=%s stage=%s scan=%s best_text=%s best_href=%s best_score=%s",
                intent,
                page_probe.stage,
                scan_index,
                best.candidate.text[:80],
                best.candidate.href[:200],
                best.score,
            )
            if best.score < min_score:
                low_signal_scans += 1
                if low_signal_scans >= 2:
                    break
                continue
            low_signal_scans = 0
            for planned in ranked[:5]:
                candidate = planned.candidate
                candidate_key = (
                    candidate.href
                    or f"{candidate.matched_selector}:{candidate.index}:{candidate.text[:80]}"
                )
                if candidate_key in tried_candidates:
                    continue
                tried_candidates.add(candidate_key)
                clicked = await self._click_candidate(browser, candidate)
                if clicked:
                    return True
        return False

    async def _search_jobs(self, browser: BrowserComputerUse, request: OfficialSendRequest) -> str:
        assert browser.page is not None
        keywords = list(request.job_keywords)
        _, initial_probe = await self._probe_page(browser, "job_search_probe_start", keywords)
        if initial_probe.is_job_detail and initial_probe.keyword_hits > 0:
            return keywords[0]

        search_input = await self._ensure_job_search_surface(browser, request)
        if not search_input:
            return ""

        for keyword in keywords:
            logger.info("search-keyword keyword=%s url=%s", keyword, await self._current_url())
            await search_input.fill(keyword)
            search_button = await browser.find_first_visible(JOB_SEARCH_BUTTON_SELECTORS, timeout_ms=800)
            if search_button:
                await search_button.click()
            else:
                await browser.try_press_enter(search_input)
            await self._wait(2.0)
            _, search_probe = await self._probe_page(browser, f"job_search_after_{keyword}", [keyword])
            if search_probe.is_job_detail and search_probe.keyword_hits > 0:
                return keyword
            if await self._open_matching_job(browser, keyword, request):
                return keyword
        return ""

    def _guess_position_urls(self, current_url: str) -> list[str]:
        parsed = urlparse(current_url)
        base_segments = [segment for segment in parsed.path.split("/") if segment]
        path_variants: list[list[str]] = []
        if base_segments and base_segments[-1].lower() in {"home", "index", "main", "landing"}:
            path_variants.append(base_segments[:-1])
        if base_segments and "." in base_segments[-1]:
            path_variants.append(base_segments[:-1])
        path_variants.append(list(base_segments))

        guesses: list[str] = []
        suffix_groups = [
            ["position"],
            ["positions"],
            ["post"],
            ["posts"],
            ["job"],
            ["jobs"],
            ["campus", "position"],
            ["campus", "positions"],
            ["campus", "post"],
            ["campus", "jobs"],
        ]
        for base in path_variants:
            trimmed = list(base)
            if trimmed and trimmed[-1].lower() in {"position", "positions", "post", "posts", "job", "jobs"}:
                trimmed = trimmed[:-1]
            parent = trimmed[:-1] if trimmed else []
            for suffix in suffix_groups:
                candidates = [trimmed + suffix, parent + suffix, suffix]
                for path_segments in candidates:
                    path = "/" + "/".join(segment for segment in path_segments if segment)
                    guesses.append(
                        urlunparse(
                            (
                                parsed.scheme,
                                parsed.netloc,
                                path,
                                "",
                                parsed.query,
                                "",
                            )
                        )
                    )
        ordered: list[str] = []
        for item in guesses:
            if item not in ordered:
                ordered.append(item)
        return ordered

    async def _ensure_job_search_surface(
        self,
        browser: BrowserComputerUse,
        request: OfficialSendRequest,
    ):
        attempts = max(1, request.max_recovery_attempts)
        guessed_tried: set[str] = set()
        for attempt in range(1, attempts + 1):
            _, probe = await self._probe_page(
                browser,
                f"job_search_surface_attempt_{attempt}",
                list(request.job_keywords),
            )
            search_input = await self._find_search_input_with_scroll(browser, attempt)
            if search_input:
                logger.info("job-search-surface-ready attempt=%s stage=%s", attempt, probe.stage)
                return search_input

            if probe.is_login:
                logger.info("job-search-surface-login-block attempt=%s", attempt)
                return None

            current_url = await browser.current_url()
            for guessed in self._guess_position_urls(current_url):
                if guessed in guessed_tried:
                    continue
                guessed_tried.add(guessed)
                try:
                    logger.info("job-search-surface-guess attempt=%s url=%s", attempt, guessed)
                    await self._navigate(guessed, timeout_ms=12_000)
                    await self._wait(1.5)
                    break
                except Exception as exc:
                    logger.warning("job-search-surface-guess-failed url=%s err=%s", guessed, exc)
                    continue

            search_input = await self._find_search_input_with_scroll(browser, attempt)
            if search_input:
                logger.info("job-search-surface-ready-after-guess attempt=%s stage=%s", attempt, probe.stage)
                return search_input

            expanded = await self._run_generic_recovery_actions(browser)
            if expanded:
                continue

            moved = await self._click_first_visible(
                browser,
                POSITION_ENTRY_SELECTORS,
                intent="position_entry",
                keyword_hints=list(request.job_keywords),
                snapshot_label=f"job_search_position_entry_probe_{attempt}",
                min_score=2,
            )
            if moved:
                continue

        return None

    async def _find_search_input_with_scroll(self, browser: BrowserComputerUse, attempt: int):
        await self._scroll_to(0, 0)
        for scan_index, (dx, dy) in enumerate(self._scroll_scan_steps()):
            if dx or dy:
                await self._scroll_by(dx=dx, dy=dy)
                await self._wait(0.4)
            locator = await browser.find_first_visible(JOB_SEARCH_INPUT_SELECTORS, timeout_ms=900)
            if locator:
                logger.info("job-search-input-found attempt=%s scan=%s", attempt, scan_index)
                return locator
        return None

    async def _reach_verified_job_detail(
        self,
        browser: BrowserComputerUse,
        keyword: str,
        request: OfficialSendRequest,
    ) -> bool:
        tried_candidates: set[str] = set()
        attempts = max(1, request.max_recovery_attempts)
        for attempt in range(1, attempts + 1):
            _, probe = await self._probe_page(
                browser,
                f"job_detail_probe_before_{keyword}_{attempt}",
                [keyword],
            )
            if probe.is_job_detail and probe.keyword_hits > 0:
                return True
            if probe.is_login:
                logger.info("job-detail-recovery-login-block keyword=%s attempt=%s", keyword, attempt)
                return False

            if not probe.is_job_listing:
                recovered = await self._run_generic_recovery_actions(browser)
                if recovered:
                    continue
                search_input = await self._ensure_job_search_surface(browser, request)
                if not search_input:
                    continue
                try:
                    await search_input.fill(keyword)
                    search_button = await browser.find_first_visible(
                        JOB_SEARCH_BUTTON_SELECTORS,
                        timeout_ms=800,
                    )
                    if search_button:
                        await search_button.click()
                    else:
                        await browser.try_press_enter(search_input)
                    await self._wait(2.0)
                except Exception as exc:
                    logger.warning("job-detail-recovery-refill-failed keyword=%s err=%s", keyword, exc)
                    continue

            candidates = await self._probe_selectors(JOB_CARD_SELECTORS, max_per_selector=8)
            if not candidates:
                candidates = await self._probe_selectors(
                    GENERIC_DETAIL_CANDIDATE_SELECTORS,
                    max_per_selector=10,
                )
            if not candidates:
                candidates = await self._probe_clickables(max_results=80)
            ranked = self._planner.rank_candidates(candidates, "job_detail", [keyword])

            clicked_any = False
            for planned in ranked[: max(1, request.max_candidate_trials)]:
                candidate = planned.candidate
                candidate_key = (
                    candidate.href
                    or f"{candidate.matched_selector}:{candidate.index}:{candidate.text[:80]}"
                )
                if candidate_key in tried_candidates:
                    continue
                tried_candidates.add(candidate_key)
                score = planned.score
                if score < 2:
                    continue
                clicked_any = True
                logger.info(
                    "job-detail-recovery-click attempt=%s score=%s text=%s href=%s",
                    attempt,
                    score,
                    candidate.text[:80],
                    candidate.href[:200],
                )
                clicked = await self._click_candidate(browser, candidate)
                if not clicked:
                    continue
                _, after_probe = await self._probe_page(
                    browser,
                    f"job_detail_probe_after_{keyword}_{attempt}",
                    [keyword],
                )
                if after_probe.is_job_detail and after_probe.keyword_hits > 0:
                    return True
                if after_probe.is_login:
                    return False

            if not clicked_any:
                fallback_candidates = await self._probe_selectors(
                    GENERIC_DETAIL_CANDIDATE_SELECTORS,
                    max_per_selector=10,
                )
                if not fallback_candidates:
                    fallback_candidates = await self._probe_clickables(max_results=80)
                fallback_ranked = self._planner.rank_candidates(
                    fallback_candidates,
                    "job_detail",
                    [keyword],
                    source="keyword_probe",
                )
                for planned in fallback_ranked[: max(1, request.max_candidate_trials)]:
                    candidate = planned.candidate
                    candidate_key = (
                        candidate.href
                        or f"{candidate.matched_selector}:{candidate.index}:{candidate.text[:80]}"
                    )
                    if candidate_key in tried_candidates:
                        continue
                    score = planned.score
                    if score < 4:
                        continue
                    tried_candidates.add(candidate_key)
                    clicked_any = True
                    logger.info(
                        "job-detail-recovery-fallback-click attempt=%s score=%s text=%s href=%s",
                        attempt,
                        score,
                        candidate.text[:80],
                        candidate.href[:200],
                    )
                    clicked = await self._click_candidate(browser, candidate)
                    if not clicked:
                        continue
                    _, after_probe = await self._probe_page(
                        browser,
                        f"job_detail_probe_after_fallback_{keyword}_{attempt}",
                        [keyword],
                    )
                    if after_probe.is_job_detail and after_probe.keyword_hits > 0:
                        return True
                    if after_probe.is_login:
                        return False

            response_candidates = await self._probe_response_candidates([keyword], max_results=10)
            for candidate in response_candidates:
                href = str(candidate.get("href", ""))
                if not href or href in tried_candidates:
                    continue
                tried_candidates.add(href)
                logger.info(
                    "job-detail-response-candidate attempt=%s href=%s text=%s",
                    attempt,
                    href,
                    str(candidate.get("text", ""))[:120],
                )
                try:
                    await self._navigate(href, timeout_ms=20_000)
                    await self._wait(2.0)
                except Exception as exc:
                    logger.warning("job-detail-response-candidate-failed href=%s err=%s", href, exc)
                    continue
                _, after_probe = await self._probe_page(
                    browser,
                    f"job_detail_probe_after_response_{keyword}_{attempt}",
                    [keyword],
                )
                if after_probe.is_job_detail and after_probe.keyword_hits > 0:
                    return True
                if after_probe.is_login:
                    return False

            if not clicked_any:
                logger.info("job-detail-recovery-no-candidates keyword=%s attempt=%s", keyword, attempt)
                recovered = await self._run_generic_recovery_actions(browser)
                if recovered:
                    continue
                search_input = await self._ensure_job_search_surface(browser, request)
                if not search_input:
                    continue
        return False

    async def _open_matching_job(
        self,
        browser: BrowserComputerUse,
        keyword: str,
        request: OfficialSendRequest,
    ) -> bool:
        assert browser.page is not None
        return await self._reach_verified_job_detail(browser, keyword, request)

    async def _apply_resume(self, browser: BrowserComputerUse, request: OfficialSendRequest) -> bool:
        assert browser.page is not None
        current_url = await self._current_url()
        if "login" in current_url.lower():
            return False

        matched_keywords = list(request.job_keywords)
        _, pre_apply_probe = await self._probe_page(browser, "pre_apply_probe", matched_keywords)
        if not pre_apply_probe.is_job_detail or pre_apply_probe.keyword_hits <= 0:
            logger.info(
                "pre-apply-check-failed stage=%s keyword_hits=%s url=%s",
                pre_apply_probe.stage,
                pre_apply_probe.keyword_hits,
                current_url,
            )
            return False

        file_input = await browser.find_first_visible(RESUME_UPLOAD_SELECTORS, timeout_ms=1_000)
        resume_path = str(request.candidate.resolved_resume_path())
        if file_input and Path(resume_path).exists():
            await file_input.set_input_files(resume_path)
            await self._wait(1.0)

        await self._fill_common_fields(browser, request)

        apply_button = await browser.find_first_visible(APPLY_BUTTON_SELECTORS, timeout_ms=1_500)
        if apply_button:
            await apply_button.click()
            await self._wait(2.0)
            _, post_apply_probe = await self._probe_page(browser, "post_apply_probe", matched_keywords)
            return not post_apply_probe.is_login

        if await self._open_matching_job(browser, matched_keywords[0] if matched_keywords else "", request):
            if "login" in (await self._current_url()).lower():
                return False
            _, detail_probe = await self._probe_page(browser, "pre_apply_after_reopen_probe", matched_keywords)
            if not detail_probe.is_job_detail or detail_probe.keyword_hits <= 0:
                return False
            apply_button = await browser.find_first_visible(APPLY_BUTTON_SELECTORS, timeout_ms=1_500)
            if apply_button:
                await apply_button.click()
                await self._wait(2.0)
                return True
        return False

    async def _fill_common_fields(self, browser: BrowserComputerUse, request: OfficialSendRequest) -> None:
        assert browser.page is not None
        field_map = {
            request.candidate.name: [
                "input[placeholder*='姓名']",
                "input[name*='name']",
                "input[id*='name']",
            ],
            request.candidate.email: [
                "input[placeholder*='邮箱']",
                "input[type='email']",
                "input[name*='email']",
            ],
            request.candidate.phone: [
                "input[placeholder*='手机']",
                "input[placeholder*='手机号']",
                "input[name*='phone']",
            ],
            request.candidate.city: [
                "input[placeholder*='城市']",
                "input[name*='city']",
            ],
            request.candidate.school: [
                "input[placeholder*='学校']",
                "input[name*='school']",
            ],
        }
        for value, selectors in field_map.items():
            if not value:
                continue
            locator = await browser.find_first_visible(selectors, timeout_ms=500)
            if not locator:
                continue
            existing = await locator.input_value()
            if not existing.strip():
                await locator.fill(value)
                await self._wait(0.2)

        for key, value in request.candidate.extra_fields.items():
            if not value:
                continue
            locator = await browser.find_first_visible(
                [
                    f"input[placeholder*='{key}']",
                    f"input[name*='{key}']",
                    f"textarea[placeholder*='{key}']",
                ],
                timeout_ms=400,
            )
            if locator:
                try:
                    await locator.fill(value)
                except Exception:
                    continue

    async def _probe_page(
        self,
        browser: BrowserComputerUse,
        label: str,
        keywords: list[str],
    ) -> tuple[object, dict[str, object]]:
        snapshot = await self._snapshot(label)
        probe = self._verifier.verify(snapshot, keywords)
        logger.info(
            "page-probe label=%s stage=%s keyword_hits=%s apply=%s cards=%s url=%s",
            label,
            probe.stage,
            probe.keyword_hits,
            probe.apply_count,
            probe.job_card_count,
            snapshot.url,
        )
        return snapshot, probe

    def _scroll_scan_steps(self) -> list[tuple[int, int]]:
        return [
            (0, 0),
            (0, 700),
            (0, 700),
            (0, 700),
            (0, -1400),
            (300, 0),
            (-600, 0),
            (300, 0),
        ]

    async def _probe_selectors(
        self,
        selectors: list[str],
        max_per_selector: int = 5,
    ):
        if self._runtime:
            return await self._runtime.call(
                "browser.probe_selectors",
                selectors=selectors,
                max_per_selector=max_per_selector,
            )
        raise RuntimeError("Agent runtime not initialized")

    async def _probe_keywords_for_intent(
        self,
        intent: str,
        max_results: int = 20,
    ):
        keywords = intent_keywords(intent)
        if not keywords:
            return []
        if self._runtime:
            return await self._runtime.call(
                "browser.probe_keywords",
                keywords=keywords,
                max_results=max_results,
            )
        raise RuntimeError("Agent runtime not initialized")

    async def _probe_clickables(
        self,
        max_results: int = 80,
    ):
        if self._runtime:
            return await self._runtime.call(
                "browser.probe_clickables",
                max_results=max_results,
            )
        raise RuntimeError("Agent runtime not initialized")

    async def _probe_response_candidates(
        self,
        keywords: list[str],
        max_results: int = 20,
    ):
        if self._runtime:
            return await self._runtime.call(
                "browser.probe_response_candidates",
                keywords=keywords,
                current_url=await self._current_url(),
                max_results=max_results,
            )
        raise RuntimeError("Agent runtime not initialized")

    async def _run_generic_recovery_actions(self, browser: BrowserComputerUse) -> bool:
        snapshot, verification = await self._probe_page(browser, "generic_recovery_probe", [])
        del snapshot
        selector_map = {
            "expand": EXPAND_BUTTON_SELECTORS,
            "recovery": RECOVERY_BUTTON_SELECTORS,
            "position_entry": POSITION_ENTRY_SELECTORS,
        }
        for step in self._recovery.sequence_for_stage(verification.stage):
            selectors = selector_map.get(step.intent, [])
            clicked = await self._click_first_visible(
                browser,
                selectors,
                intent=step.intent,
                snapshot_label=f"generic_recovery_{step.intent}",
                min_score=1,
            )
            if clicked:
                logger.info("generic-recovery-clicked intent=%s", step.intent)
                return True
        return False

    async def _scroll_by(self, dx: int = 0, dy: int = 0) -> dict[str, int]:
        if self._runtime:
            return await self._runtime.call("browser.scroll_by", dx=dx, dy=dy)
        raise RuntimeError("Agent runtime not initialized")

    async def _scroll_to(self, x: int = 0, y: int = 0) -> dict[str, int]:
        if self._runtime:
            return await self._runtime.call("browser.scroll_to", x=x, y=y)
        raise RuntimeError("Agent runtime not initialized")

    async def _click_candidate(self, browser: BrowserComputerUse, candidate) -> bool:
        assert browser.page is not None
        locator = browser.page.locator(candidate.matched_selector).nth(candidate.index)
        before_url = await self._current_url()
        before_sig = await self._page_signature()
        center_x = max(candidate.x + (candidate.width / 2), 1)
        center_y = max(candidate.y + (candidate.height / 2), 1)
        click_variants = (
            ("native", lambda: locator.click()),
            ("mouse", lambda: browser.page.mouse.click(center_x, center_y)),
            ("force", lambda: locator.click(force=True)),
            ("dispatch", lambda: locator.dispatch_event("click")),
            ("dom", lambda: locator.evaluate("(node) => node.click()")),
        )
        try:
            await locator.scroll_into_view_if_needed()
            for variant_name, click_call in click_variants:
                try:
                    await click_call()
                except Exception as variant_exc:
                    logger.debug(
                        "candidate-click-variant-failed variant=%s selector=%s index=%s err=%s",
                        variant_name,
                        candidate.matched_selector,
                        candidate.index,
                        variant_exc,
                    )
                    continue
                await self._wait(1.2)
                after_url = await self._current_url()
                after_sig = await self._page_signature()
                if after_url != before_url or after_sig != before_sig:
                    return True

            descendant = locator.locator(
                "a,button,[role='button'],[tabindex],h1,h2,h3,h4,[class*='title'],[class*='name']"
            ).first
            try:
                await descendant.click()
                await self._wait(1.2)
                after_url = await self._current_url()
                after_sig = await self._page_signature()
                if after_url != before_url or after_sig != before_sig:
                    return True
            except Exception:
                pass

            if candidate.href and candidate.href.startswith("http"):
                logger.info(
                    "candidate-click-noop-fallback href=%s selector=%s index=%s",
                    candidate.href,
                    candidate.matched_selector,
                    candidate.index,
                )
                await self._navigate(candidate.href, timeout_ms=20_000)
                await self._wait(2.0)
                return True
            return False
        except Exception as exc:
            logger.warning(
                "candidate-click-failed selector=%s index=%s err=%s",
                candidate.matched_selector,
                candidate.index,
                exc,
            )
            if candidate.href and candidate.href.startswith("http"):
                try:
                    logger.info(
                        "candidate-click-error-fallback href=%s selector=%s index=%s",
                        candidate.href,
                        candidate.matched_selector,
                        candidate.index,
                    )
                    await self._navigate(candidate.href, timeout_ms=20_000)
                    await self._wait(2.0)
                    return True
                except Exception as nav_exc:
                    logger.warning(
                        "candidate-fallback-navigate-failed href=%s err=%s",
                        candidate.href,
                        nav_exc,
                    )
            return False

    async def _navigate(self, url: str, timeout_ms: int = 30_000) -> str:
        if self._runtime:
            return await self._runtime.call("browser.navigate", url=url, timeout_ms=timeout_ms)
        raise RuntimeError("Agent runtime not initialized")

    async def _wait(self, seconds: float) -> None:
        if self._runtime:
            await self._runtime.call("browser.wait", seconds=seconds)
            return
        raise RuntimeError("Agent runtime not initialized")

    async def _snapshot(self, label: str):
        if self._runtime:
            return await self._runtime.call("browser.snapshot", label=label)
        raise RuntimeError("Agent runtime not initialized")

    async def _current_url(self) -> str:
        if self._runtime:
            return await self._runtime.call("browser.current_url")
        raise RuntimeError("Agent runtime not initialized")

    async def _page_signature(self) -> str:
        if self._runtime:
            return await self._runtime.call("browser.page_signature")
        raise RuntimeError("Agent runtime not initialized")

    async def _wait_for_code(self, **kwargs: object) -> str:
        if self._runtime:
            return await self._runtime.call("otp.wait_for_code", **kwargs)
        raise RuntimeError("Agent runtime not initialized")

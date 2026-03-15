from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import quote_plus, urlparse

SEARCH_ENGINE_URLS = {
    "bing": "https://www.bing.com/search?q={query}",
    "google": "https://www.google.com/search?q={query}",
    "baidu": "https://www.baidu.com/s?wd={query}",
}

OFFICIAL_SITE_HINTS: dict[str, list[str]] = {
    "字节跳动": [
        "https://jobs.bytedance.com/campus",
    ],
    "腾讯": [
        "https://join.qq.com/",
    ],
    "阿里巴巴": [
        "https://careers-tongyi.alibaba.com/?lang=zh",
        "https://talent.alibaba.com/?lang=zh",
    ],
}

ALIBABA_ENTITY_HINTS: dict[str, list[str]] = {
    "default": ["通义实验室", "千问C端事业群", "阿里云", "阿里巴巴控股集团"],
    "多模态": ["通义实验室", "千问C端事业群", "阿里云"],
    "多模态基模": ["通义实验室", "千问C端事业群"],
    "多模态大模型": ["通义实验室", "千问C端事业群"],
    "大模型": ["通义实验室", "千问C端事业群"],
}

SEARCH_RESULT_LINK_SELECTORS = [
    "li.b_algo h2 a",
    "#b_results a",
    "a h3",
]

LOGIN_BUTTON_KEYWORDS = [
    "登录",
    "登录/注册",
    "注册登录",
    "立即登录",
    "手机号登录",
    "短信登录",
    "验证码登录",
    "账号登录",
    "去登录",
]

SEND_CODE_BUTTON_KEYWORDS = [
    "获取验证码",
    "发送验证码",
    "获取短信验证码",
    "发送短信验证码",
    "获取校验码",
    "发送校验码",
    "重新发送",
]

LOGIN_SUBMIT_KEYWORDS = [
    "登录",
    "立即登录",
    "确认登录",
    "提交",
    "继续登录",
    "完成登录",
]

POSITION_ENTRY_KEYWORDS = [
    "岗位投递",
    "校招职位",
    "校园招聘",
    "校园职位",
    "全部职位",
    "热招职位",
    "查看岗位",
    "查看职位",
    "浏览岗位",
    "浏览职位",
    "职位列表",
    "岗位列表",
    "应届生招聘",
    "实习生招聘",
    "招聘项目",
    "一键投递",
    "立即投递",
    "投递简历",
    "申请职位",
    "应聘职位",
    "加入我们",
    "工作在阿里",
    "工作在京东",
]

POSITION_ENTRY_SUPPORT_KEYWORDS = [
    "人才计划",
    "青云计划",
    "职位",
    "岗位",
    "校招公告",
    "招聘动态",
    "应聘流程",
    "求职攻略",
    "招聘Q&A",
    "了解腾讯",
]

POSITION_ENTRY_NEGATIVE_TOKENS = [
    "登录",
    "注册",
    "求职攻略",
    "招聘动态",
    "公告",
    "Q&A",
    "了解更多",
    "社会招聘",
]

JOB_DETAIL_KEYWORDS = [
    "职位详情",
    "岗位详情",
    "查看详情",
    "查看岗位",
    "查看职位",
    "投递简历",
    "立即投递",
    "申请职位",
    "应聘职位",
    "马上投递",
    "立即申请",
    "一键投递",
]

JOB_DETAIL_SUPPORT_KEYWORDS = [
    "职位描述",
    "岗位职责",
    "任职要求",
    "职位要求",
    "工作地点",
    "所属部门",
    "岗位类别",
    "工作城市",
    "部门介绍",
    "热招职位",
]

JOB_DETAIL_NEGATIVE_TOKENS = [
    "登录",
    "注册",
    "公告",
    "了解更多",
    "招聘动态",
]

APPLY_BUTTON_KEYWORDS = [
    "立即投递",
    "投递简历",
    "申请职位",
    "申请该职位",
    "确认投递",
    "提交申请",
    "马上投递",
    "一键投递",
    "立即申请",
    "应聘职位",
    "应聘",
]

SEARCH_BUTTON_KEYWORDS = [
    "搜索",
    "查询",
    "查找",
    "搜索职位",
    "搜索岗位",
    "查职位",
    "查岗位",
]

EXPAND_BUTTON_KEYWORDS = [
    "查看更多",
    "展开更多",
    "查看全部",
    "全部职位",
    "更多职位",
    "加载更多",
    "更多",
]

RECOVERY_BUTTON_KEYWORDS = [
    "重试",
    "重新加载",
    "刷新",
    "稍后再试",
    "继续",
    "我知道了",
    "确定",
]

BUTTON_KEYWORD_GROUPS: dict[str, list[str]] = {
    "login": LOGIN_BUTTON_KEYWORDS,
    "send_code": SEND_CODE_BUTTON_KEYWORDS,
    "login_submit": LOGIN_SUBMIT_KEYWORDS,
    "position_entry": POSITION_ENTRY_KEYWORDS,
    "job_detail": JOB_DETAIL_KEYWORDS,
    "apply": APPLY_BUTTON_KEYWORDS,
    "search": SEARCH_BUTTON_KEYWORDS,
    "expand": EXPAND_BUTTON_KEYWORDS,
    "recovery": RECOVERY_BUTTON_KEYWORDS,
}


def intent_keywords(intent: str) -> list[str]:
    return list(BUTTON_KEYWORD_GROUPS.get(intent, []))


def _escape_text(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("'", "\\'")


def _build_clickable_text_selectors(keywords: list[str]) -> list[str]:
    selectors: list[str] = []
    clickable_tags = ("button", "a", "[role='button']", "[class*='btn']", "[class*='button']")
    for keyword in keywords:
        escaped = _escape_text(keyword)
        for tag in clickable_tags:
            selectors.append(f"{tag}:has-text('{escaped}')")
        selectors.append(f"text={keyword}")
        selectors.append(f"[title*='{escaped}']")
        selectors.append(f"[aria-label*='{escaped}']")
    return selectors


def _dedupe(items: list[str]) -> list[str]:
    ordered: list[str] = []
    for item in items:
        if item not in ordered:
            ordered.append(item)
    return ordered


LOGIN_BUTTON_SELECTORS = _dedupe(_build_clickable_text_selectors(LOGIN_BUTTON_KEYWORDS))

PHONE_INPUT_SELECTORS = [
    "input[placeholder*='手机']",
    "input[placeholder*='手机号']",
    "input[name*='phone']",
    "input[id*='phone']",
    "input[type='tel']",
]

CODE_INPUT_SELECTORS = [
    "input[placeholder*='验证码']",
    "input[name*='code']",
    "input[id*='code']",
    "input[autocomplete='one-time-code']",
]

SEND_CODE_BUTTON_SELECTORS = _dedupe(_build_clickable_text_selectors(SEND_CODE_BUTTON_KEYWORDS))

LOGIN_SUBMIT_SELECTORS = _dedupe(_build_clickable_text_selectors(LOGIN_SUBMIT_KEYWORDS))

JOB_SEARCH_INPUT_SELECTORS = [
    "input[placeholder*='搜索职位']",
    "input[placeholder*='搜索岗位']",
    "input[placeholder*='搜索']",
    "input[placeholder*='关键字']",
    "input[type='search']",
    "input[name*='keyword']",
]

JOB_SEARCH_BUTTON_SELECTORS = _dedupe(_build_clickable_text_selectors(SEARCH_BUTTON_KEYWORDS))

POSITION_ENTRY_SELECTORS = _dedupe(_build_clickable_text_selectors(POSITION_ENTRY_KEYWORDS) + [
    "a[href*='position']",
    "a[href*='post']",
    "a[href*='job']",
    "a[href*='campus']",
])

JOB_CARD_SELECTORS = _dedupe(_build_clickable_text_selectors(JOB_DETAIL_KEYWORDS + APPLY_BUTTON_KEYWORDS) + [
    "a[href*='/position/']",
    "a[href*='/detail']",
    "a[href*='post_detail']",
    "a[href*='job-detail']",
    "a[href*='/job/']",
    "[class*='job'] a",
    "[class*='position'] a",
    "[class*='post'] a",
])

GENERIC_DETAIL_CANDIDATE_SELECTORS = [
    "a",
    "button",
    "[role='button']",
    "[onclick]",
    "[class*='job']",
    "[class*='position']",
    "[class*='post']",
    "li",
]

RESUME_UPLOAD_SELECTORS = [
    "input[type='file']",
]

APPLY_BUTTON_SELECTORS = _dedupe(_build_clickable_text_selectors(APPLY_BUTTON_KEYWORDS))

EXPAND_BUTTON_SELECTORS = _dedupe(_build_clickable_text_selectors(EXPAND_BUTTON_KEYWORDS))

RECOVERY_BUTTON_SELECTORS = _dedupe(_build_clickable_text_selectors(RECOVERY_BUTTON_KEYWORDS))

COMMON_BLOCKLIST_HOSTS = {
    "zhidao.baidu.com",
    "baike.baidu.com",
    "zhuanlan.zhihu.com",
    "www.zhihu.com",
    "mp.weixin.qq.com",
    "weixin.sogou.com",
}

DETAIL_URL_TOKENS = (
    "/detail",
    "/job/",
    "/jobs/",
    "/position/",
    "post_detail",
    "job-detail",
    "jobdetail",
)

LISTING_URL_TOKENS = (
    "/position",
    "/positions",
    "/post",
    "/posts",
    "/jobs",
    "/campus/post",
    "/campus/position",
)

LOGIN_TEXT_TOKENS = (
    "登录",
    "验证码",
    "手机登录",
    "短信登录",
    "获取验证码",
    "登录/注册",
)

LISTING_TEXT_TOKENS = (
    "搜索职位",
    "搜索岗位",
    "职位列表",
    "岗位列表",
    "筛选",
    "招聘类型",
    "校招职位",
    "在招职位",
    "全部职位",
    "热招职位",
    "岗位投递",
    "应届生招聘",
    "实习生招聘",
    "招聘项目",
    "岗位类别",
    "工作城市",
    "应聘项目",
    "查看岗位",
    "查看职位",
)

DETAIL_TEXT_TOKENS = (
    "职位描述",
    "岗位职责",
    "任职要求",
    "职位要求",
    "工作地点",
    "所属部门",
    "立即投递",
    "投递简历",
    "申请职位",
    "职位详情",
    "岗位详情",
    "查看详情",
)

STRUCTURAL_DETAIL_TOKENS = (
    "职位描述",
    "岗位职责",
    "任职要求",
    "职位要求",
    "所属部门",
    "职位详情",
    "岗位详情",
    "查看详情",
)

APPLY_TEXT_TOKENS = (
    "立即投递",
    "投递简历",
    "申请职位",
    "确认投递",
    "提交申请",
    "一键投递",
    "立即申请",
    "应聘职位",
)

ENTRY_TEXT_TOKENS = (
    "职位",
    "岗位",
    "岗位投递",
    "校园招聘",
    "校招职位",
    "立即投递",
    "全部职位",
    "热招职位",
    "查看岗位",
    "查看职位",
    "应届生招聘",
    "实习生招聘",
    "招聘项目",
    "一键投递",
    "加入我们",
)


def build_search_url(search_engine: str, query: str) -> str:
    template = SEARCH_ENGINE_URLS.get(search_engine, SEARCH_ENGINE_URLS["bing"])
    return template.format(query=quote_plus(query))


def build_company_query(company: str) -> str:
    return f"{company} 春招 官网"


def normalize_company_token(company: str) -> str:
    return re.sub(r"\s+", "", company).lower()


def is_likely_official_result(company: str, title: str, href: str) -> bool:
    if not href.startswith("http"):
        return False
    hostname = urlparse(href).netloc.lower()
    if not hostname or hostname in COMMON_BLOCKLIST_HOSTS:
        return False

    company_token = normalize_company_token(company)
    title_token = normalize_company_token(title)
    positive = 0

    if company_token and company_token in title_token:
        positive += 3
    if company_token and company_token in hostname.replace("-", ""):
        positive += 4
    if any(key in title for key in ("官网", "校园招聘", "校招", "春招", "招聘")):
        positive += 2
    if any(key in hostname for key in ("career", "jobs", "recruit", "zhaopin")):
        positive += 2

    return positive >= 4


def extract_first_code(text: str, preferred_keywords: list[str] | None = None) -> str | None:
    lowered = text.lower()
    if preferred_keywords:
        lowered_keywords = [item.lower() for item in preferred_keywords if item]
        if lowered_keywords and not any(item in lowered for item in lowered_keywords):
            return None
    match = re.search(r"(?<!\d)(\d{4,8})(?!\d)", text)
    return match.group(1) if match else None


def official_site_hints(company: str) -> list[str]:
    for key, urls in OFFICIAL_SITE_HINTS.items():
        if key in company or company in key:
            return urls
    return []


def alibaba_entity_hints(job_keywords: list[str]) -> list[str]:
    ordered: list[str] = []
    for keyword in job_keywords:
        for hint in ALIBABA_ENTITY_HINTS.get(keyword, []):
            if hint not in ordered:
                ordered.append(hint)
    for hint in ALIBABA_ENTITY_HINTS["default"]:
        if hint not in ordered:
            ordered.append(hint)
    return ordered


def keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = normalize_text(text)
    return sum(1 for keyword in keywords if keyword and normalize_text(keyword) in lowered)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def element_blob(element: Any) -> str:
    parts: list[str] = []
    for field in ("text", "href", "selector", "placeholder", "aria_label", "tag", "role"):
        value = getattr(element, field, None)
        if value:
            parts.append(str(value))
    if not parts and isinstance(element, dict):
        for field in ("text", "href", "selector", "placeholder", "aria_label", "tag", "role"):
            value = element.get(field)
            if value:
                parts.append(str(value))
    return " ".join(parts)


def count_matching_elements(elements: Iterable[Any], tokens: tuple[str, ...]) -> int:
    total = 0
    for element in elements:
        blob = element_blob(element)
        if any(token in blob for token in tokens):
            total += 1
    return total


def classify_job_page(
    url: str,
    title: str,
    page_text: str,
    elements: list[Any],
    keywords: list[str],
) -> dict[str, Any]:
    url_lower = url.lower()
    title_lower = title.lower()
    body = page_text[:12000]
    combined = f"{title}\n{body}"

    login_signal_count = sum(1 for token in LOGIN_TEXT_TOKENS if token in combined)
    listing_signal_count = sum(1 for token in LISTING_TEXT_TOKENS if token in combined)
    detail_signal_count = sum(1 for token in DETAIL_TEXT_TOKENS if token in combined)
    structural_detail_count = sum(1 for token in STRUCTURAL_DETAIL_TOKENS if token in combined)

    search_inputs = count_matching_elements(elements, ("搜索", "关键字", "keyword"))
    job_card_count = count_matching_elements(elements, ("/detail", "/job/", "/position/", "投递", "申请"))
    apply_count = count_matching_elements(elements, APPLY_TEXT_TOKENS)
    login_element_count = count_matching_elements(elements, LOGIN_TEXT_TOKENS)
    keyword_hit_count = keyword_hits(combined + "\n" + "\n".join(element_blob(item) for item in elements), keywords)

    is_login = "login" in url_lower or (login_signal_count >= 2 and login_element_count >= 1)
    looks_like_detail_url = any(token in url_lower for token in DETAIL_URL_TOKENS)
    looks_like_listing_url = any(token in url_lower for token in LISTING_URL_TOKENS)

    is_job_detail = (
        looks_like_detail_url
        and (detail_signal_count >= 1 or structural_detail_count >= 1 or apply_count >= 1 or keyword_hit_count >= 1)
    ) or (
        structural_detail_count >= 2
        and (apply_count >= 1 or keyword_hit_count >= 1)
        and search_inputs == 0
        and job_card_count <= 4
    )

    is_job_listing = (
        looks_like_listing_url and (search_inputs >= 1 or job_card_count >= 2 or listing_signal_count >= 1)
    ) or (
        search_inputs >= 1 and (job_card_count >= 1 or listing_signal_count >= 1)
    ) or (
        listing_signal_count >= 2 and job_card_count >= 1
    )

    stage = "landing"
    if is_login:
        stage = "login"
    elif is_job_detail:
        stage = "job_detail"
    elif is_job_listing:
        stage = "job_listing"

    return {
        "stage": stage,
        "keyword_hits": keyword_hit_count,
        "is_login": is_login,
        "is_job_detail": is_job_detail,
        "is_job_listing": is_job_listing,
        "looks_like_detail_url": looks_like_detail_url,
        "looks_like_listing_url": looks_like_listing_url,
        "search_inputs": search_inputs,
        "job_card_count": job_card_count,
        "apply_count": apply_count,
        "login_signal_count": login_signal_count,
        "listing_signal_count": listing_signal_count,
        "detail_signal_count": detail_signal_count,
        "structural_detail_count": structural_detail_count,
        "page_title": title_lower[:200],
    }


def score_click_target(
    text: str,
    href: str,
    selector: str,
    keyword_hints: list[str],
    intent: str,
) -> int:
    blob = normalize_text(" ".join(part for part in (text, href, selector) if part))
    score = 0

    if intent == "position_entry":
        for token in POSITION_ENTRY_KEYWORDS:
            if normalize_text(token) in blob:
                score += 4
        for token in POSITION_ENTRY_SUPPORT_KEYWORDS:
            if normalize_text(token) in blob:
                score += 1
        if any(token in href.lower() for token in LISTING_URL_TOKENS):
            score += 4
        for token in POSITION_ENTRY_NEGATIVE_TOKENS:
            if normalize_text(token) in blob:
                score -= 3
        if "login" in href.lower():
            score -= 6

    if intent == "job_detail":
        for token in JOB_DETAIL_KEYWORDS:
            if normalize_text(token) in blob:
                score += 3
        for token in JOB_DETAIL_SUPPORT_KEYWORDS:
            if normalize_text(token) in blob:
                score += 1
        for token in APPLY_BUTTON_KEYWORDS:
            if normalize_text(token) in blob:
                score += 2
        if any(token in href.lower() for token in DETAIL_URL_TOKENS):
            score += 5
        keyword_score = keyword_hits(blob, keyword_hints)
        score += keyword_score * 4
        for token in JOB_DETAIL_NEGATIVE_TOKENS:
            if normalize_text(token) in blob:
                score -= 3
        if any(token in href.lower() for token in ("login", "register", "signup")):
            score -= 6

    if intent == "expand":
        for token in EXPAND_BUTTON_KEYWORDS:
            if normalize_text(token) in blob:
                score += 3

    if intent == "recovery":
        for token in RECOVERY_BUTTON_KEYWORDS:
            if normalize_text(token) in blob:
                score += 3

    if "javascript:void(0)" in href.lower():
        score -= 1

    return score

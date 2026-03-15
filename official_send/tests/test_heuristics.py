from official_send.heuristics import (
    classify_job_page,
    extract_first_code,
    is_likely_official_result,
    score_click_target,
)


def test_extract_first_code_prefers_keyword_match() -> None:
    text = "【腾讯招聘】您的验证码为 384920，请在 5 分钟内使用。"
    assert extract_first_code(text, ["验证码"]) == "384920"


def test_extract_first_code_returns_none_without_preferred_keyword() -> None:
    text = "订单号 384920 已生成。"
    assert extract_first_code(text, ["验证码"]) is None


def test_is_likely_official_result_accepts_career_site() -> None:
    assert is_likely_official_result(
        "字节跳动",
        "字节跳动校园招聘官网",
        "https://jobs.bytedance.com/campus",
    )


def test_is_likely_official_result_rejects_knowledge_sites() -> None:
    assert not is_likely_official_result(
        "腾讯",
        "腾讯春招介绍",
        "https://baike.baidu.com/item/腾讯",
    )


def test_classify_job_page_marks_listing_page() -> None:
    result = classify_job_page(
        url="https://jobs.bytedance.com/campus/position",
        title="校招职位 - 字节跳动",
        page_text="搜索职位\n职位列表\n筛选\n多模态",
        elements=[
            {"text": "搜索职位", "href": "", "selector": "input[placeholder*='搜索职位']"},
            {"text": "多模态大模型研究员", "href": "/campus/position/123/detail", "selector": "a.job"},
            {"text": "立即投递", "href": "/campus/position/123/detail", "selector": "a.apply"},
        ],
        keywords=["多模态"],
    )
    assert result["is_job_listing"]
    assert not result["is_job_detail"]


def test_classify_job_page_marks_relevant_detail_page() -> None:
    result = classify_job_page(
        url="https://jobs.bytedance.com/campus/position/123/detail",
        title="多模态大模型研究员",
        page_text="职位描述\n岗位职责\n任职要求\n立即投递",
        elements=[
            {"text": "立即投递", "href": "", "selector": "button.apply"},
            {"text": "职位描述", "href": "", "selector": "section.desc"},
        ],
        keywords=["多模态"],
    )
    assert result["is_job_detail"]
    assert result["keyword_hits"] > 0


def test_score_click_target_prefers_detail_candidate() -> None:
    detail_score = score_click_target(
        text="多模态大模型研究员 立即投递",
        href="https://jobs.bytedance.com/campus/position/123/detail",
        selector="a.job",
        keyword_hints=["多模态"],
        intent="job_detail",
    )
    entry_score = score_click_target(
        text="校园招聘",
        href="https://jobs.bytedance.com/campus",
        selector="a.nav",
        keyword_hints=["多模态"],
        intent="job_detail",
    )
    assert detail_score > entry_score

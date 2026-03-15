from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StageToolPolicy:
    stage: str
    goal: str
    tools: list[str]
    success_signal: str
    fallback: str


GENERALIZED_STAGE_TOOL_POLICIES: list[StageToolPolicy] = [
    StageToolPolicy(
        stage="discover_official_site",
        goal="找到可信的官网招聘入口，而不是百科、资讯或聚合页。",
        tools=[
            "browser.navigate",
            "browser.snapshot",
            "browser.current_url",
            "browser.click_selector",
        ],
        success_signal="当前 URL 已进入目标公司官方招聘域名。",
        fallback="如果搜索页不稳定，回退到公司级官方站点 hints 或人工维护的 seed URL。",
    ),
    StageToolPolicy(
        stage="enter_jobs_page",
        goal="从官网首页进入职位列表页、岗位投递页或校园招聘页。",
        tools=[
            "browser.snapshot",
            "browser.find_first_visible",
            "browser.click_selector",
            "browser.current_url",
        ],
        success_signal="页面出现职位搜索框、职位卡片，或 URL 进入 position/post/detail 页面。",
        fallback="优先点“职位 / 岗位投递 / 立即投递 / 校园招聘”，再尝试 /position、/post 等路径猜测。",
    ),
    StageToolPolicy(
        stage="locate_login",
        goal="识别登录入口、手机号输入框、验证码输入框和提交按钮。",
        tools=[
            "browser.snapshot",
            "browser.find_first_visible",
            "browser.current_url",
        ],
        success_signal="找到登录按钮或已进入 login 页面 / login 弹窗。",
        fallback="如果没看到登录入口，先继续搜索岗位，直到点击投递后再触发登录。",
    ),
    StageToolPolicy(
        stage="login_with_sms",
        goal="完成手机号登录和验证码填写。",
        tools=[
            "browser.fill_selector",
            "browser.click_selector",
            "otp.wait_for_code",
            "browser.current_url",
            "browser.snapshot",
        ],
        success_signal="页面登录态变化，或当前 URL 离开 login 页面。",
        fallback="如果验证码控件结构异常，重新 snapshot 后再次定位；如果短信未到，停在当前页等待用户。",
    ),
    StageToolPolicy(
        stage="search_target_job",
        goal="搜索用户输入的职位关键词，并把结果缩到最相关岗位。",
        tools=[
            "browser.find_first_visible",
            "browser.fill_selector",
            "browser.press_key",
            "browser.click_selector",
            "browser.snapshot",
            "browser.page_contains_any_text",
        ],
        success_signal="出现包含关键词的职位卡片或详情页。",
        fallback="如果没有标准搜索框，就从列表页卡片文本里直接扫描关键词并点击最相关卡片。",
    ),
    StageToolPolicy(
        stage="open_job_detail",
        goal="进入具体岗位详情页，而不是停在首页或列表页。",
        tools=[
            "browser.snapshot",
            "browser.click_selector",
            "browser.current_url",
        ],
        success_signal="URL 或页面结构进入 detail / position / post_detail 之类的详情页。",
        fallback="优先点带关键词的岗位卡片；如果没有关键词高亮，就点第一个相关业务线岗位再验证。",
    ),
    StageToolPolicy(
        stage="submit_resume",
        goal="上传简历并点击投递。",
        tools=[
            "browser.find_first_visible",
            "browser.upload_file",
            "browser.fill_selector",
            "browser.click_selector",
            "browser.snapshot",
        ],
        success_signal="出现“已投递 / 投递成功 / 已申请”之类状态，或提交后页面进入个人中心。",
        fallback="如果找不到上传框，就先找“附件简历 / 上传简历 / 选择文件”；如果只有登录拦截，则回到 login_with_sms。",
    ),
    StageToolPolicy(
        stage="escalate_to_user",
        goal="在自动化无法继续时，把当前状态明确交还给用户。",
        tools=[
            "browser.snapshot",
            "browser.current_url",
        ],
        success_signal="返回清楚的卡点描述、当前 URL、截图路径和下一步需要用户提供的信息。",
        fallback="不要瞎点，不要硬猜，停在可恢复状态。",
    ),
]

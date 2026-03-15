# official_send

`official_send` 是一个独立于现有 `jobclaw` 的原型目录，用来实现“春招官网自动投递”的 computer-use agent 流程。

设计上参考了 `openclaw` 的 browser tool 思路，不走“单个大脚本把所有细节写死”，而是拆成两层：

1. 浏览器能力层：`snapshot + act`
2. 业务工作流层：搜索官网 -> 进入官网 -> 登录 -> 搜岗位 -> 投递

## 当前目录结构

- `official_send/browser.py`
  提供 `BrowserComputerUse`，对外暴露 `navigate`、`snapshot`、`act`，接口上模仿 `openclaw` 的 browser action 风格。
- `official_send/workflow.py`
  负责春招官网工作流编排。
- `official_send/imessage.py`
  负责从 macOS `~/Library/Messages/chat.db` 轮询验证码。
- `official_send/heuristics.py`
  放搜索结果筛选、登录按钮/手机号/验证码/职位搜索等通用启发式规则。
- `official_send/cli.py`
  命令行入口。

## 已实现流程

1. 用户输入公司关键词列表，例如 `字节跳动`、`腾讯`、`阿里巴巴`
2. 浏览器自动搜索 `公司名 春招 官网`
3. 自动打开更像官网的搜索结果
4. 截图保存，并尝试定位“登录/注册”类入口
5. 填手机号，点击获取验证码
6. 从 iMessage 轮询验证码并自动填入
7. 用用户输入的职位关键词搜索岗位
8. 命中后尝试上传简历并点击“投递/申请”
9. 如果没搜到岗位，返回 `no_matching_job`

每一步截图都会保存到 `official_send/artifacts/<run_id>/`。

当前还内置了一个通用“验证-恢复”循环：

- 每次点击前先探针页面和候选元素，判断当前是 `landing`、`job_listing`、`job_detail` 还是 `login`
- 每次搜索岗位后都会复核当前页是否真的进入相关岗位详情页
- 如果点击职位卡片没有跳转，但候选元素已经暴露出可信 `href`，会退回到直接导航
- 如果阶段不对，会继续尝试通用恢复动作，例如重找职位入口、重找搜索框、重试高分候选卡片

也就是说，后续像 `小米` 这种新站点，优先增加的是中间检测和恢复逻辑，而不是先写站点特化。

## 运行方式

```bash
python -m official_send.cli \
  --company 字节跳动 \
  --company 腾讯 \
  --job-keyword 多模态 \
  --job-keyword 多模态大模型 \
  --phone 13800000000 \
  --resume /absolute/path/to/resume.pdf \
  --name 张三 \
  --email zhangsan@example.com \
  --max-recovery-attempts 6 \
  --max-candidate-trials 6
```

如果你还有更多简历字段需要自动填，可以准备一个 JSON：

```json
{
  "extra_fields": {
    "专业": "计算机科学与技术",
    "学历": "硕士"
  }
}
```

然后运行：

```bash
python -m official_send.cli \
  --company 阿里巴巴 \
  --job-keyword 多模态 \
  --phone 13800000000 \
  --resume /absolute/path/to/resume.pdf \
  --profile-json /absolute/path/to/profile.json
```

## 和 openclaw 的对应关系

`openclaw` 里浏览器能力的核心抽象是：

- `profile`
- `action`
- `snapshot`
- `act`

这里暂时没有照搬它完整的 Gateway / node / relay 体系，而是保留了同样的核心控制模型：

- `BrowserComputerUse.navigate(url)`
- `BrowserComputerUse.snapshot(label)`
- `BrowserComputerUse.act(BrowserAction(...))`

也就是说，这个原型先把 computer-use 的“观察-动作”环打通，后面如果你要接更强的 VLM planner，或者再加站点级 adapter，会比较自然。

## 当前限制

1. 官网页面差异很大，所以现在是“通用启发式 + 验证恢复循环 + best effort”，不是每家公司都能 100% 直接投成功。
2. `iMessage` 自动读验证码需要 Terminal / Python 对 Messages 数据库有访问权限。
3. 某些站点的登录、简历投递是多页表单，后续更适合按公司做 adapter。
4. 搜索引擎默认是 `bing`，因为对自动化相对稳定；如果你要严格用百度或 Google，可以通过 `--search-engine` 切换。

## 下一步建议

如果你要继续做成稳定可用版本，优先顺序应该是：

1. 继续强化通用检测和恢复策略，而不是优先加更多站点特化
2. 加入“人工接管”模式：找不到按钮时直接把截图和当前 URL 返回
3. 把投递历史持久化，避免重复投
4. 把通用 planner 升级成真正的 VLM-based planner

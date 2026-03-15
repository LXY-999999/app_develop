from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecoveryStep:
    intent: str
    description: str


class RecoveryPlanner:
    def sequence_for_stage(self, stage: str) -> list[RecoveryStep]:
        common = [
            RecoveryStep("expand", "先展开更多内容或更多职位。"),
            RecoveryStep("recovery", "处理刷新、重试、继续等阻断按钮。"),
            RecoveryStep("position_entry", "重新寻找职位入口或岗位入口。"),
        ]
        if stage == "landing":
            return common
        if stage == "job_listing":
            return [
                RecoveryStep("expand", "尝试展开列表、查看更多或加载更多。"),
                RecoveryStep("recovery", "处理页面上的继续/刷新/重试提示。"),
            ]
        return common

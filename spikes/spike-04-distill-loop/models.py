"""Structured claim schema extracted by Instructor (Pydantic-constrained)."""
from typing import Literal

from pydantic import BaseModel, Field


class ClaimDraft(BaseModel):
    """Distillation output contract: meta-cognition claim, NOT a summary."""

    statement: str = Field(
        description="一句话元认知陈述（方法论/原则/权衡），不是对原文的摘要",
    )
    level: Literal["principle", "pattern", "antipattern", "tradeoff"] = Field(
        description="claim 层级：原理/模式/反模式/权衡",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="对该陈述的置信度 0~1")
    topic: str = Field(description="所属主题标签（用于 topic 组织与反向连接）")
    reasoning: str = Field(description="为什么从这些来源能得出该陈述（供人审参考）")

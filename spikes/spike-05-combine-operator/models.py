"""Structured modeling artifact contract (Instructor-constrained, citation-bound)."""
from typing import Literal

from pydantic import BaseModel, Field


class ArtifactClaim(BaseModel):
    statement: str = Field(description="该建模产物下的一条结构化断言")
    level: Literal["principle", "pattern", "antipattern", "tradeoff"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(
        description="支撑该断言的来源条目 id（必须来自给定来源集合）",
    )


class ModelingArtifact(BaseModel):
    """结合算子产物：带引用的结构化建模产物，不是摘要堆砌。"""

    title: str = Field(description="产物标题（一句话命名该模型/方法论）")
    kind: Literal["methodology", "mental_model", "tradeoff_map"]
    claims: list[ArtifactClaim] = Field(min_length=1, description="1 条以上带引用断言")
    local: list[str] = Field(
        default_factory=list,
        description="local 层：各来源实体级要点（可空；空层是蒸馏不足的质量信号）",
    )
    global_insights: list[str] = Field(
        default_factory=list,
        alias="global",
        description="global 层：跨来源关系链/更高维模式（可空；空层是质量信号）",
    )
    methodology_steps: list[str] = Field(
        default_factory=list,
        description="若 kind=methodology：可执行步骤序列",
    )

    model_config = {"populate_by_name": True}

"""Spike 10: a resilient structured-output client (fixes the spike 05 retry defect).

THE DEFECT (recorded in spike 05, not silently accepted):
    "模型稳定漏填 required local 字段，Instructor 重试 4 次不补（prompt 线性膨胀）"

Two separate problems were bundled in that sentence:
  1. PROMPT GROWTH: Instructor's built-in retry appends the failed assistant message and
     a full validation error to the message list, so every retry is strictly longer than
     the last. A small model gets buried under its own failure history — the reason it
     "never recovers" may be the growing context, not its capability.
  2. ERROR NOISE: the retry hint is a raw Pydantic dump (full JSON, all errors, long
     `input` echoes). It is unreadable to a small model and eats the context.

THE FIX: own the retry loop.
  - `max_retries=0` on Instructor (it must not append anything);
  - every attempt rebuilds `messages` from scratch: original prompt + ONE short,
     bounded correction hint. Length is CONSTANT across attempts, by construction;
  - the hint names only the offending fields (max HINT_MAX_ERRORS, each truncated).

This module is model-agnostic: it takes any Instructor-wrapped client, so the same
retry policy is applied to the 1.5B baseline and to the new target model — otherwise the
comparison would conflate "new model" with "new retry policy".
"""
from __future__ import annotations

from dataclasses import dataclass, field

HINT_MAX_ERRORS = 3
HINT_ERROR_CHARS = 80


@dataclass
class AttemptTrace:
    attempt: int
    prompt_chars: int
    ok: bool
    error: str | None = None


@dataclass
class RetryReport:
    attempts: list[AttemptTrace] = field(default_factory=list)

    @property
    def n_attempts(self) -> int:
        return len(self.attempts)

    @property
    def succeeded(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].ok

    @property
    def prompt_lengths(self) -> list[int]:
        return [a.prompt_chars for a in self.attempts]

    @property
    def prompt_growth(self) -> int:
        """Total character growth across attempts. 0 == no linear inflation."""
        ls = self.prompt_lengths
        return max(ls) - min(ls) if ls else 0


def condense_error(exc: Exception) -> str:
    """Turn a validation failure into a short, bounded, model-readable hint."""
    errors = getattr(exc, "errors", None)
    try:
        raw = errors() if callable(errors) else None
    except Exception:  # noqa: BLE001 - a broken error object must not break the retry
        raw = None
    parts: list[str] = []
    if raw:
        for e in raw[:HINT_MAX_ERRORS]:
            loc = ".".join(str(x) for x in (e.get("loc") or ()))
            msg = str(e.get("msg") or e.get("type") or "invalid")
            parts.append(f"{loc}: {msg}"[:HINT_ERROR_CHARS])
    else:
        parts.append(str(exc)[:HINT_ERROR_CHARS * HINT_MAX_ERRORS])
    return "；".join(parts)


def _build_messages(prompt: str, system: str | None, attempt: int,
                    last_error: str | None) -> list[dict]:
    """Rebuild from scratch every time — never append to a growing history."""
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    if attempt == 0 or not last_error:
        msgs.append({"role": "user", "content": prompt})
    else:
        hint = (f"上一次输出未通过结构校验（{last_error}）。"
                f"请重新输出完整对象，补全所有必填字段，不要省略任何层级。")
        msgs.append({"role": "user", "content": f"{prompt}\n\n{hint}"})
    return msgs


def resilient_create(client, model: str, response_model, prompt: str, *,
                     system: str | None = None, temperature: float = 0.2,
                     max_attempts: int = 3, extra_body: dict | None = None):
    """Structured extraction with a non-inflating retry policy.

    Returns (object, RetryReport). Raises the last exception if all attempts fail.
    """
    report = RetryReport()
    last_error: str | None = None
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        messages = _build_messages(prompt, system, attempt, last_error)
        prompt_chars = sum(len(m["content"]) for m in messages)
        try:
            kwargs = dict(
                model=model,
                response_model=response_model,
                messages=messages,
                temperature=temperature,
                max_retries=0,          # Instructor must NOT append anything itself
            )
            if extra_body:
                kwargs["extra_body"] = extra_body
            obj = client.chat.completions.create(**kwargs)
            report.attempts.append(AttemptTrace(attempt, prompt_chars, True))
            return obj, report
        except Exception as exc:  # noqa: BLE001 - retry on any validation/API failure
            last_exc = exc
            last_error = condense_error(exc)
            report.attempts.append(AttemptTrace(attempt, prompt_chars, False, last_error))

    raise last_exc  # type: ignore[misc]

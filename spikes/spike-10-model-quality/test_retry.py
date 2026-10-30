"""Tests for the retry-policy fix — no model required (stub client).

These tests encode the spike 05 defect directly: if anyone reintroduces Instructor's
appending retry, `test_prompt_does_not_grow_across_attempts` fails.
"""
import unittest

from pydantic import BaseModel, Field, ValidationError

from llm_client import (
    resilient_create, condense_error, RetryReport, HINT_ERROR_CHARS, HINT_MAX_ERRORS,
)


class _Stub(BaseModel):
    title: str = Field(description="t")
    local: list[str] = Field(min_length=1, description="must not be empty")
    nested: dict = Field(description="nested object")


class _FakeCompletions:
    """Fails `fail_times` times with a realistic Pydantic error, then succeeds."""

    def __init__(self, fail_times: int = 2):
        self.fail_times = fail_times
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self.fail_times:
            raise ValidationError.from_exception_data(
                "Stub",
                [
                    {"type": "missing", "loc": ("local",), "msg": "Field required",
                     "input": {}},
                    {"type": "missing", "loc": ("nested", "a"), "msg": "Field required",
                     "input": {}},
                    {"type": "missing", "loc": ("nested", "b"), "msg": "Field required",
                     "input": {}},
                    {"type": "missing", "loc": ("nested", "c"), "msg": "Field required",
                     "input": {}},
                ],
            )
        return _Stub(title="ok", local=["x"], nested={"a": 1})


class _FakeClient:
    def __init__(self, fail_times: int = 2):
        self.chat = _FakeChat(self, fail_times)


class _FakeChat:
    def __init__(self, owner, fail_times):
        self.completions = _FakeCompletions(fail_times)
        owner.completions = self.completions


class TestRetryPolicy(unittest.TestCase):
    def _client(self, fail_times=2):
        return _FakeClient(fail_times)

    def test_recovers_after_validation_failures(self):
        c = self._client(fail_times=2)
        obj, rep = resilient_create(c, "stub", _Stub, "prompt", max_attempts=3)
        self.assertEqual(obj.title, "ok")
        self.assertEqual(rep.n_attempts, 3)
        self.assertTrue(rep.succeeded)

    def test_prompt_does_not_grow_across_attempts(self):
        """THE regression test for spike 05: no linear prompt inflation."""
        c = self._client(fail_times=4)
        _, rep = resilient_create(c, "stub", _Stub, "x" * 500, max_attempts=5)
        self.assertGreater(rep.n_attempts, 1)
        # attempt 0 is the bare prompt; later attempts add ONE bounded hint only.
        self.assertLessEqual(rep.prompt_growth, 200)
        # and crucially: each message list is rebuilt, never appended to
        for call in c.completions.calls:
            self.assertEqual(len(call["messages"]), 1)

    def test_instructor_retry_is_disabled(self):
        c = self._client(fail_times=0)
        resilient_create(c, "stub", _Stub, "p")
        self.assertEqual(c.completions.calls[0]["max_retries"], 0)

    def test_error_hint_is_bounded(self):
        c = self._client(fail_times=1)
        _, rep = resilient_create(c, "stub", _Stub, "p", max_attempts=2)
        hint = rep.attempts[0].error
        self.assertIsNotNone(hint)
        self.assertLessEqual(len(hint), HINT_ERROR_CHARS * HINT_MAX_ERRORS + 10)
        self.assertIn("local", hint)
        self.assertNotIn("input", hint)      # raw Pydantic echo must not leak in

    def test_condense_error_handles_plain_exceptions(self):
        self.assertLessEqual(len(condense_error(RuntimeError("x" * 500))),
                             HINT_ERROR_CHARS * HINT_MAX_ERRORS + 10)

    def test_all_attempts_exhausted_raises(self):
        c = self._client(fail_times=99)
        with self.assertRaises(ValidationError):
            resilient_create(c, "stub", _Stub, "p", max_attempts=2)

    def test_system_prompt_is_preserved_and_not_duplicated(self):
        c = self._client(fail_times=1)
        resilient_create(c, "stub", _Stub, "p", system="SYS", max_attempts=2)
        for call in c.completions.calls:
            self.assertEqual(call["messages"][0]["role"], "system")
            self.assertEqual(call["messages"][0]["content"], "SYS")

    def test_empty_report_is_safe(self):
        rep = RetryReport()
        self.assertEqual(rep.prompt_growth, 0)
        self.assertFalse(rep.succeeded)
        self.assertEqual(rep.n_attempts, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

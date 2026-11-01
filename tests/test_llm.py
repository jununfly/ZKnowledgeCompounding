"""zkc/llm 单测（1-5-6）：真实 Ollama 接线的三条铁律编码为测试。

不依赖真实 Ollama：patch urllib.request.urlopen 捕获请求体，验证 payload 构造。
铁律（1-5-2 dogfood 定位 + spike-10 记录）：
  ① 只走原生 /api/chat + format:"json"，绝不用 /v1+response_format（qwen3.5-mlx 挂死）；
  ② 每次调用 think=False + num_ctx=8192（防 256K 默认加载爬行）；
  ③ num_predict 显式给足（默认截断腰斩 JSON）。
"""
from __future__ import annotations

import io
import json
import unittest
import urllib.request
from unittest import mock

from zkc import tuning
from zkc.llm import (
    DEFAULT_NUM_CTX, ollama_chat, ollama_reachable, make_distill_llm,
)


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class OllamaChatPayloadTest(unittest.TestCase):
    def _capture(self, **kwargs):
        """拦截 urlopen，返回 (捕获的 payload dict, ollama_chat 返回文本)。"""
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["payload"] = json.loads(req.data.decode())
            return _FakeResp(b'{"message": {"content": "{\\"ok\\": true}"}}')

        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            out = ollama_chat("http://localhost:11434/", "m1", "PROMPT", **kwargs)
        return captured, out

    def test_native_chat_endpoint_with_json_format(self):
        captured, out = self._capture()
        self.assertEqual(captured["url"], "http://localhost:11434/api/chat")
        self.assertEqual(captured["payload"]["format"], "json")
        self.assertEqual(out, '{"ok": true}')

    def test_think_false_and_num_ctx_pinned(self):
        captured, _ = self._capture()
        self.assertIs(captured["payload"]["think"], False)
        self.assertEqual(captured["payload"]["options"]["num_ctx"], DEFAULT_NUM_CTX)
        self.assertEqual(DEFAULT_NUM_CTX, 8192)  # 铁律②定值

    def test_num_predict_explicit_from_tuning(self):
        captured, _ = self._capture()
        self.assertEqual(captured["payload"]["options"]["num_predict"],
                         int(tuning.get("DISTILL_NUM_PREDICT")))
        captured, _ = self._capture(num_predict=2048)
        self.assertEqual(captured["payload"]["options"]["num_predict"], 2048)

    def test_json_mode_off_drops_format(self):
        captured, _ = self._capture(json_mode=False)
        self.assertNotIn("format", captured["payload"])

    def test_stream_false_and_single_user_message(self):
        captured, _ = self._capture()
        self.assertIs(captured["payload"]["stream"], False)
        self.assertEqual(captured["payload"]["messages"],
                         [{"role": "user", "content": "PROMPT"}])


class MakeDistillLLMTest(unittest.TestCase):
    def test_factory_returns_llm_seam_with_model_name(self):
        llm = make_distill_llm("http://x:1", "m-test")
        self.assertEqual(getattr(llm, "model_name", None), "m-test")

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode())
            return _FakeResp(b'{"message": {"content": "{}"}}')

        captured = {}
        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            raw = llm("hi")
        self.assertEqual(raw, "{}")
        self.assertEqual(captured["payload"]["model"], "m-test")
        self.assertEqual(captured["payload"]["format"], "json")
        self.assertIs(captured["payload"]["think"], False)

    def test_reachable_false_on_error(self):
        def boom(req, timeout=None):
            raise OSError("down")

        with mock.patch.object(urllib.request, "urlopen", boom):
            self.assertFalse(ollama_reachable("http://x:1"))


if __name__ == "__main__":
    unittest.main()

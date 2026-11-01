"""ZKC · encoder（P5.1 切片A）测试。

不依赖真实 Ollama：批量/维度校验/错误路径全部用 monkeypatch / fake HTTP 验证。
真实连通性由 dogfood 脚本覆盖（切片C）。
"""
from __future__ import annotations

import json
import unittest
import urllib.error
from unittest import mock

from zkc import encoder as E
from zkc import tuning


class EncodeTextsTest(unittest.TestCase):
    def test_empty_input_no_call(self):
        with mock.patch.object(E, "_OPENER") as op:
            self.assertEqual(E.encode_texts([]), [])
            op.open.assert_not_called()

    def test_ok_batch_returns_float_vectors(self):
        dim = int(tuning.get("EMBEDDING_DIM"))
        fake = [0.0] * (dim - 1) + [1.0]
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(
            {"embeddings": [fake, [1.0] + [0.0] * (dim - 1)]}
        ).encode()
        resp.__enter__.return_value = resp
        with mock.patch.object(E, "_OPENER") as op:
            op.open.return_value = resp
            out = E.encode_texts(["a", "b"])
        self.assertEqual(len(out), 2)
        self.assertEqual(len(out[0]), dim)
        self.assertIsInstance(out[0][0], float)
        # 请求打到 /api/embed 且 body 带 model/input
        req = op.open.call_args[0][0]
        self.assertTrue(req.full_url.endswith("/api/embed"))
        body = json.loads(req.data.decode())
        self.assertEqual(body["input"], ["a", "b"])
        self.assertEqual(body["model"], tuning.get("EMBEDDING_MODEL"))

    def test_dim_mismatch_raises(self):
        with mock.patch.object(E, "_OPENER") as op:
            resp = mock.MagicMock()
            resp.read.return_value = json.dumps({"embeddings": [[0.1, 0.2]]}).encode()
            resp.__enter__.return_value = resp
            op.open.return_value = resp
            with self.assertRaises(E.EncoderError) as ctx:
                E.encode_texts(["a"])
            self.assertIn("维度不符", str(ctx.exception))

    def test_count_mismatch_raises(self):
        with mock.patch.object(E, "_OPENER") as op:
            resp = mock.MagicMock()
            resp.read.return_value = json.dumps({"embeddings": []}).encode()
            resp.__enter__.return_value = resp
            op.open.return_value = resp
            with self.assertRaises(E.EncoderError):
                E.encode_texts(["a"])

    def test_network_error_wrapped(self):
        with mock.patch.object(E, "_OPENER") as op:
            op.open.side_effect = urllib.error.URLError("conn refused")
            with self.assertRaises(E.EncoderError) as ctx:
                E.encode_texts(["a"])
            self.assertIn("embed 调用失败", str(ctx.exception))

    def test_make_encoder_uses_default_model_and_attr(self):
        seen = {}

        def fake_encode(texts, *, url, model, timeout, dim=None):
            seen["model"] = model
            seen["dim"] = dim
            return [[0.0] * int(tuning.get("EMBEDDING_DIM")) for _ in texts]

        with mock.patch.object(E, "encode_texts", side_effect=fake_encode):
            enc = E.make_encoder()
            out = enc(["x"])
        self.assertIsNone(seen["model"])  # None = 延迟到 encode_texts 内部按 tuning 解析
        self.assertIsNone(seen["dim"])
        self.assertEqual(len(out), 1)
        self.assertEqual(enc.model_name, tuning.get("EMBEDDING_MODEL"))

    def test_dim_override_validates_against_explicit_dim(self):
        # 1-8-4-1：dim 覆写（4096 列）按显式维度校验，不再绑定 768
        with mock.patch.object(E, "_OPENER") as op:
            resp = mock.MagicMock()
            resp.read.return_value = json.dumps(
                {"embeddings": [[0.5] * 4096]}).encode()
            resp.__enter__.return_value = resp
            op.open.return_value = resp
            out = E.encode_texts(["a"], dim=4096)
        self.assertEqual(len(out[0]), 4096)
        # 维度不符仍按显式值拒绝
        with mock.patch.object(E, "_OPENER") as op2:
            resp2 = mock.MagicMock()
            resp2.read.return_value = json.dumps(
                {"embeddings": [[0.5] * 4096]}).encode()
            resp2.__enter__.return_value = resp2
            op2.open.return_value = resp2
            with self.assertRaises(E.EncoderError) as ctx:
                E.encode_texts(["a"], dim=1024)
            self.assertIn("维度不符", str(ctx.exception))

    def test_make_encoder_4096_uses_4096_tuning(self):
        seen = {}

        def fake_encode(texts, *, url, model, timeout, dim=None):
            seen["model"] = model
            seen["dim"] = dim
            return [[0.0] * int(dim or 768) for _ in texts]

        with mock.patch.object(E, "encode_texts", side_effect=fake_encode):
            enc = E.make_encoder_4096()
            out = enc(["x"])
        self.assertEqual(seen["model"], tuning.get("EMBEDDING_4096_MODEL"))
        self.assertEqual(seen["dim"], int(tuning.get("EMBEDDING_4096_DIM")))
        self.assertEqual(len(out), 1)
        self.assertEqual(enc.model_name, tuning.get("EMBEDDING_4096_MODEL"))


if __name__ == "__main__":
    unittest.main()

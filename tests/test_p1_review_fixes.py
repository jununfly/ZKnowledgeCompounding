"""P1 review 修复 guard（TDD，Red→Green）。

锁住两处低风险硬伤的契约：
- #1 protocols.NodeRepository.update_decay / set_interval 必须暴露 version_seq 默认参数，
  与 0003 迁移「严格 OCC 保留给这两个方法的显式 version_seq」不变量一致（R19 已关，
  但 OCC 入口不得被协议层堵死）。
- #3 list_due_for_review 的 docstring 不得写死裸阈值 0.6，须引用 tuning.SURFACE_THRESHOLD
  （P1.4 铁律「禁裸数字 + 来源标签」在契约注释层同样适用）。

测试经公共接口（协议 ABC 签名 / docstring）验证，非实现细节。
"""

import inspect
import unittest

from zkc.repository.protocols import NodeRepository


class ProtocolsVersionSeqContract(unittest.TestCase):
    def test_update_decay_signature_carries_version_seq(self):
        sig = inspect.signature(NodeRepository.update_decay)
        self.assertIn("version_seq", sig.parameters)
        self.assertIsNone(sig.parameters["version_seq"].default)

    def test_set_interval_signature_carries_version_seq(self):
        sig = inspect.signature(NodeRepository.set_interval)
        self.assertIn("version_seq", sig.parameters)
        self.assertIsNone(sig.parameters["version_seq"].default)


class ProtocolsDocstringNoBareThreshold(unittest.TestCase):
    def test_list_due_for_review_docstring_no_bare_threshold(self):
        doc = NodeRepository.list_due_for_review.__doc__ or ""
        self.assertNotIn("0.6", doc)
        self.assertIn("SURFACE_THRESHOLD", doc)


if __name__ == "__main__":
    unittest.main()

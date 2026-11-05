"""ZKC · MCP 业务适配层（transport seam 的调用方）。

- `exposure.py` 攻击面枚举表（可机读，与契约快照一致）
- `capture.py`  `zkc_capture` push 命令层（过分流闸）
- `handlers.py` 五白名单 tool 的 handler 工厂
- `wiring.py`   composition root：把 handler 注入 `zkc.transport.McpServer`

正式入口：`python -m zkc.transport`（由 wiring 构造完整 server）。
"""
from __future__ import annotations

from .wiring import build_zkc_server

__all__ = ["build_zkc_server"]

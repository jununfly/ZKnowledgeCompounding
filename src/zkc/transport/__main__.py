"""MCP stdio 入口：`python -m zkc.transport`。

MCP client 配置示例（command / args）：
    {"command": "python", "args": ["-m", "zkc.transport"]}

零网络监听面；stdout 只写 JSON-RPC 帧，日志一律走 stderr。
"""
from __future__ import annotations

import sys

from .mcp_server import build_server  # noqa: F401  (transport 骨架工厂，协议层自测仍用)
from .stdio import serve_stdio


def main() -> int:
    # composition root：正式入口注入五个白名单 tool；transport 包自身仍是纯协议层。
    from zkc.mcp.wiring import build_zkc_server

    print("zkc-mcp stdio server ready (no network listener)", file=sys.stderr, flush=True)
    # serve_stdio 返回「已处理帧数」，那是计数不是进程状态；正常结束必须回 0。
    serve_stdio(build_zkc_server())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""ZKC · MCP stdio 事件循环（唯一 I/O 面）。

stdout **只**承载 JSON-RPC 帧；任何诊断/日志必须走 stderr，否则会污染
client 的帧解析。空行跳过、通知不回帧、EOF 正常退出。
"""
from __future__ import annotations

import sys
from typing import Any, Optional, TextIO

from .protocol import decode_message, encode_message, error_response
from .protocol import JsonRpcError


def serve_stdio(server: Any, *, stdin: Optional[TextIO] = None,
                stdout: Optional[TextIO] = None) -> int:
    """逐行读帧 → 分发 → 逐行写帧；返回已处理的请求帧数。"""
    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout
    handled = 0
    for raw_line in in_stream:
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue
        try:
            message = decode_message(line)
        except JsonRpcError as exc:
            response = error_response(None, exc.code, exc.message, exc.data)
        else:
            response = server.handle_message(message)
        if response is None:
            continue
        out_stream.write(encode_message(response) + "\n")
        out_stream.flush()
        handled += 1
    return handled


__all__ = ["serve_stdio"]

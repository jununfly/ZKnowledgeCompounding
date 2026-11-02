"""启动 ZKC 本地 web（localhost:8000）。用法：python -m zkc.web

遵循 ADR-0001：本地 web 应用，不做打包/分发。Ollama 默认 localhost:11434；
ZKC_LLM_ENABLED=0 可显式走离线（词法单信号 / 弃权）。词法语料见 ZKC_LEXICAL_CORPUS。
"""
from __future__ import annotations

import uvicorn

from zkc.web.app import create_app

app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)

"""ZKC · 任务队列 web 路由（1-9）。

挂到同一 FastAPI app（与 /review 同 store）。提供：
- GET  /review/api/tasks         → task_queue_view（当日任务卡片数据）
- POST /review/api/tasks/complete → complete_task（勾选完成）

纯函数逻辑在 zkc.task_queue（可脱离 web 栈单测）。UI 卡片渲染在 review.py 的 REVIEW_HTML。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from zkc.repository.protocols import Storage
from zkc.task_queue import complete_task, task_queue_view


def register_taskqueue_routes(app, store: Storage) -> None:
    """把任务队列路由挂到已有 FastAPI app（create_app 调用）。store 注入以便脱离 PG 单测。"""
    router = APIRouter()

    @router.get("/review/api/tasks")
    def tasks_api() -> dict:
        return task_queue_view(store)

    @router.post("/review/api/tasks/complete")
    def complete_api(task_id: str = Form(...)) -> dict:
        return complete_task(store, task_id)

    app.include_router(router)

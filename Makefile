# ZKC Makefile — 本地开发入口
# 测试、服务、冷启动 dogfood 回归统一收口，避免每个人记不同的命令。

PY ?= python

.PHONY: help setup db migrate verify test serve dogfood dogfood-seed dogfood-drive

help:
	@echo "ZKC targets:"
	@echo "  make setup          安装 Python 依赖（requirements.txt）+ 本包 editable 安装（src 布局）"
	@echo "  make db             确保 Postgres 容器（zkc-spike-pg, :55433）在跑"
	@echo "  make migrate        应用全部待执行 schema 迁移"
	@echo "  make verify         校验已应用迁移 sha256 与磁盘一致"
	@echo "  make test           运行全量单测套件"
	@echo "  make serve          启动 web 服务（127.0.0.1:8000，PG 后端）"
	@echo "  make dogfood        冷启动验证：播种 + 驱动复审/收口，独立 PG 直查两锚落库"
	@echo "                      需先另开终端 make serve（drive 打 localhost:8000）"
	@echo "  make dogfood-seed   仅播种 4 条到期待复审节点（直写 PG，无需服务）"
	@echo "  make dogfood-drive  仅驱动复审标注 + 每日收口并验证（需服务在跑）"

test:
	$(PY) -m unittest discover -s tests

setup:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e .

db:
	@docker inspect -f '{{.State.Running}}' zkc-spike-pg 2>/dev/null | grep -q true \
		|| docker start zkc-spike-pg >/dev/null 2>&1 \
		|| (echo "容器不存在，首次请执行："; echo "  docker run -d --name zkc-spike-pg -p 55433:5432 -e POSTGRES_PASSWORD=zkc -e POSTGRES_USER=postgres -e POSTGRES_DB=zkc_dev pgvector/pgvector:pg16"; exit 1)
	@echo "zkc-spike-pg 已在运行 (:55433)"

migrate:
	$(PY) -m zkc.migrate upgrade

verify:
	$(PY) -m zkc.migrate verify

serve:
	$(PY) -m zkc.web

dogfood-seed:
	$(PY) scripts/dogfood_review_seed.py

dogfood-drive:
	$(PY) scripts/dogfood_review_drive.py

dogfood: dogfood-seed dogfood-drive

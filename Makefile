# ZKC Makefile — 本地开发入口
# 测试、服务、冷启动 dogfood 回归统一收口，避免每个人记不同的命令。

PY ?= python

.PHONY: help test serve dogfood dogfood-seed dogfood-drive

help:
	@echo "ZKC targets:"
	@echo "  make test           运行全量单测套件（tests/ 下 172+ 项）"
	@echo "  make serve          启动 web 服务（127.0.0.1:8000，PG 后端）"
	@echo "  make dogfood        冷启动验证：播种 + 驱动复审/收口，独立 PG 直查两锚落库"
	@echo "                      需先另开终端 make serve（drive 打 localhost:8000）"
	@echo "  make dogfood-seed   仅播种 4 条到期待复审节点（直写 PG，无需服务）"
	@echo "  make dogfood-drive  仅驱动复审标注 + 每日收口并验证（需服务在跑）"

test:
	$(PY) -m unittest discover -s tests

serve:
	$(PY) -m zkc.web

dogfood-seed:
	$(PY) scripts/dogfood_review_seed.py

dogfood-drive:
	$(PY) scripts/dogfood_review_drive.py

dogfood: dogfood-seed dogfood-drive

SHELL := /bin/bash
PY ?= python3
BACKEND_DIR := backend
FRONTEND_DIR := frontend

.PHONY: help setup setup-backend setup-frontend model mock dev api web build test clean

help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: setup-backend setup-frontend ## 安装前后端依赖

setup-backend: ## 创建 Python 虚拟环境并安装后端依赖
	cd $(BACKEND_DIR) && $(PY) -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt

setup-frontend: ## 安装前端依赖
	cd $(FRONTEND_DIR) && npm install

model: ## 克隆 CosyVoice 并下载默认模型权重
	bash scripts/setup_cosyvoice.sh

mock: ## 以 Mock 模式启动后端（无需 GPU / 模型权重）
	cd $(BACKEND_DIR) && CV_MOCK=true .venv/bin/uvicorn app.main:app --reload --port 8000

api: ## 启动后端
	cd $(BACKEND_DIR) && .venv/bin/uvicorn app.main:app --reload --port 8000

web: ## 启动前端开发服务器
	cd $(FRONTEND_DIR) && npm run dev

build: ## 构建前端生产包
	cd $(FRONTEND_DIR) && npm run build

test: ## 运行后端测试
	cd $(BACKEND_DIR) && .venv/bin/pytest -q

clean: ## 清理构建产物与缓存
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules/.vite
	find $(BACKEND_DIR) -type d -name __pycache__ -prune -exec rm -rf {} +

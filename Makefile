.PHONY: setup smoke scout-smoke

export UV_CACHE_DIR := $(CURDIR)/.cache/uv
export XDG_CACHE_HOME := $(CURDIR)/.runtime/cache
export XDG_DATA_HOME := $(CURDIR)/.runtime/data

setup:
	uv sync --locked

smoke:
	uv run inspect eval evals/smoke.py --model mockllm/model --log-dir logs/smoke

scout-smoke:
	uv run scout scan scout.yaml

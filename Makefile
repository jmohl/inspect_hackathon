.PHONY: setup smoke scout-smoke hle-smoke hle scout-hle

export UV_CACHE_DIR := $(CURDIR)/.cache/uv
export XDG_CACHE_HOME := $(CURDIR)/.runtime/cache
export XDG_DATA_HOME := $(CURDIR)/.runtime/data

# XDG_CACHE_HOME above also moves Hugging Face's cache, so a `make` run and a
# bare `uv run inspect eval` would each keep their own copy of the 274MB HLE
# parquet. Pin HF to its usual shared location so both agree and it downloads once.
export HF_HOME := $(HOME)/.cache/huggingface

# Model under test for the HLE targets. Override per-run, e.g.
#   make hle-smoke MODEL=openrouter/openai/gpt-5-mini
MODEL ?= openrouter/anthropic/claude-sonnet-5

setup:
	uv sync --locked

smoke:
	uv run inspect eval evals/smoke.py --model mockllm/model --log-dir logs/smoke

scout-smoke:
	uv run scout scan scout.yaml

# Cheapest end-to-end check of the HLE wiring: 5 text-only questions, one judge
# instead of the default two. Still downloads the full dataset on first run.
hle-smoke:
	uv run inspect eval inspect_evals/hle --model $(MODEL) \
		--limit 5 -T graders=grader -T include_multi_modal=false \
		--log-dir logs/hle

# Full 2,500-question run with HLE's default two-judge scoring.
hle:
	uv run inspect eval inspect_evals/hle --model $(MODEL) --log-dir logs/hle

# Scan HLE transcripts with the scanners in scout.yaml, without repointing it.
scout-hle:
	uv run scout scan scout.yaml --transcripts logs/hle

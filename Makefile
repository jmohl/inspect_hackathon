.PHONY: setup hle-smoke hle hle-200 scout-hle-failures

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

# Models compared by `hle-200`, run sequentially against configs/hle-200.yaml.
HLE_200_MODELS ?= openrouter/openai/gpt-5.6-luna \
                  openrouter/openai/gpt-5-mini \
                  openrouter/openai/gpt-4o

setup:
	uv sync --locked

# Cheapest end-to-end check of the HLE wiring: 5 text-only questions, one judge
# instead of the default two. Still downloads the full dataset on first run.
hle-smoke:
	uv run inspect eval inspect_evals/hle --model $(MODEL) \
		--limit 5 -T graders=grader -T include_multi_modal=false \
		--log-dir logs/hle

# Full 2,500-question run with HLE's default two-judge scoring.
hle:
	uv run inspect eval inspect_evals/hle --model $(MODEL) --log-dir logs/hle

# Three-model comparison on a seeded 200-question text-only subset, single
# judge. All settings live in configs/hle-200.yaml; only the model varies, so
# every model sees the same 200 questions.
hle-200:
	@for m in $(HLE_200_MODELS); do \
		echo "=== HLE-200: $$m ==="; \
		uv run inspect eval --run-config configs/hle-200.yaml \
			--model $$m --log-dir logs/hle-200 || exit 1; \
	done

# Categorise why each incorrect HLE attempt failed, using the taxonomy in
# label_descriptions.md. This calls a judge model once per failed sample, so
# start with a small SCAN_LIMIT before scanning all of them:
#   make scout-hle-failures SCAN_LIMIT=10
#   make scout-hle-failures SCAN_MODEL=openrouter/openai/gpt-5-mini
scout-hle-failures:
	uv run scout scan scout.yaml \
		$(if $(SCAN_MODEL),--model $(SCAN_MODEL),) \
		$(if $(SCAN_LIMIT),--limit $(SCAN_LIMIT),)

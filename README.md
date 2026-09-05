# Inspect hackathon

Minimal [`uv`](https://docs.astral.sh/uv/) environment for running
[Inspect Evals](https://github.com/UKGovernmentBEIS/inspect_evals) and
[Inspect Scout](https://github.com/meridianlabs-ai/inspect_scout). The versions
match the working setup in `LabBench2_audit` and are locked for reproducibility.

## Set up

Install `uv`, then run:

```bash
uv sync --locked
```

This creates `.venv`. Commands can be run with `uv run` without activating it,
or activate it in the usual way:

```bash
source .venv/bin/activate
```

For a real model, copy `.env.example` to `.env` and add the key for the model
provider you use. `.env` is ignored by Git.

## Verify Inspect

The included smoke eval uses Inspect's mock model name and a deterministic local
solver, so it needs no API key, model call, or network access after setup:

```bash
make smoke
```

The Make targets keep uv caches, Inspect traces, and Scout bookkeeping in the
ignored `.cache/` and `.runtime/` directories.

Run a project eval by replacing `evals/smoke.py` and the model, for example:

```bash
uv run inspect eval evals/my_eval.py --model openai/gpt-5-mini
```

or if using OpenRouter:

```bash
uv run inspect eval inspect_evals/hle --model openrouter/openai/gpt-5-mini 
```

Installed Inspect Evals tasks can be addressed through their package paths:

```bash
uv run inspect eval inspect_evals/hellaswag \
  --model openai/gpt-5-mini \
  --limit 10
```

Consult each task's README for its arguments, dataset access, and sandbox needs.

## Humanity's Last Exam (HLE)

[HLE](https://inspect.aisi.org.uk/evals/#/eval/hle) is installed as part of
Inspect Evals and is addressed directly as `inspect_evals/hle` — no wrapper task
file is needed. It needs two credentials in `.env`:

- `OPENROUTER_API_KEY` — for the model under test *and* for the two default
  judges (`google/gemma-4-31b-it` and `google/gemini-3.6-flash`), which run
  through OpenRouter regardless of which model is being evaluated.
- `HF_TOKEN` — the `cais/hle` dataset is gated. Accept the terms at
  <https://huggingface.co/datasets/cais/hle> while logged in, then put a read
  token in `.env`.

Use `HF_TOKEN` in `.env` rather than `huggingface-cli login`: the Make targets
set `XDG_CACHE_HOME`, so a token written to `~/.cache/huggingface/token` would
not be found under `make`. For the same reason the Makefile pins `HF_HOME` back
to `~/.cache/huggingface`, so `make` and a bare `uv run` share one copy of the
274MB dataset instead of downloading it twice.

Cheapest end-to-end check — 5 text-only questions, one judge instead of two:

```bash
make hle-smoke
```

The full 2,500-question run with the default two-judge scoring:

```bash
make hle
```

Both accept a `MODEL` override:

```bash
make hle-smoke MODEL=openrouter/openai/gpt-5-mini
```

### Config-driven runs

[`configs/hle-200.yaml`](configs/hle-200.yaml) defines a 200-question,
text-only, single-judge run so the settings live in version control rather than
in shell history:

```bash
uv run inspect eval --run-config configs/hle-200.yaml \
    --model openrouter/openai/gpt-5-mini --log-dir logs/hle-200
```

To compare the three models in sequence against that one config:

```bash
make hle-200
```

The config has no `model:` field on purpose. Inspect accepts exactly one model
per run config, and multi-model runs need repeated `--model-spec`, which cannot
be combined with a run-config `model` field — so the model is supplied per-run
and everything else stays shared. Upstream's own HLE run configs omit `model`
for the same reason. CLI flags override the file, so
`--limit 1` is a quick way to test the config before committing to 200.

The config sets `sample_shuffle: 42` rather than taking `--limit 200` alone.
The first 200 questions in dataset order are skewed — 34% Math, 19% Computer
Science/AI, 1% Chemistry, against a true 45% / 10% / 5% — so an unshuffled
slice would not represent "all task types". The fixed seed draws a
representative 200 and gives every model and every rerun the same 200
questions.

### Reading the results

- `original_accuracy` is the official HLE convention (counts unparseable
  judgments as incorrect). `score/accuracy` excludes them, so the two differ
  whenever `unscored` > 0.
- `cerr` is **not** comparable with the leaderboard's Calibration Error — the
  official implementation drops the top-confidence bin, roughly halving it.
- Each judge is a separate score column (`llm_grader`, `llm_grader1`); they are
  never voted or averaged against each other, and each one multiplies judging
  cost. `-T graders=grader` runs a single judge.

For reasoning models, keep the completion budget at or above 8192 tokens —
below that, reasoning consumes the budget and the visible answer comes back
empty. Other useful task args: `-T include_multi_modal=false` for the 2,158
text-only questions, `-T category=Math` to subset, and
`-T judge_prompt=grade_c_i` if a judge cannot do JSON-schema structured output.

## Verify Scout

After `make smoke` has written a transcript under `logs/smoke/`, run the included
non-LLM scanner:

```bash
make scout-smoke
```

Edit `scout.yaml` to point `transcripts` at other `.eval` files or log
directories and add scanners from `scanners.py`. To scan the HLE transcripts
without repointing the config, override the source on the command line:

```bash
make scout-hle
```
 For an LLM-backed scanner,
also set `model` in `scout.yaml` (or pass `--model`) and provide its API key.

Useful commands:

```bash
uv run inspect --version
uv run scout --version
uv run scout scan scout.yaml --dry-run
uv run scout view --scans scans
```

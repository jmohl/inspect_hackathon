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

Installed Inspect Evals tasks can be addressed through their package paths;
consult the task's README for its arguments, dataset access, and sandbox needs.

## Verify Scout

After `make smoke` has written a transcript under `logs/smoke/`, run the included
non-LLM scanner:

```bash
make scout-smoke
```

Edit `scout.yaml` to point `transcripts` at other `.eval` files or log
directories and add scanners from `scanners.py`. For an LLM-backed scanner,
also set `model` in `scout.yaml` (or pass `--model`) and provide its API key.

Useful commands:

```bash
uv run inspect --version
uv run scout --version
uv run scout scan scout.yaml --dry-run
uv run scout view --scans scans
```

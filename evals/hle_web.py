"""HLE with a Tavily-backed web_search tool added to the solver.

inspect_evals.hle.hle() hardcodes solver=[generate()] with no tool-use hook
(HLE is meant to be closed-book), so this task reuses its dataset, judge, and
epoch reducer directly and only replaces the solver. Scores from this task
are NOT comparable to the official closed-book HLE leaderboard or to plain
inspect_evals/hle runs -- letting the model search changes what's being
measured.
"""

from typing import Literal

from inspect_ai import Epochs, Task, task
from inspect_ai.model import GenerateConfig
from inspect_ai.solver import generate, use_tools
from inspect_ai.tool import web_search
from inspect_evals.hle.hle import get_hle_dataset
from inspect_evals.hle.judge import llm_grader
from inspect_evals.hle.metrics import attempt_preserving_mean
from inspect_evals.hle.run_config import default_run_config


def _normalize_filters(filters: str | list[str] | None) -> list[str]:
    if filters is None:
        return []
    return filters if isinstance(filters, list) else [filters]


# Defaults match configs/hle-200.yaml / configs/hle-web-200.yaml, not
# inspect_evals.hle's own DEFAULT_TASK_ARGS (which differ: multi-modal
# included, two graders). These configs always pass task.args explicitly and
# override these anyway, but keeping the defaults aligned means a bare
# `inspect eval evals/hle_web.py` also matches the configs' 200-question run.
@task
def hle_web(
    include_multi_modal: bool = False,
    category: str | list[str] | None = None,
    subject: str | list[str] | None = None,
    judge_prompt: Literal["original", "grade_c_i"] = "original",
    max_grader_attempts: int = 3,
    only_hle_verified_gold: bool = False,
    rolling: bool = False,
    graders: str | list[str] | None = "grader",
) -> Task:
    grader_roles = _normalize_filters(graders)
    return Task(
        dataset=get_hle_dataset(
            include_multi_modal=include_multi_modal,
            categories=_normalize_filters(category),
            subjects=_normalize_filters(subject),
            only_hle_verified_gold=only_hle_verified_gold,
            rolling=rolling,
        ),
        solver=[use_tools(web_search("tavily")), generate()],
        scorer=[
            llm_grader(
                judge_prompt=judge_prompt,
                max_grader_attempts=max_grader_attempts,
                grader_role=role,
            )
            for role in grader_roles
        ],
        config=GenerateConfig(**default_run_config().get("generate_config", {})),
        epochs=Epochs(1, attempt_preserving_mean()),
    )

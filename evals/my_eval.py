"""A short Inspect eval that exercises real model generation end-to-end."""

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import match
from inspect_ai.solver import generate, system_message


SYSTEM_PROMPT = (
    "Answer with only the final answer. Do not explain your reasoning."
)


@task
def my_eval() -> Task:
    return Task(
        dataset=[
            Sample(
                input="What is the capital of France?",
                target="Paris",
            ),
            Sample(
                input="What is 12 + 30?",
                target="42",
            ),
            Sample(
                input="What planet is known as the Red Planet?",
                target="Mars",
            ),
        ],
        solver=[
            system_message(SYSTEM_PROMPT),
            generate(),
        ],
        scorer=match(),
    )
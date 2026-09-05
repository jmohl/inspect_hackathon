"""A tiny, offline Inspect eval used to verify the local installation."""

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageAssistant, ModelOutput
from inspect_ai.scorer import match
from inspect_ai.solver import Generate, Solver, TaskState, solver


RESPONSE = "Inspect smoke test passed."


@solver
def offline_response() -> Solver:
    """Produce a transcript without making a model or tokenizer request."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state.messages.append(ChatMessageAssistant(content=RESPONSE))
        state.output = ModelOutput.from_content(
            model="mockllm/model",
            content=RESPONSE,
        )
        return state

    return solve


@task
def smoke() -> Task:
    return Task(
        dataset=[
            Sample(
                input="Run the local Inspect smoke test.",
                target=RESPONSE,
            )
        ],
        solver=[offline_response()],
        scorer=match(),
    )

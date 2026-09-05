"""Inspect Scout scanners for this workspace.

`hle_failure_mode` is the main one: it categorises *why* a failed Humanity's
Last Exam attempt failed, using the taxonomy in `label_descriptions.md`.
`hle_failure_signals` is its free, model-free counterpart — it reports only the
deterministic termination evidence, and is useful for triage and for sanity
checking the LLM scanner's `resource_limit` / `tool_or_environment_failure`
calls.
"""

import sys
from pathlib import Path
from typing import Literal, get_args

# Scout loads scanner files by path, so this file's directory is not
# necessarily on sys.path when `scanner_utils` is imported below.
sys.path.insert(0, str(Path(__file__).parent))

from inspect_scout import (
    AnswerStructured,
    Result,
    Scanner,
    Transcript,
    llm_scanner,
    scanner,
)
from pydantic import BaseModel, Field

from scanner_utils import (
    get_author_rationale,
    get_execution_signals,
    get_failure_signals,
    get_grader_record,
    get_question_metadata,
    get_reference_answer,
    get_system_messages,
    get_task_result,
    get_termination_context,
    get_tool_interactions,
)

FailureCategory = Literal[
    "judge_failure",
    "incorrect_reference_answer",
    "tool_or_environment_failure",
    "resource_limit",
    "answer_format_failure",
    "ambiguous_or_defective_prompt",
    "reasoning_failure",
    "knowledge_failure",
    "undetermined",
]

FAILURE_CATEGORIES: tuple[str, ...] = get_args(FailureCategory)


# --------------------------------------------------------- failure mode -----

# Taxonomy text tracks label_descriptions.md; keep the two in sync when the
# label set changes.
FAILURE_TAXONOMY = """\
- **judge_failure**: The model provides an acceptable answer, but the evaluator
  incorrectly marks it wrong despite a valid reference answer. Examples include
  rejecting equivalent expressions or valid alternative answers.
- **incorrect_reference_answer**: The benchmark's reference answer is factually
  or mathematically incorrect, or excludes other demonstrably valid answers.
  Identify evidence that the reference is defective; disagreement with the model
  alone is insufficient.
- **tool_or_environment_failure**: A malfunctioning or unavailable tool,
  inaccessible resource, or execution-environment problem prevents successful
  completion. Excludes model errors in selecting or using a functioning tool.
- **resource_limit**: An enforced token, time, context, or tool-call limit
  prevents completion. Require evidence that the limit was reached and
  materially affected the attempt.
- **answer_format_failure**: The model provides the substantively correct answer
  but fails to follow an explicit output-format requirement, causing rejection
  or extraction failure.
- **ambiguous_or_defective_prompt**: Ambiguity, missing information,
  contradictory requirements, or faulty premises prevent a uniquely defensible
  answer or support the model's alternative interpretation.
- **reasoning_failure**: The model makes an identifiable error in inference,
  calculation, planning, or applying available information. Identify the
  erroneous step and how it contributes to the incorrect answer.
- **knowledge_failure**: The model lacks, misrecalls, or fabricates a fact,
  definition, or domain-specific rule needed to solve the task. Identify the
  specific knowledge gap or factual error.
- **undetermined**: No specific cause is supported by the record.
"""

FAILURE_MODE_PROMPT = f"""\
## Task

A model attempted a benchmark question and was graded incorrect. Determine the
failure mode: the most directly supported explanation for why the attempt did
not score as correct. Use the transcript above together with the record below.

## Categories

{FAILURE_TAXONOMY}

## How to decide

Work through the record in this order, because the earlier causes make the
later ones unnecessary:

1. **Did the attempt terminate abnormally?** Check the execution signals for a
   fired limit, a truncated output, or a tool/environment error. A limit or
   tool failure only counts when the evidence shows it was reached *and* that
   it materially affected the attempt — a model that answered fully and simply
   answered wrong is not a `resource_limit`.
2. **Was the answer actually wrong?** Compare the model's substantive answer
   against the reference answer, and check the answer the judge extracted.
   - Right answer, wrongly extracted or wrongly rejected → `judge_failure`
     (rejected despite matching) or `answer_format_failure` (the model broke an
     explicit output-format requirement, so the answer could not be extracted
     or matched). Prefer `answer_format_failure` when the prompt stated a
     format and the response did not follow it; prefer `judge_failure` when the
     response did follow it and the judge still rejected an equivalent answer.
   - Right answer under a different but demonstrably valid reading of the
     question → `incorrect_reference_answer` or `ambiguous_or_defective_prompt`.
3. **Is the question itself sound?** Use the author's rationale as evidence.
   A rationale that is self-contradictory, that derives a different value than
   the stated reference answer, or that rules out answers that are in fact
   valid, is evidence for `incorrect_reference_answer`. A question missing
   information needed to pin down a unique answer is
   `ambiguous_or_defective_prompt`.
4. **Otherwise the model failed on the merits.** Separate the two:
   `reasoning_failure` when you can point to the erroneous inference,
   calculation, or planning step; `knowledge_failure` when the model lacked,
   misrecalled, or fabricated a needed fact, definition, or domain rule.

## Evidential standard

Cite evidence from the record. Disagreement between the model and the reference
answer is not by itself evidence that the reference is defective. Do not infer
`reasoning_failure` or `knowledge_failure` solely from an incorrect final
answer — you must be able to name the erroneous step or the specific missing
fact. If the response is too abbreviated or too redacted to locate either,
report `undetermined`.

Assign the single most directly supported primary category, and list secondary
categories only where the record independently supports them.
"""


class FailureModeAnswer(BaseModel):
    """Structured verdict for a single failed attempt."""

    explanation: str = Field(
        description=(
            "Your reasoning, in a few sentences: what the model answered, what "
            "the reference answer was, and why that gap is best explained by "
            "the category you chose. Cite message ids (e.g. '[M2]') for claims "
            "about the transcript."
        )
    )
    evidence: str = Field(
        description=(
            "The specific evidence supporting the primary category — the "
            "erroneous reasoning step, the missing fact, the judge's extracted "
            "answer, the defect in the author's rationale, or the execution "
            "signal. Quote it. Write 'none' if no specific evidence exists."
        )
    )
    primary_category: FailureCategory = Field(
        alias="value",
        description=(
            "The single most directly supported failure category. Use "
            "'undetermined' if the record does not support a specific cause."
        ),
    )
    secondary_categories: list[FailureCategory] = Field(
        description=(
            "Additional categories independently supported by the record, most "
            "supported first. Empty list when only the primary category "
            "applies. Never repeat the primary category."
        )
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "Confidence in the primary category: 'high' when the record names "
            "the cause directly, 'medium' when it is the best of several "
            "readings, 'low' when the record is thin."
        )
    )


@scanner(messages="all", events=["model", "score", "error"])
def hle_failure_mode() -> Scanner[Transcript]:
    """Categorise why a failed HLE attempt failed.

    Passing attempts short-circuit to `not_applicable` without a model call, so
    the scanner is safe to point at a whole log; filtering to incorrect samples
    in the scan config just avoids writing the extra rows.
    """

    async def scan(transcript: Transcript) -> Result:
        result = get_task_result(transcript)
        if result != "FAILED":
            return Result(
                value="not_applicable",
                explanation=f"Task result is {result}; only failures are categorised.",
            )

        # Build the grading record from the full transcript — the events carry
        # stop reasons and the judge's raw output — but hand `llm_scanner` a
        # copy with the events removed. When events are attached it renders
        # `{{ messages }}` from a timeline built out of them, which leaves user
        # content as unresolved `attachment://` references and (without span
        # events to mark the scorers span) can substitute the grader's own
        # model call for the attempt's response.
        question = await _build_question(transcript)
        judge = llm_scanner(
            question=question,
            answer=AnswerStructured(type=FailureModeAnswer),
        )
        return await judge(  # type: ignore[return-value]
            transcript.model_copy(update={"events": [], "timelines": []})
        )

    return scan


async def _build_question(transcript: Transcript) -> str:
    """Assemble the grading record that accompanies the rendered transcript.

    The transcript itself is rendered into the prompt by `llm_scanner`, so this
    adds only what is *not* in the message thread: the system prompt (which the
    default preprocessor strips), the dataset's reference answer and rationale,
    the judge's verdict, and the deterministic execution signals.
    """
    sections = [
        FAILURE_MODE_PROMPT,
        f"--- SYSTEM PROMPT (output format requirements) ---\n{get_system_messages(transcript)}\n",
        f"--- QUESTION METADATA ---\n{get_question_metadata(transcript)}\n",
        f"--- REFERENCE ANSWER ---\n{get_reference_answer(transcript)}\n",
        f"--- AUTHOR RATIONALE FOR REFERENCE ANSWER ---\n{get_author_rationale(transcript)}\n",
        f"--- GRADER RECORD ---\n{get_grader_record(transcript)}\n",
        f"--- EXECUTION SIGNALS ---\n{get_execution_signals(transcript)}\n",
        f"--- TASK RESULT ---\n{get_task_result(transcript)}\n",
    ]

    tools = get_tool_interactions(transcript)
    if tools != "(no tool interactions found)":
        sections.insert(-1, f"--- TOOL INTERACTIONS ---\n{tools}\n")

    return "\n".join(sections)


# ------------------------------------------------------ deterministic ------


@scanner(messages="all", events=["model", "score", "error"])
def hle_failure_signals() -> Scanner[Transcript]:
    """Report deterministic termination evidence without calling a model.

    The value is a comma-separated list of signal names (or `none`), so the
    results frame can be joined against `hle_failure_mode` to check that the
    LLM's `resource_limit` and `tool_or_environment_failure` verdicts are
    backed by an actual limit or tool error.
    """

    async def scan(transcript: Transcript) -> Result:
        signals = get_failure_signals(transcript)
        return Result(
            value=",".join(signals) if signals else "none",
            explanation=(
                f"Task result: {get_task_result(transcript)}\n"
                f"{get_execution_signals(transcript)}"
            ),
            metadata={**signals, **get_termination_context(transcript)} or None,
        )

    return scan

"""Helpers for building Inspect Scout scanners over Inspect eval logs.

These accessors are written for Humanity's Last Exam (`inspect_evals/hle`)
transcripts but degrade gracefully on other benchmarks: every function returns
a placeholder string rather than raising when a field is absent.

The HLE record that matters for failure-mode analysis is spread across three
places in a Scout `Transcript`:

- `transcript.messages` — system prompt (answer format), question, response.
- `transcript.metadata` — `target` (reference answer), `sample_metadata`
  (category, answer type, and the question author's `rationale`), and `scores`
  (the `llm_grader` verdict *with* the judge's extracted answer and reasoning).
- `transcript.events` — model events carry `stop_reason` and usage, which is
  the only place a silent max-tokens truncation shows up.
"""

import json
from typing import Any

from inspect_scout import Transcript

NOT_AVAILABLE = "(not available)"


# ---------------------------------------------------------------- metadata --


def get_sample_metadata(transcript: Transcript) -> dict[str, Any]:
    """Return the eval's per-sample metadata dict.

    Scout stores this either pre-parsed or as a JSON string depending on how
    the transcript was read, so normalise both.
    """
    sample_metadata = (transcript.metadata or {}).get("sample_metadata", {})
    if isinstance(sample_metadata, str):
        try:
            sample_metadata = json.loads(sample_metadata)
        except (json.JSONDecodeError, ValueError):
            return {}
    return sample_metadata if isinstance(sample_metadata, dict) else {}


def get_question_metadata(transcript: Transcript) -> str:
    """Return a formatted block of the question's dataset attributes.

    For HLE this is category, raw subject, answer type (`exactMatch` vs
    `multipleChoice`), and whether the question includes an image — the last
    matters because a text-only run silently drops the image.
    """
    metadata = get_sample_metadata(transcript)
    fields = [
        ("question id", metadata.get("uid")),
        ("category", metadata.get("category")),
        ("subject", metadata.get("raw_subject")),
        ("answer type", metadata.get("answer_type")),
        ("has image", metadata.get("has_image")),
    ]
    lines = [f"{label}: {value}" for label, value in fields if value is not None]
    lines.append(f"model under test: {transcript.model or NOT_AVAILABLE}")
    return "\n".join(lines) if lines else NOT_AVAILABLE


def get_reference_answer(transcript: Transcript) -> str:
    """Return the benchmark's reference (target) answer."""
    target = (transcript.metadata or {}).get("target")
    if isinstance(target, list):
        target = ", ".join(str(t) for t in target)
    target = str(target).strip() if target is not None else ""
    return target or NOT_AVAILABLE


def get_author_rationale(transcript: Transcript) -> str:
    """Return the question author's rationale for the reference answer.

    HLE ships this per question. It is the strongest available evidence for
    telling `incorrect_reference_answer` apart from a plain model error: it
    shows the intended derivation (or admits to citing a source for it).
    """
    rationale = get_sample_metadata(transcript).get("rationale")
    rationale = str(rationale).strip() if rationale else ""
    return rationale or NOT_AVAILABLE


# ---------------------------------------------------------------- messages --


def _numbered(transcript: Transcript, role: str) -> str:
    return "\n".join(
        f"[M{i}] {getattr(m, 'text', '') or ''}"
        for i, m in enumerate(transcript.messages)
        if m.role == role
    )


def get_system_messages(transcript: Transcript) -> str:
    """Return system messages with `[M#]` ids.

    The `llm_scanner` default preprocessor strips system messages from the
    rendered transcript, so scanners that care about output-format
    instructions have to inject them into the question themselves.
    """
    return _numbered(transcript, "system") or NOT_AVAILABLE


def get_user_messages(transcript: Transcript) -> str:
    """Return user messages with `[M#]` ids."""
    return _numbered(transcript, "user") or NOT_AVAILABLE


def get_final_response(transcript: Transcript) -> str:
    """Return the last assistant message, keeping reasoning content labelled.

    Reasoning blocks are included because a resource-limit or format failure
    often shows up as a long reasoning trace with no text content after it.
    """
    final = next(
        ((i, m) for i, m in reversed(list(enumerate(transcript.messages))) if m.role == "assistant"),
        None,
    )
    if final is None:
        return NOT_AVAILABLE
    index, message = final

    if isinstance(message.content, str):
        body = message.content
    else:
        parts: list[str] = []
        for content in message.content:
            content_type = getattr(content, "type", None)
            if content_type == "reasoning":
                if getattr(content, "redacted", False):
                    reasoning = getattr(content, "summary", None) or "REDACTED"
                else:
                    reasoning = getattr(content, "reasoning", "") or ""
                if reasoning.strip():
                    parts.append(f"[reasoning]\n{reasoning}\n[end of reasoning]")
            elif content_type == "text":
                text = getattr(content, "text", "") or ""
                if text.strip():
                    parts.append(text)
        body = "\n\n".join(parts)

    return f"[M{index}] {body}" if body.strip() else f"[M{index}] (empty response)"


# ------------------------------------------------------------------ scores --


def get_scores(transcript: Transcript) -> dict[str, dict[str, Any]]:
    """Return full score records keyed by scorer name.

    `transcript.metadata["scores"]` carries the judge's extracted answer and
    reasoning, but only once transcript content has been read. Fall back to
    `score` events (available when the scanner requests events) and finally to
    the bare `score_<scorer>` values that are present even in the index.
    """
    metadata = transcript.metadata or {}

    scores = metadata.get("scores")
    if isinstance(scores, str):
        try:
            scores = json.loads(scores)
        except (json.JSONDecodeError, ValueError):
            scores = None
    if isinstance(scores, dict) and scores:
        return {k: v for k, v in scores.items() if isinstance(v, dict)}

    from_events: dict[str, dict[str, Any]] = {}
    for event in transcript.events:
        if getattr(event, "event", None) != "score":
            continue
        score = getattr(event, "score", None)
        if score is None:
            continue
        name = getattr(event, "scorer", None) or "score"
        from_events[name] = score.model_dump() if hasattr(score, "model_dump") else dict(score)
    if from_events:
        return from_events

    bare: dict[str, dict[str, Any]] = {}
    for key, value in metadata.items():
        if not key.startswith("score_"):
            continue
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                pass
        bare[key.removeprefix("score_")] = {"value": value}
    return bare


def _score_verdict(value: Any) -> str | None:
    """Reduce a score value to 'PASSED'/'FAILED', or None if undecidable."""
    if isinstance(value, bool):
        return "PASSED" if value else "FAILED"
    if isinstance(value, (int, float)):
        return "PASSED" if value > 0 else "FAILED"
    if isinstance(value, str):
        upper = value.strip().upper()
        if upper in ("C", "CORRECT", "1", "TRUE", "YES", "PASS", "PASSED", "P"):
            return "PASSED"
        if upper in ("I", "INCORRECT", "0", "FALSE", "NO", "FAIL", "FAILED", "F"):
            return "FAILED"
        return None
    if isinstance(value, dict):
        for key in ("score", "is_correct", "correct", "value", "result"):
            if key in value:
                verdict = _score_verdict(value[key])
                if verdict is not None:
                    return verdict
    return None


def get_task_result(transcript: Transcript) -> str:
    """Return 'PASSED', 'FAILED', or 'NOT REPORTED' for the transcript.

    `transcript.success` is None for HLE because `llm_grader` returns a dict
    (`{"score": "C"|"I", "confidence": N}`) that Scout cannot reduce on its
    own, so fall through to the score value itself.
    """
    if transcript.success is True:
        return "PASSED"
    if transcript.success is False:
        return "FAILED"

    verdict = _score_verdict(transcript.score)
    if verdict is not None:
        return verdict
    for score in get_scores(transcript).values():
        verdict = _score_verdict(score.get("value"))
        if verdict is not None:
            return verdict
    return "NOT REPORTED"


def get_grader_record(transcript: Transcript) -> str:
    """Return a formatted block of every scorer's verdict and reasoning.

    Includes the judge's *extracted* answer, which is what distinguishes a
    format/extraction failure (right answer, wrong extraction) from a judge
    failure (right answer extracted, wrongly rejected).
    """
    scores = get_scores(transcript)
    if not scores:
        return NOT_AVAILABLE

    blocks: list[str] = []
    for name, score in scores.items():
        value = score.get("value")
        lines = [f"scorer: {name}"]
        if isinstance(value, dict):
            lines.extend(f"  {k}: {v}" for k, v in value.items())
        else:
            lines.append(f"  value: {value}")
        lines.append(f"  verdict: {_score_verdict(value) or 'NOT REPORTED'}")
        lines.append(f"  answer extracted by judge: {score.get('answer') or '(none)'}")
        lines.append(f"  judge reasoning: {score.get('explanation') or '(none)'}")
        score_metadata = score.get("metadata") or {}
        if isinstance(score_metadata, dict) and score_metadata:
            lines.extend(f"  {k}: {v}" for k, v in score_metadata.items())
        blocks.append("\n".join(lines))

    raw = get_grader_outputs(transcript)
    if raw != NOT_AVAILABLE:
        blocks.append(f"raw judge output(s):\n{raw}")
    return "\n\n".join(blocks)


def get_grader_outputs(transcript: Transcript) -> str:
    """Return raw completions from model calls made under a grader role.

    Only available when the scanner requests model events; HLE's judge answers
    with a JSON object whose `reasoning` field is more detailed than the
    explanation that ends up on the score.
    """
    outputs: list[str] = []
    for event in transcript.events:
        if getattr(event, "event", None) != "model":
            continue
        role = getattr(event, "role", None)
        if not role or "grad" not in role.lower():
            continue
        output = getattr(event, "output", None)
        completion = getattr(output, "completion", "") if output else ""
        if completion:
            outputs.append(f"[{role} / {getattr(event, 'model', '?')}]\n{completion}")
    return "\n\n".join(outputs) if outputs else NOT_AVAILABLE


# ------------------------------------------------------- execution signals --


def get_failure_signals(transcript: Transcript) -> dict[str, Any]:
    """Return deterministic, non-LLM evidence that the attempt ended abnormally.

    Only anomalies are reported: a fired limit, a truncated or errored
    generation, a tool error, an empty response, or a judge that could not
    extract an answer. An empty dict means "nothing abnormal detected", not
    "the attempt was fine". Normal termination context lives in
    `get_termination_context`.
    """
    signals: dict[str, Any] = {}

    error = (transcript.error or "").strip()
    if error:
        signals["sample_error"] = error

    limit = (transcript.limit or "").strip()
    if limit:
        signals["limit_exceeded"] = limit

    truncated: list[str] = []
    model_errors: list[str] = []
    for event in _attempt_model_events(transcript):
        output = getattr(event, "output", None)
        stop_reason = getattr(output, "stop_reason", None) if output else None
        if stop_reason in ("max_tokens", "model_length"):
            truncated.append(str(stop_reason))
        event_error = getattr(event, "error", None)
        if event_error:
            model_errors.append(str(event_error))
    if truncated:
        signals["output_truncated"] = truncated
    if model_errors:
        signals["model_errors"] = model_errors

    tool_errors: list[str] = []
    for i, message in enumerate(transcript.messages):
        if message.role != "tool":
            continue
        tool_error = getattr(message, "error", None)
        if tool_error:
            error_type = getattr(tool_error, "type", None) or "unknown"
            error_message = getattr(tool_error, "message", None) or str(tool_error)
            tool_errors.append(f"[M{i}] [{error_type}] {error_message}")
    if tool_errors:
        signals["tool_errors"] = tool_errors

    final = get_final_response(transcript)
    if final == NOT_AVAILABLE or final.endswith("(empty response)"):
        signals["empty_final_response"] = True

    for name, score in get_scores(transcript).items():
        answer = str(score.get("answer") or "").strip()
        if not answer or answer.lower() in ("none", "null"):
            signals.setdefault("no_answer_extracted", []).append(name)

    return signals


def _attempt_model_events(transcript: Transcript) -> list[Any]:
    """Return model events for the attempt itself, excluding judge/grader calls."""
    return [
        event
        for event in transcript.events
        if getattr(event, "event", None) == "model" and not getattr(event, "role", None)
    ]


def get_termination_context(transcript: Transcript) -> dict[str, Any]:
    """Return non-anomalous facts about how the attempt ended.

    Kept apart from `get_failure_signals` so that a normal `stop` does not read
    as evidence of a resource limit, while still being visible to a judge that
    needs to rule one out.
    """
    context: dict[str, Any] = {}
    stop_reasons = [
        str(getattr(event.output, "stop_reason", None))
        for event in _attempt_model_events(transcript)
        if getattr(event, "output", None) is not None
        and getattr(event.output, "stop_reason", None)
    ]
    if stop_reasons:
        context["stop_reasons"] = stop_reasons
    if transcript.total_tokens:
        context["total_tokens"] = transcript.total_tokens
    if transcript.total_time:
        context["total_time_seconds"] = round(transcript.total_time, 1)
    return context


def _render(mapping: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in mapping.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    return lines


def get_execution_signals(transcript: Transcript) -> str:
    """Return the anomalies and termination context as a block for a prompt."""
    signals = get_failure_signals(transcript)
    lines = (
        _render(signals)
        if signals
        else ["No limit, truncation, tool, or extraction anomaly detected."]
    )
    context = get_termination_context(transcript)
    if context:
        lines.append("")
        lines.append("context (not in itself evidence of failure):")
        lines.extend(f"  {line}" for line in _render(context))
    return "\n".join(lines)


# --------------------------------------------------------- tool inventory ---


def _format_arguments(arguments: Any) -> str:
    if isinstance(arguments, dict):
        try:
            return json.dumps(arguments, indent=2)
        except (TypeError, ValueError):
            return str(arguments)
    return str(arguments) if arguments is not None else "(none)"


def get_tool_interactions(transcript: Transcript) -> str:
    """Return a chronological view of tool calls and their results.

    HLE runs with no tools, so this is normally empty — but a tool or
    environment failure cannot be told apart from a model error without it, so
    the scanner includes the block whenever there is anything to show.
    """
    results: dict[str, tuple[int, Any]] = {}
    for i, message in enumerate(transcript.messages):
        if message.role == "tool":
            tool_call_id = getattr(message, "tool_call_id", None)
            if tool_call_id:
                results[tool_call_id] = (i, message)

    def render_result(tool_call_id: str) -> list[str]:
        entry = results.get(tool_call_id)
        if entry is None:
            return []
        index, message = entry
        error = getattr(message, "error", None)
        if error:
            error_type = getattr(error, "type", None) or "unknown"
            error_message = getattr(error, "message", None) or str(error)
            return [f"  result [M{index}]:", f"    error: [{error_type}] {error_message}"]
        content = getattr(message, "result", None) or getattr(message, "text", None) or "(empty)"
        return [f"  result [M{index}]:", f"    {content}"]

    blocks: list[str] = []
    for i, message in enumerate(transcript.messages):
        if message.role != "assistant":
            continue
        for tool_call in getattr(message, "tool_calls", None) or []:
            block = [
                f"[M{i}] TOOL CALL: {tool_call.function} (id={tool_call.id})",
                f"  arguments:\n{_format_arguments(tool_call.arguments)}",
            ]
            if getattr(tool_call, "parse_error", None):
                block.append(f"  parse_error: {tool_call.parse_error}")
            block.extend(render_result(tool_call.id))
            blocks.append("\n".join(block))

        content_list = message.content if isinstance(message.content, list) else []
        for content in content_list:
            if getattr(content, "type", None) != "tool_use":
                continue
            block = [
                f"[M{i}] TOOL USE: {getattr(content, 'name', None) or '?'}"
                f" (tool_type={getattr(content, 'tool_type', None) or 'unknown'})",
                f"  arguments:\n{_format_arguments(getattr(content, 'arguments', None))}",
            ]
            error = getattr(content, "error", None)
            if error:
                error_type = getattr(error, "type", None) or "unknown"
                error_message = getattr(error, "message", None) or str(error)
                block.append(f"  error: [{error_type}] {error_message}")
            else:
                block.append(f"  result: {getattr(content, 'result', None) or '(empty)'}")
            blocks.append("\n".join(block))

    return "\n\n".join(blocks) if blocks else "(no tool interactions found)"

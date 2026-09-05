"""Starter Inspect Scout scanners."""

from inspect_scout import Result, Scanner, Transcript, scanner


@scanner(messages="all")
def assistant_message_count() -> Scanner[Transcript]:
    """Count assistant messages in a transcript without calling a model."""

    async def scan(transcript: Transcript) -> Result:
        count = sum(message.role == "assistant" for message in transcript.messages)
        return Result(
            value=count,
            explanation=f"Found {count} assistant message(s).",
        )

    return scan

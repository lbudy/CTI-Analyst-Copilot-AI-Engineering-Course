"""Course tool-call inspection. This module does not run or select tools."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    call_id: str | None = field(default=None, compare=False)


def collect_tools(messages):
    tool_calls = []
    for message in messages:
        for part in message.parts:
            if part.part_kind != 'tool-call':
                continue
            if part.tool_name == 'final_result':
                continue
            # Pydantic AI can store args as JSON text or a dict. Use its public
            # converter so tests always see a dictionary; don't parse JSON here.
            tool_calls.append(ToolCall(part.tool_name, part.args_as_dict(), part.tool_call_id))
    return tool_calls


async def run_agent_test(agent, user_prompt, message_history=None, *, show_usage=False, config=None):
    """Same real graph, silent JSON handler and no user/tool console prints."""
    from jaxn import JSONParserHandler
    from doc_agent import AgentStreamRunner
    runner = AgentStreamRunner(agent, JSONParserHandler(), verbose=False, config=config)
    from tests.cost_tracker import capture_usage
    try:
        result = await runner.run(user_prompt, message_history)
    except Exception as exc:
        partial = getattr(exc, 'cti_partial_result', None)
        if partial is not None:
            capture_usage(get_model_name(agent, partial), partial)
        raise
    capture_usage(get_model_name(agent, result), result)
    if show_usage:
        print(f"Usage: {result.usage}")
    return result


def get_model_name(agent, result):
    """Identify the executed model using response metadata, including test overrides."""
    from tests.cost_tracker import identify_model
    return identify_model(agent, result)

"""Course-style, read-only tools and message/event displays for Pydantic AI."""
import inspect
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartStartEvent,
    PartDeltaEvent,
    TextPart,
    TextPartDelta,
)


class SearchTools:
    """Search report snippets, then retrieve complete text from the supplied corpus."""

    def __init__(self, index: Any, highlighter: Any, file_index: dict[str, str]) -> None:
        self.index = index
        self.highlighter = highlighter
        self.file_index = dict(file_index)

    def search(self, query: str) -> list[dict[str, Any]]:
        """Find relevant public threat reports and return highlighted snippets.

        Search results include filenames and original source metadata. Snippets help
        choose which reports to open; fetch full text before quoting threat evidence.

        Args:
            query: Search terms describing the actor, technique, vulnerability, or question.

        Returns:
            Up to five report records with highlighted snippets instead of full content.
        """
        if not query.strip():
            return []
        search_results = self.index.search(query=query, num_results=5)
        return self.highlighter.highlight(query, search_results)

    def get_file(self, filename: str) -> str:
        """Retrieve the complete extracted text of one report from the local corpus.

        Only filenames in the supplied mapping are available. This does not open
        arbitrary filesystem paths, browse websites, or perform enrichment.

        Args:
            filename: Exact report filename returned by search, for example AA24-109A.txt.

        Returns:
            Full source text without highlighting, or a file-not-found message.
        """
        if filename in self.file_index:
            return self.file_index[filename]
        return f'file {filename} does not exist'


def get_instance_methods(instance: Any) -> list[Any]:
    """Return public bound methods, matching the course helper without ToyAIKit."""
    return [method for name, method in inspect.getmembers(instance, predicate=inspect.ismethod)
            if not name.startswith('_')]


def print_messages(messages: list[Any]) -> None:
    """Print the course's request/response parts without dumping full report returns."""
    for message in messages:
        print(message.kind)
        for part in message.parts:
            part_kind = part.part_kind
            if part_kind == 'user-prompt':
                print('USER:', part.content)
            if part_kind == 'tool-call':
                print('TOOL CALL:', part.tool_name, part.args)
            if part_kind == 'tool-return':
                print('TOOL RETURN:', part.tool_name, '| characters:', len(str(part.content)))
            if part_kind == 'text':
                print(part.content)
            if part_kind == 'retry-prompt':
                print('RETRY:', part.content)
        print()


class NamedCallback:
    """Display observable tool and text events while Pydantic AI runs the agent."""

    def __init__(self, agent: Any, show_text: bool = True) -> None:
        self.agent_name = agent.name
        self.show_text = show_text
        self.events: list[dict[str, Any]] = []

    async def print_function_calls(self, ctx: RunContext[Any], event: Any) -> None:
        # Pydantic AI supplies an async event iterator; retain the course's recursion.
        if hasattr(event, '__aiter__'):
            async for sub in event:
                await self.print_function_calls(ctx, sub)
            return
        if isinstance(event, FunctionToolCallEvent):
            tool_name = event.part.tool_name
            args = event.part.args
            self.events.append({'kind': 'tool-call', 'agent': self.agent_name,
                                'tool': tool_name, 'args': args, 'call_id': event.part.tool_call_id})
            print(f'TOOL CALL ({self.agent_name}): {tool_name}({args})')
        elif isinstance(event, FunctionToolResultEvent):
            tool_name = getattr(event.part, 'tool_name', None)
            self.events.append({'kind': 'tool-return', 'agent': self.agent_name,
                                'tool': tool_name, 'call_id': event.part.tool_call_id})
            print(f'TOOL RETURN ({self.agent_name}): {tool_name}')
        elif isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
            self.events.append({'kind': 'text', 'agent': self.agent_name, 'text': event.part.content})
            if self.show_text:
                print(event.part.content, end='', flush=True)
        elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            self.events.append({'kind': 'text-delta', 'agent': self.agent_name,
                                'text': event.delta.content_delta})
            if self.show_text:
                print(event.delta.content_delta, end='', flush=True)

    async def __call__(self, ctx: RunContext[Any], event: Any) -> None:
        await self.print_function_calls(ctx, event)

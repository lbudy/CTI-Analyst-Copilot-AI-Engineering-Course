"""Inspect recorded messages; never select or execute an agent tool."""
import re
from tests.utils import collect_tools as collect_tool_records


def collect_tools(messages):
    # Preserve the earlier dictionary interface for existing test callers.
    return [{'name': call.name, 'args': call.args, 'call_id': call.call_id}
            for call in collect_tool_records(messages) if call.name in {'search', 'get_file'}]


def code_blocks(answer):
    return re.findall(r'```[^\n]*\n(.*?)```', answer, flags=re.DOTALL)


def source_references(answer, allowed_urls):
    # Match actual Markdown targets or raw URLs, not a trusted URL prefix in an evil URL.
    links = re.findall(r'https?://[^\s<>\[\]()]+', answer)
    return [link for link in links if link.rstrip('.,;') in set(allowed_urls)]

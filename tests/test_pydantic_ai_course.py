import ast
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from minsearch import AppendableIndex, Highlighter, Tokenizer
from minsearch.tokenizer import DEFAULT_ENGLISH_STOP_WORDS
from pydantic_ai import Agent, Tool
from pydantic_ai import models
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (ModelResponse, TextPart, ToolCallPart, ToolReturnPart,
                                  FunctionToolCallEvent, FunctionToolResultEvent)
from pydantic_ai.models.function import FunctionModel, DeltaToolCall
from pydantic_ai.usage import RequestUsage, RunUsage, UsageLimits

from course_structured_agent import RAGResponse
from pydantic_search_tools import SearchTools, get_instance_methods, print_messages, NamedCallback

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = {'answer': 'Offline fixture summary; not a real intelligence assessment.',
           'found_answer': True, 'confidence': 0.5, 'confidence_explanation': 'Synthetic test only.',
           'answer_type': 'explanation', 'followup_questions': ['What evidence is missing?']}


def build_tools():
    reports = json.loads((ROOT / 'data/threat_reports.json').read_text())
    documents = [{**report, 'filename': f"{report['report_id']}.txt", 'description': ''}
                 for report in reports]
    index = AppendableIndex(text_fields=['title', 'description', 'content'], keyword_fields=['filename'])
    index.fit(documents)
    highlighter = Highlighter(highlight_fields=['content'], max_matches=3, snippet_size=50,
                              tokenizer=Tokenizer(stemmer='snowball', stop_words=DEFAULT_ENGLISH_STOP_WORDS))
    file_index = {doc['filename']: doc['content'] for doc in documents}
    return SearchTools(index, highlighter, file_index), documents


def research_model(structured=False):
    calls = []
    def function(messages, info):
        calls.append(copy.deepcopy(messages))
        stage = (len(calls)-1) % 3
        if stage == 0:
            part = ToolCallPart('search', {'query': 'Akira ransomware VMware'}, tool_call_id=f'search-{len(calls)}')
        elif stage == 1:
            part = ToolCallPart('get_file', {'filename': 'AA24-109A.txt'}, tool_call_id=f'file-{len(calls)}')
        elif structured:
            part = ToolCallPart(info.output_tools[0].name, PAYLOAD, tool_call_id=f'output-{len(calls)}')
        else:
            part = TextPart('Offline fixture summary after searching and opening the source report.')
        return ModelResponse(parts=[part], usage=RequestUsage(input_tokens=20, output_tokens=10))
    return FunctionModel(function), calls


class SearchToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools, cls.documents = build_tools()

    def test_all_thirteen_full_reports_are_available_without_rechunking(self):
        self.assertEqual(len(self.documents), 13)
        for report in self.documents:
            self.assertEqual(self.tools.get_file(report['filename']), report['content'])
        hits = self.tools.search('Akira ransomware VMware')
        self.assertTrue(hits)
        self.assertIn('AA24-109A.txt', {h['filename'] for h in hits})
        for hit in hits:
            self.assertIsInstance(hit['content'], dict)
            self.assertIn('matches', hit['content'])
            self.assertIn('source_url', hit)
        self.assertNotIn('chunk_id', self.documents[0])

    def test_unknown_paths_do_not_read_filesystem(self):
        self.assertEqual(self.tools.get_file('../.env'), 'file ../.env does not exist')
        self.assertEqual(self.tools.search(' '), [])

    def test_discovery_and_generated_docstring_schemas(self):
        methods = get_instance_methods(self.tools)
        self.assertEqual({f.__name__ for f in methods}, {'search', 'get_file'})
        for method in methods:
            tool = Tool(method, docstring_format='google', require_parameter_descriptions=True)
            schema = tool.function_schema.json_schema
            self.assertFalse(schema['additionalProperties'])
            parameter = 'query' if method.__name__ == 'search' else 'filename'
            self.assertEqual(schema['required'], [parameter])
            self.assertIn('description', schema['properties'][parameter])
            self.assertIn('report', tool.description.lower())

    def test_notebook_tools_and_callback_match_library(self):
        names = {'SearchTools', 'get_instance_methods', 'print_messages', 'NamedCallback'}
        expected = {n.name: ast.dump(n) for n in ast.parse((ROOT / 'pydantic_search_tools.py').read_text()).body
                    if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names}
        notebook = json.loads((ROOT / 'notebooks/02-rag-chemical-triage.ipynb').read_text())
        actual = {}
        for cell in notebook['cells']:
            if cell['cell_type']=='code' and 'pydantic-ai-course' in cell.get('metadata',{}).get('tags',[]):
                for node in ast.parse(''.join(cell['source'])).body:
                    if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names:
                        actual[node.name]=ast.dump(node)
        self.assertEqual(actual, expected)


class PydanticRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools, self.documents = build_tools()
        self.block_real_requests = patch.object(models, 'ALLOW_MODEL_REQUESTS', False)
        self.block_real_requests.start()
        self.addCleanup(self.block_real_requests.stop)

    async def test_search_open_answer_and_message_parts_use_real_framework(self):
        model, calls = research_model()
        agent = Agent(model, name='search', tools=get_instance_methods(self.tools))
        before = json.dumps(self.documents, sort_keys=True)
        result = await agent.run('Find Akira reporting', usage_limits=UsageLimits(request_limit=6, tool_calls_limit=10))
        self.assertIn('Offline fixture summary', result.output)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.usage.requests, 3)
        self.assertEqual(result.usage.tool_calls, 2)
        returns = [part for message in result.all_messages() for part in message.parts if isinstance(part, ToolReturnPart)]
        self.assertEqual([p.tool_name for p in returns], ['search', 'get_file'])
        self.assertEqual(returns[1].content, self.tools.file_index['AA24-109A.txt'])
        self.assertEqual(json.dumps(self.documents, sort_keys=True), before)
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            print_messages(result.all_messages())
        self.assertIn('TOOL CALL: search', capture.getvalue())
        self.assertIn('TOOL RETURN: get_file', capture.getvalue())

    async def test_followup_history_and_run_usage_addition(self):
        model, calls = research_model()
        agent = Agent(model, tools=get_instance_methods(self.tools))
        first = await agent.run('First question')
        second = await agent.run('Follow-up question', message_history=first.all_messages())
        total = RunUsage() + first.usage + second.usage
        self.assertEqual(total.requests, 6)
        self.assertEqual(total.tool_calls, 4)
        self.assertEqual(total.input_tokens, 120)
        self.assertGreater(len(second.all_messages()), len(second.new_messages()))
        user_prompts = [p.content for m in second.all_messages() for p in m.parts if p.part_kind == 'user-prompt']
        self.assertEqual(user_prompts, ['First question', 'Follow-up question'])

    async def test_native_structured_output_reuses_course_schema(self):
        model, calls = research_model(structured=True)
        agent = Agent(model, tools=get_instance_methods(self.tools), output_type=RAGResponse)
        result = await agent.run('Structured fixture')
        self.assertIsInstance(result.output, RAGResponse)
        self.assertEqual(result.output.model_dump(), PAYLOAD)
        self.assertEqual(len(calls), 3)

    async def test_native_usage_limit_stops_unfinished_research(self):
        model, calls = research_model()
        agent = Agent(model, tools=get_instance_methods(self.tools))
        with self.assertRaises(UsageLimitExceeded):
            await agent.run('Stop before synthesis', usage_limits=UsageLimits(request_limit=2))
        self.assertEqual(len(calls), 2)

    async def test_native_event_stream_handler_receives_tool_and_text_events(self):
        count = 0
        async def streaming(messages, info):
            nonlocal count
            count += 1
            if count == 1:
                yield {0: DeltaToolCall(name='search', json_args='{"query":"Akira ransomware"}', tool_call_id='s1')}
            elif count == 2:
                yield {0: DeltaToolCall(name='get_file', json_args='{"filename":"AA24-109A.txt"}', tool_call_id='f1')}
            else:
                yield 'Offline '
                yield 'streamed fixture.'
        agent = Agent(FunctionModel(stream_function=streaming), name='search', tools=get_instance_methods(self.tools))
        callback = NamedCallback(agent, show_text=False)
        with contextlib.redirect_stdout(io.StringIO()):
            result = await agent.run('Stream fixture', event_stream_handler=callback)
        self.assertEqual(result.output, 'Offline streamed fixture.')
        self.assertEqual([e['tool'] for e in callback.events if e['kind']=='tool-call'], ['search','get_file'])
        self.assertEqual([e['tool'] for e in callback.events if e['kind']=='tool-return'], ['search','get_file'])
        self.assertTrue(any(e['kind'] in {'text','text-delta'} for e in callback.events))
        self.assertEqual(count, 3)

    async def test_course_qna_cell_preserves_history_with_scripted_inputs(self):
        notebook = json.loads((ROOT / 'notebooks/02-rag-chemical-triage.ipynb').read_text())
        code = next(''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code'
                    and ''.join(c['source']).startswith('pydantic_qa_messages = []'))
        model, calls = research_model()
        agent = Agent(model, tools=get_instance_methods(self.tools))
        namespace = {'RUN_PYDANTIC_QNA': True, 'RunUsage': RunUsage, 'search_agent': agent,
                     'pydantic_limits': UsageLimits(request_limit=6,tool_calls_limit=10),
                     'UsageLimitExceeded': UsageLimitExceeded, 'print_messages': lambda messages: None}
        compiled = compile(code, 'framework-qna', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        with patch('builtins.input', side_effect=['First', 'Follow-up', 'stop']), contextlib.redirect_stdout(io.StringIO()):
            await eval(compiled, namespace)
        self.assertEqual(namespace['pydantic_qa_usage'].requests, 6)
        prompts = [p.content for m in namespace['pydantic_qa_messages'] for p in m.parts if p.part_kind=='user-prompt']
        self.assertEqual(prompts, ['First','Follow-up'])


class EventLessonTests(unittest.IsolatedAsyncioTestCase):
    async def test_course_callback_accepts_nested_streams_and_direct_events(self):
        callback = NamedCallback(type('AgentName', (), {'name': 'search'})(), show_text=False)
        async def inner():
            yield FunctionToolCallEvent(ToolCallPart('search', {'query': 'fixture'}, tool_call_id='s'))
        async def outer():
            yield inner()
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            await callback(None, outer())
            await callback(None, FunctionToolCallEvent(ToolCallPart('get_file', {'filename': 'AA24-109A.txt'}, tool_call_id='f')))
        self.assertEqual([e['tool'] for e in callback.events], ['search', 'get_file'])
        self.assertIn('TOOL CALL (search): search', capture.getvalue())
        self.assertIn('AA24-109A.txt', capture.getvalue())

    async def test_notebook_live_stream_cell_uses_native_handler(self):
        notebook = json.loads((ROOT / 'notebooks/02-rag-chemical-triage.ipynb').read_text())
        code = next(''.join(c['source']) for c in notebook['cells']
                    if c['cell_type']=='code' and 'pydantic-events-lesson' in c.get('metadata',{}).get('tags',[])
                    and ''.join(c['source']).startswith('if RUN_PYDANTIC_STREAM:'))
        tools, documents = build_tools()
        count = 0
        async def stream(messages, info):
            nonlocal count
            count += 1
            if count == 1:
                yield {0: DeltaToolCall(name='search', json_args='{"query":"Akira"}', tool_call_id='s')}
            else:
                yield 'Offline event lesson fixture.'
        agent = Agent(FunctionModel(stream_function=stream), name='search', tools=get_instance_methods(tools))
        callback = NamedCallback(agent, show_text=False)
        callback.events.append({'kind': 'stale'})
        namespace = {'RUN_PYDANTIC_STREAM': True, 'search_agent': agent,
                     'callback': callback, 'pydantic_stream_query': 'Fixture question',
                     'pydantic_limits': UsageLimits(request_limit=6, tool_calls_limit=10),
                     'UsageLimitExceeded': UsageLimitExceeded,
                     'pydantic_stream_result': object()}
        compiled = compile(code, 'event-lesson', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        with patch.object(models, 'ALLOW_MODEL_REQUESTS', False), contextlib.redirect_stdout(io.StringIO()):
            await eval(compiled, namespace)
        self.assertEqual(namespace['pydantic_stream_result'].output, 'Offline event lesson fixture.')
        self.assertTrue(any(e['kind']=='tool-call' for e in callback.events))
        self.assertFalse(any(e['kind']=='stale' for e in callback.events))
        self.assertEqual(count, 2)

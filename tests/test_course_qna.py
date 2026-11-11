import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from course_agent import Agent

ROOT = Path(__file__).resolve().parents[1]
TOOL = {'type': 'function', 'name': 'search', 'description': 'Fixture search',
        'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}}


def call(name='search', query='fixture', call_id='c1'):
    return SimpleNamespace(type='function_call', name=name, arguments=json.dumps({'query': query}), call_id=call_id)


def message(text='Fixture answer, not a real threat finding.'):
    return SimpleNamespace(type='message', content=[SimpleNamespace(type='output_text', text=text)])


class FakeResponses:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return SimpleNamespace(output=next(self.steps), usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15))


def make_agent(steps, **kwargs):
    responses = FakeResponses(steps)
    agent = Agent(SimpleNamespace(responses=responses), 'fixture-model', 'Instance instructions', [TOOL],
                  tool_functions={'search': lambda query: [{'content': query, 'origin': 'fixture'}]}, **kwargs)
    return agent, responses


class AgentLibraryTests(unittest.TestCase):
    def test_loop_returns_history_and_supports_followup(self):
        agent, responses = make_agent([[call()], [message()], [message('Follow-up answer.')]])
        with contextlib.redirect_stdout(io.StringIO()):
            history = agent.loop('First question')
            returned = agent.loop('Follow-up', history)
        self.assertIs(returned, history)
        user_messages = [m['content'] for m in responses.requests[-1]['input'] if isinstance(m, dict) and m.get('role') == 'user']
        self.assertEqual(user_messages, ['First question', 'Follow-up'])
        self.assertEqual(agent.last_status, 'answered_unreviewed')
        self.assertEqual(agent.last_answer, 'Follow-up answer.')
        self.assertEqual(len(agent.trace), 1)
        self.assertEqual(agent.turn_number, 2)
        self.assertEqual(sum(u['total_tokens'] for u in agent.usage), 45)
        self.assertTrue(any(isinstance(m, dict) and m.get('call_id') == 'c1' for m in history))

    def test_qna_keeps_context_and_uses_instance_instructions(self):
        agent, responses = make_agent([[message()], [message('Second answer.')]])
        with patch('builtins.input', side_effect=['First', 'Second', ' STOP ']), contextlib.redirect_stdout(io.StringIO()):
            history = agent.qna()
        self.assertEqual(len(responses.requests), 2)
        self.assertEqual(history[0]['content'], 'Instance instructions')
        self.assertEqual([m['content'] for m in history if isinstance(m, dict) and m.get('role') == 'user'], ['First', 'Second'])
        self.assertIs(history, agent.message_history)

    def test_stop_blank_and_eof_make_no_calls(self):
        agent, responses = make_agent([])
        with patch('builtins.input', side_effect=[' ', 'stop']), contextlib.redirect_stdout(io.StringIO()):
            agent.qna()
        with patch('builtins.input', side_effect=EOFError), contextlib.redirect_stdout(io.StringIO()):
            agent.qna()
        self.assertFalse(responses.requests)

    def test_unknown_and_malformed_calls_return_errors(self):
        agent, responses = make_agent([])
        self.assertIn('error', json.loads(agent.make_call(call('not_available'))['output']))
        malformed = SimpleNamespace(name='search', arguments='{broken', call_id='bad')
        result = agent.make_call(malformed)
        self.assertEqual(result['call_id'], 'bad')
        self.assertIn('error', json.loads(result['output']))

    def test_registered_but_unadvertised_tool_is_not_executed(self):
        agent, responses = make_agent([])
        invoked = []
        agent.tool_functions['unadvertised'] = lambda query: invoked.append(query)
        self.assertIn('error', json.loads(agent.make_call(call('unadvertised'))['output']))
        self.assertFalse(invoked)

    def test_limit_and_independent_instances(self):
        agent, responses = make_agent([[call()], [call(call_id='c2')]], max_iterations=2)
        other, _ = make_agent([])
        with contextlib.redirect_stdout(io.StringIO()):
            agent.loop('Question')
        self.assertEqual(agent.last_status, 'iteration_limit')
        self.assertIsNone(agent.last_answer)
        self.assertEqual(len(responses.requests), 2)
        self.assertFalse(other.message_history)
        self.assertFalse(other.usage)
        self.assertFalse(other.trace)

    def test_missing_client_is_explicit(self):
        agent = Agent(None, 'fixture', 'Instructions', [])
        with self.assertRaisesRegex(ValueError, 'llm_client'):
            agent.loop('Question')

    def test_notebook_class_matches_library(self):
        notebook = json.loads((ROOT / 'notebooks/02-rag-chemical-triage.ipynb').read_text())
        implementations = [''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code'
                           and ''.join(c['source']).startswith('"""Small course-style Agent library:')]
        self.assertEqual(implementations, [(ROOT / 'course_agent.py').read_text()])


class VisibleQALoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        notebook = json.loads((ROOT / 'notebooks/02-rag-chemical-triage.ipynb').read_text())
        cls.cell = next(''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code'
                        and ''.join(c['source']).startswith('RUN_COURSE_QNA ='))

    def test_outer_loop_multiple_questions_and_tool_outputs(self):
        responses = FakeResponses([[call()], [message()], [message('Follow-up.')]])
        namespace = {
            'search_tool': TOOL, 'add_entry_tool': {**TOOL, 'name': 'add_entry'},
            'course_instructions': 'Instance instructions', 'course_client': SimpleNamespace(responses=responses),
            'COURSE_MODEL': 'fixture', 'MAX_ITERATIONS': 3,
            'make_call': lambda c: {'type': 'function_call_output', 'call_id': c.call_id, 'output': '[]'},
        }
        with patch('builtins.input', side_effect=['First', 'Follow-up', 'stop']), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(self.cell.replace('RUN_COURSE_QNA = False', 'RUN_COURSE_QNA = True'), 'visible-qna', 'exec'), namespace)
        self.assertEqual(namespace['qna_turn_number'], 2)
        self.assertEqual(len(namespace['qna_trace']), 1)
        self.assertEqual(sum(u['total_tokens'] for u in namespace['qna_usage']), 45)
        requests = responses.requests[-1]['input']
        self.assertEqual([m['content'] for m in requests if isinstance(m, dict) and m.get('role') == 'user'], ['First', 'Follow-up'])
        self.assertTrue(any(isinstance(m, dict) and m.get('type') == 'function_call_output' for m in requests))

    def test_visible_loop_stop_without_requests(self):
        responses = FakeResponses([])
        namespace = {'search_tool': TOOL, 'add_entry_tool': {**TOOL, 'name': 'add_entry'},
                     'course_instructions': 'Instructions', 'course_client': SimpleNamespace(responses=responses)}
        with patch('builtins.input', side_effect=['stop']), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(self.cell.replace('RUN_COURSE_QNA = False', 'RUN_COURSE_QNA = True'), 'visible-qna', 'exec'), namespace)
        self.assertFalse(responses.requests)
        self.assertEqual(namespace['qna_turn_number'], 0)

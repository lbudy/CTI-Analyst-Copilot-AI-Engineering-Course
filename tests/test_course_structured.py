import ast
import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from course_structured_agent import (RAGResponse, SimpleStructuredAgent, StructuredAgent1,
                                     StructuredAgent2, create_fake_tool)

ROOT = Path(__file__).resolve().parents[1]
TOOL = {'type': 'function', 'name': 'search', 'description': 'Fixture search',
        'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}},
                       'required': ['query'], 'additionalProperties': False}}
PAYLOAD = {'answer': 'Fixture answer, not a real threat assessment.', 'found_answer': True,
           'confidence': 0.6, 'confidence_explanation': 'Synthetic test evidence only.',
           'answer_type': 'explanation', 'followup_questions': ['What evidence is missing?']}


def call(name='search', arguments=None, call_id='call_1'):
    return SimpleNamespace(type='function_call', name=name,
                           arguments=json.dumps({'query': 'fixture'} if arguments is None else arguments), call_id=call_id)


def message(text='Fixture answer.'):
    return SimpleNamespace(type='message', content=[SimpleNamespace(type='output_text', text=text)])


def response(output, parsed=None):
    return SimpleNamespace(output=output, output_parsed=parsed,
                           usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30))


class ScriptedResponses:
    def __init__(self, creates=(), parses=()):
        self.creates = iter(creates)
        self.parses = iter(parses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(('create', copy.deepcopy(kwargs)))
        return next(self.creates)

    def parse(self, **kwargs):
        self.requests.append(('parse', copy.deepcopy(kwargs)))
        return next(self.parses)


def instance(cls, creates=(), parses=(), **kwargs):
    responses = ScriptedResponses(creates, parses)
    agent = cls(SimpleNamespace(responses=responses), 'fixture', 'Use retrieved evidence.', [TOOL], RAGResponse,
                tool_functions={'search': lambda query: [{'content': query}]}, **kwargs)
    return agent, responses


class StructuredCourseTests(unittest.TestCase):
    def test_schema_fields_and_bounds(self):
        self.assertEqual(set(RAGResponse.model_fields), set(PAYLOAD))
        for changed in [{**PAYLOAD, 'confidence': 1.5}, {**PAYLOAD, 'confidence': -0.1},
                        {**PAYLOAD, 'answer_type': 'invented'}, {**PAYLOAD, 'extra': True}]:
            with self.assertRaises(ValidationError):
                RAGResponse.model_validate(changed)

    def test_approach_one_parses_each_iteration_and_keeps_tools_strict(self):
        original = copy.deepcopy(TOOL)
        parsed = RAGResponse.model_validate(PAYLOAD)
        agent, responses = instance(SimpleStructuredAgent, parses=[
            response([call()]), response([message(json.dumps(PAYLOAD))], parsed)])
        with contextlib.redirect_stdout(io.StringIO()):
            history = agent.loop('Question')
        self.assertEqual([method for method, _ in responses.requests], ['parse', 'parse'])
        self.assertTrue(responses.requests[0][1]['tools'][0]['strict'])
        self.assertEqual(TOOL, original)
        self.assertEqual(agent.last_output, parsed)
        self.assertEqual(agent.last_status, 'structured_unreviewed')
        self.assertTrue(any(isinstance(m, dict) and m.get('call_id') == 'call_1' for m in history))

    def test_wrapper_finishes_research_before_one_extra_parse(self):
        parsed = RAGResponse.model_validate(PAYLOAD)
        agent, responses = instance(StructuredAgent1,
            creates=[response([call()]), response([message()])],
            parses=[response([message(json.dumps(PAYLOAD))], parsed)])
        with contextlib.redirect_stdout(io.StringIO()):
            history, output = agent.structured_loop('Question')
        self.assertEqual([method for method, _ in responses.requests], ['create', 'create', 'parse'])
        self.assertNotIn('tools', responses.requests[-1][1])
        self.assertEqual(output, parsed)
        self.assertEqual(sum(u['total_tokens'] for u in agent.usage), 90)
        self.assertEqual(agent.usage[-1]['stage'], 'structure_final_answer')
        self.assertIs(history, agent.message_history)

    def test_wrapper_does_not_format_incomplete_research(self):
        agent, responses = instance(StructuredAgent1, creates=[response([call()])], max_iterations=1)
        with contextlib.redirect_stdout(io.StringIO()):
            _, output = agent.structured_loop('Question')
        self.assertIsNone(output)
        self.assertEqual([m for m, _ in responses.requests], ['create'])
        self.assertEqual(agent.last_status, 'iteration_limit')

    def test_wrapper_handles_no_parsed_output(self):
        agent, responses = instance(StructuredAgent1, creates=[response([message()])], parses=[response([])])
        with contextlib.redirect_stdout(io.StringIO()):
            _, output = agent.structured_loop('Question')
        self.assertIsNone(output)
        self.assertEqual(agent.last_status, 'incomplete')
        self.assertIsNone(agent.last_answer)

    def test_fake_tool_returns_validated_result_and_acknowledges_call(self):
        agent, responses = instance(StructuredAgent2, creates=[
            response([call()]), response([call('structure_result', PAYLOAD, 'final')]),
            response([call('structure_result', PAYLOAD, 'followup')])])
        with contextlib.redirect_stdout(io.StringIO()):
            history, output = agent.loop('Question')
            agent.loop('Follow-up', history)
        self.assertIsInstance(output, RAGResponse)
        self.assertEqual([m for m, _ in responses.requests], ['create', 'create', 'create'])
        history_sent = responses.requests[-1][1]['input']
        self.assertTrue(any(isinstance(m, dict) and m.get('call_id') == 'final' for m in history_sent))
        self.assertEqual(sum(u['total_tokens'] for u in agent.usage), 90)

    def test_fake_tool_invalid_output_is_correctable(self):
        bad = {**PAYLOAD, 'confidence': 10}
        agent, responses = instance(StructuredAgent2, creates=[
            response([call('structure_result', bad, 'bad')]),
            response([call('structure_result', PAYLOAD, 'fixed')])])
        with contextlib.redirect_stdout(io.StringIO()):
            history, output = agent.loop('Question')
        error_reply = next(m for m in history if isinstance(m, dict) and m.get('call_id') == 'bad')
        self.assertIn('error', json.loads(error_reply['output']))
        self.assertEqual(output.confidence, 0.6)

    def test_fake_tool_mixed_with_research_is_not_accepted_early(self):
        agent, responses = instance(StructuredAgent2, creates=[
            response([call('structure_result', PAYLOAD, 'early'), call(call_id='search')]),
            response([call('structure_result', PAYLOAD, 'complete')])])
        with contextlib.redirect_stdout(io.StringIO()):
            history, output = agent.loop('Question')
        reply = next(m for m in history if isinstance(m, dict) and m.get('call_id') == 'early')
        self.assertIn('error', json.loads(reply['output']))
        self.assertEqual(output.answer, PAYLOAD['answer'])
        self.assertEqual(len(responses.requests), 2)

    def test_fake_tool_plain_text_does_not_finish_structured_loop(self):
        agent, responses = instance(StructuredAgent2, creates=[response([message()])], max_iterations=1)
        with contextlib.redirect_stdout(io.StringIO()):
            _, output = agent.loop('Question')
        self.assertIsNone(output)
        self.assertEqual(agent.last_status, 'iteration_limit')

    def test_structured_qna_keeps_followup_context(self):
        for cls in [StructuredAgent1, StructuredAgent2]:
            if cls is StructuredAgent1:
                agent, responses = instance(cls,
                    creates=[response([message()]), response([message()])],
                    parses=[response([message()], RAGResponse.model_validate(PAYLOAD)),
                            response([message()], RAGResponse.model_validate(PAYLOAD))])
            else:
                agent, responses = instance(cls, creates=[
                    response([call('structure_result', PAYLOAD, 'one')]),
                    response([call('structure_result', PAYLOAD, 'two')])])
            with patch('builtins.input', side_effect=['First', 'Follow-up', 'stop']), contextlib.redirect_stdout(io.StringIO()):
                history = agent.qna()
            self.assertEqual(agent.turn_number, 2)
            self.assertEqual(agent.last_status, 'structured_unreviewed')
            user_messages = [m['content'] for m in history if isinstance(m, dict) and m.get('role') == 'user']
            self.assertEqual(user_messages, ['First', 'Follow-up'])

    def test_fake_tool_schema_and_notebook_library_parity(self):
        tool = create_fake_tool(RAGResponse)
        self.assertTrue(tool['strict'])
        self.assertFalse(tool['parameters']['additionalProperties'])
        self.assertEqual(set(tool['parameters']['required']), set(PAYLOAD))
        names = {'RAGResponse', 'SimpleStructuredAgent', 'StructuredAgent1', 'create_fake_tool', 'StructuredAgent2'}
        expected = {n.name: ast.dump(n) for n in ast.parse((ROOT / 'course_structured_agent.py').read_text()).body
                    if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names}
        notebook = json.loads((ROOT / 'notebooks/02-rag-chemical-triage.ipynb').read_text())
        actual = {}
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code' and 'course-structured-output' in cell.get('metadata', {}).get('tags', []):
                for node in ast.parse(''.join(cell['source'])).body:
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names:
                        actual[node.name] = ast.dump(node)
        self.assertEqual(expected, actual)

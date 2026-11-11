"""Test the course-style notebook loop with scripted Responses outputs, offline."""
import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function_call(name, arguments, call_id):
    return SimpleNamespace(type='function_call', name=name, arguments=json.dumps(arguments), call_id=call_id)


def answer(text='Fixture answer for testing the loop, not a threat assessment.'):
    return SimpleNamespace(type='message', content=[SimpleNamespace(type='output_text', text=text)])


class CourseLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        notebook = json.loads((ROOT / 'notebooks/02-rag-chemical-triage.ipynb').read_text())
        cls.cells = notebook['cells']
        cls.base = {'__name__': '__main__'}
        # Run prerequisites only, without the user-added live RAG question.
        with contextlib.redirect_stdout(io.StringIO()):
            for cell in cls.cells:
                if 'course-agent-loop' in cell.get('metadata', {}).get('tags', []):
                    break
                if cell['cell_type'] == 'code':
                    source = ''.join(cell['source']).replace('RUN_TRIAGE = True', 'RUN_TRIAGE = False')
                    if source.lstrip().startswith('answer = rag('):
                        continue
                    exec(compile(source, 'course-prerequisite', 'exec'), cls.base)

    def prepare(self, responses):
        ns = self.base.copy()
        requests = []
        scripted = iter(responses)

        def create(**kwargs):
            requests.append(copy.deepcopy(kwargs))
            return SimpleNamespace(output=next(scripted), usage=SimpleNamespace(input_tokens=30, output_tokens=10, total_tokens=40))

        ns['OpenAI'] = lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create))
        return ns, requests

    def execute_core(self, ns):
        for cell in self.cells:
            if cell['cell_type'] == 'markdown' and ''.join(cell['source']).startswith('## 12.'):
                break
            if cell['cell_type'] == 'code' and 'course-agent-loop' in cell.get('metadata', {}).get('tags', []):
                source = ''.join(cell['source']).replace('RUN_COURSE_AGENT = False', 'RUN_COURSE_AGENT = True')
                exec(compile(source, 'course-loop', 'exec'), ns)

    def test_one_search_two_searches_then_answer_with_history_and_tokens(self):
        ns, requests = self.prepare([
            [function_call('search', {'query': 'Volt Typhoon'}, 's1')],
            [function_call('search', {'query': 'Volt Typhoon credentials'}, 's2'),
             function_call('search', {'query': 'Volt Typhoon persistence'}, 's3')],
            [answer()],
        ])
        before = json.dumps(ns['documents'], sort_keys=True)
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            self.execute_core(ns)
        self.assertEqual(len(requests), 3)
        self.assertEqual(ns['course_status'], 'answered_unreviewed')
        self.assertEqual(len(ns['course_trace']), 3)
        self.assertEqual(sum(row['total_tokens'] for row in ns['course_usage']), 120)
        results = [m for m in requests[-1]['input'] if isinstance(m, dict) and m.get('type') == 'function_call_output']
        self.assertEqual([r['call_id'] for r in results], ['s1', 's2', 's3'])
        self.assertIn('iteration number 3', capture.getvalue())
        self.assertIn('executing search', capture.getvalue())
        self.assertEqual(before, json.dumps(ns['documents'], sort_keys=True))

    def test_unknown_tool_returns_error_and_model_can_continue(self):
        ns, requests = self.prepare([
            [function_call('missing_tool', {}, 'bad')], [answer('No supported findings.')],
        ])
        with contextlib.redirect_stdout(io.StringIO()):
            self.execute_core(ns)
        result = next(m for m in requests[1]['input'] if isinstance(m, dict) and m.get('type') == 'function_call_output')
        self.assertIn('not found tool', json.loads(result['output'])['error'])
        self.assertEqual(ns['course_status'], 'answered_unreviewed')

    def test_iteration_limit_is_visible_and_stops(self):
        ns, requests = self.prepare([[function_call('search', {'query': 'Volt Typhoon'}, f's{i}')] for i in range(6)])
        with contextlib.redirect_stdout(io.StringIO()):
            self.execute_core(ns)
        self.assertEqual(len(requests), 6)
        self.assertEqual(ns['course_status'], 'iteration_limit')
        self.assertIsNone(ns['course_answer'])

    def test_optional_add_entry_changes_scratch_only(self):
        ns, requests = self.prepare([
            [answer()],
            [function_call('add_entry', {'filename': 'fixture-note', 'title': 'Generated note',
                                        'description': 'Unreviewed exercise', 'content': 'Fixture summary'}, 'note')],
            [answer('Scratch note saved.')],
        ])
        original_count = len(ns['documents'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.execute_core(ns)
            for cell in self.cells:
                if cell['cell_type'] != 'code' or 'course-agent-loop' not in cell.get('metadata', {}).get('tags', []):
                    continue
                source = ''.join(cell['source'])
                if source.startswith('def add_entry(') or source.startswith('def make_call(') and 'elif name == "add_entry"' in source or source.startswith('RUN_COURSE_ADD_ENTRY ='):
                    source = source.replace('RUN_COURSE_ADD_ENTRY = False', 'RUN_COURSE_ADD_ENTRY = True')
                    exec(compile(source, 'course-add-entry', 'exec'), ns)
        self.assertEqual(len(ns['course_index'].docs), original_count + 1)
        self.assertEqual(ns['course_index'].docs[-1]['origin'], 'generated_note')
        self.assertEqual(ns['course_index'].docs[-1]['source_url'], '')
        self.assertEqual(len(ns['documents']), original_count)
        self.assertEqual(len(requests[-1]['tools']), 2)

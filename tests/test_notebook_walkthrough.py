"""Exercise the visible course-style cells with scripted model responses."""
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from tests.notebook_execution import execute_cell

ROOT = Path(__file__).resolve().parents[1]


class NotebookWalkthroughTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        notebook = json.loads((ROOT / 'notebooks/02-rag-chemical-triage.ipynb').read_text())
        cls.cells = notebook['cells']
        cls.namespace = {'__name__': '__main__'}
        with contextlib.redirect_stdout(io.StringIO()):
            for cell in cls.cells:
                if cell['cell_type'] == 'code':
                    if ('live-evaluation' in cell.get('metadata', {}).get('tags', [])
                            or 'await generate_synthetic_cases(' in ''.join(cell['source'])
                            or 'await evaluate_answers(' in ''.join(cell['source'])):
                        continue
                    source = ''.join(cell['source']).replace('RUN_TRIAGE = True', 'RUN_TRIAGE = False')
                    # User-added live RAG demonstrations are not offline test fixtures.
                    if source.lstrip().startswith('answer = rag('):
                        continue
                    execute_cell(source, cls.namespace)

    def run_lesson(self, invalid=False):
        ns = self.namespace.copy()
        requests = []
        quote = ns['documents'][0]['content'][:100]
        chunk_id = ns['documents'][0]['chunk_id']

        def create(**kwargs):
            requests.append(('create', kwargs))
            return SimpleNamespace(
                output=[SimpleNamespace(type='function_call', name='search_reports',
                                        arguments=json.dumps({'query': 'Volt Typhoon'}), call_id='lesson_search')],
                usage=SimpleNamespace(input_tokens=50, output_tokens=20, total_tokens=70))

        def parse(**kwargs):
            requests.append(('parse', kwargs))
            answer = ns['LessonAnswer'].model_validate({
                'claims': [{'statement': 'Fixture claim for validating the mechanics.', 'kind': 'reported_fact',
                            'evidence': [{'chunk_id': chunk_id, 'quote': 'Invented quotation' if invalid else quote}]}],
                'evidence_gaps': ['No internal telemetry.']})
            return SimpleNamespace(output_parsed=answer,
                                   usage=SimpleNamespace(input_tokens=500, output_tokens=100, total_tokens=600))

        fake = SimpleNamespace(responses=SimpleNamespace(create=create, parse=parse))
        ns['OpenAI'] = lambda **kwargs: fake
        # Keep search deterministic while preserving the real corpus and citation checks.
        ns['index'] = SimpleNamespace(search=lambda **kwargs: [ns['documents'][0]])
        with contextlib.redirect_stdout(io.StringIO()):
            for cell in self.cells:
                if cell['cell_type'] == 'code' and 'agent-walkthrough' in cell.get('metadata', {}).get('tags', []):
                    source = ''.join(cell['source']).replace('RUN_AGENT_WALKTHROUGH = False', 'RUN_AGENT_WALKTHROUGH = True')
                    exec(compile(source, 'walkthrough-test', 'exec'), ns)
        return ns, requests

    def test_manual_sequence_shows_results_and_validates_citations(self):
        ns, requests = self.run_lesson()
        self.assertEqual([name for name, _ in requests], ['create', 'parse'])
        outputs = [m for m in requests[1][1]['input'] if isinstance(m, dict) and m.get('type') == 'function_call_output']
        self.assertEqual(outputs[0]['call_id'], 'lesson_search')
        self.assertTrue(ns['lesson_validated_answer'].claims)
        self.assertEqual(sum(u['total_tokens'] for u in ns['lesson_usage']), 670)

    def test_manual_sequence_rejects_invented_quotation(self):
        with self.assertRaisesRegex(ValueError, 'Unverifiable source quotation'):
            self.run_lesson(invalid=True)

    def test_manual_code_is_visible_in_main_project_notebook(self):
        code_cells = [''.join(c['source']) for c in self.cells
                      if c['cell_type'] == 'code'
                      and 'agent-walkthrough' in c.get('metadata', {}).get('tags', [])]
        self.assertGreaterEqual(len(code_cells), 10)
        self.assertTrue(any('lesson_client.responses.create(' in s for s in code_cells))
        self.assertTrue(any('lesson_client.responses.parse(' in s for s in code_cells))
        self.assertTrue(any('validate_evidence(claim.evidence, lesson_retrieved)' in s for s in code_cells))

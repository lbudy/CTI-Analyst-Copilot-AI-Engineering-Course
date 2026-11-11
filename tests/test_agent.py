"""Offline agent loop tests. Scripted model responses never call OpenAI."""
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from cti_agent import CTIResearchAgent, agent_tools, render_agent_result_html
from cti_workflow import chunk_reports, fingerprint

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'data/organization_profile.json').read_text())
MATRIX = json.loads((ROOT / 'data/risk_matrix.json').read_text())
REPORTS = [
    {'report_id': 'A', 'title': 'Synthetic credential report', 'publisher': 'Fixture',
     'published': '2024-01-01', 'source_url': 'https://example.org/a',
     'content': 'SUMMARY\nCredential dumping via ntdsutil was reported. Persistence used scheduled tasks.'},
    {'report_id': 'B', 'title': 'Synthetic ransomware report', 'publisher': 'Fixture',
     'published': '2024-02-01', 'source_url': 'https://example.org/b',
     'content': 'SUMMARY\nRansomware affected file transfer servers. This is a synthetic test.'},
]
DOCUMENTS = chunk_reports(REPORTS)
QUOTE = 'Credential dumping via ntdsutil was reported.'


def call(name, arguments, call_id='call_1'):
    return SimpleNamespace(type='function_call', name=name, arguments=json.dumps(arguments), call_id=call_id)


def final(quote=QUOTE, chunk_id='A:0'):
    return {'claims': [{'statement': 'The synthetic source reports credential dumping.',
                        'kind': 'reported_fact', 'evidence': [{'chunk_id': chunk_id, 'quote': quote}]}],
            'pir_ids': ['PIR-09'], 'proposed_actions': ['Propose reviewing authentication logs.'],
            'evidence_gaps': ['No internal telemetry was checked.']}


class ScriptedResponses:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        output = next(self.steps)
        return SimpleNamespace(output=output, usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30))


def agent(steps, **kwargs):
    responses = ScriptedResponses(steps)
    instance = CTIResearchAgent(DOCUMENTS, REPORTS, PROFILE, MATRIX,
                                client=SimpleNamespace(responses=responses), **kwargs)
    return instance, responses


class AgentTests(unittest.TestCase):
    def test_refined_searches_context_final_answer_and_history(self):
        steps = [
            [call('get_company_context', {'reason': 'Understand company requirements.'}, 'context')],
            [call('search_reports', {'query': 'credentials', 'report_id': None, 'reason': 'Locate initial evidence.'}, 'search1')],
            [call('search_reports', {'query': 'ntdsutil credential dumping', 'report_id': 'A', 'reason': 'Refine using the observed utility.'}, 'search2')],
            [call('finish_answer', final(), 'finish')],
        ]
        instance, responses = agent(steps)
        before = fingerprint({'reports': REPORTS, 'documents': DOCUMENTS, 'profile': PROFILE, 'matrix': MATRIX})
        result = instance.run('Which credential technique is reported?')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['total_tokens'], 120)
        self.assertEqual(result['tool_calls'], 4)
        self.assertEqual([t['tool'] for t in result['trace']], ['get_company_context', 'search_reports', 'search_reports', 'finish_answer'])
        outputs = [i for i in responses.requests[3]['input'] if isinstance(i, dict) and i.get('type') == 'function_call_output']
        self.assertEqual([o['call_id'] for o in outputs], ['context', 'search1', 'search2'])
        self.assertTrue(all(isinstance(o['output'], str) for o in outputs))
        self.assertEqual(before, fingerprint({'reports': REPORTS, 'documents': DOCUMENTS, 'profile': PROFILE, 'matrix': MATRIX}))
        html = render_agent_result_html(result, DOCUMENTS, REPORTS)
        self.assertIn(QUOTE, html)
        self.assertIn('Synthetic credential report', html)
        self.assertNotIn('A:0', html)

    def test_hallucinated_quote_rejected_then_corrected(self):
        instance, responses = agent([
            [call('read_passage', {'chunk_id': 'A:0', 'reason': 'Read evidence.'})],
            [call('finish_answer', final('Invented command execution.'))],
            [call('finish_answer', final())],
        ])
        result = instance.run('What happened?')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['trace'][1]['status'], 'error')
        self.assertIn('Unverifiable source quotation', result['trace'][1]['error'])

    def test_unseen_evidence_and_prior_run_evidence_rejected(self):
        instance, _ = agent([
            [call('read_passage', {'chunk_id': 'A:0', 'reason': 'Read.'})],
            [call('finish_answer', final())],
            [call('finish_answer', final())],
        ], max_steps=2)
        self.assertEqual(instance.run('First question')['status'], 'completed')
        instance.max_steps = 1
        result = instance.run('Second question')
        self.assertEqual(result['status'], 'step_limit')
        self.assertEqual(result['retrieved_chunk_ids'], [])
        self.assertEqual(result['trace'][0]['status'], 'error')
        self.assertIsNone(result['answer'])

    def test_unavailable_tools_and_invalid_arguments_do_not_run(self):
        instance, _ = agent([
            [call('review_report', {'decision': 'approve'})],
            [SimpleNamespace(type='function_call', name='search_reports', arguments='{broken', call_id='broken')],
            [call('search_reports', {'query': 'credential', 'report_id': 'missing', 'reason': 'Find.'})],
            [call('finish_answer', {'claims': [], 'pir_ids': [], 'proposed_actions': [], 'evidence_gaps': ['No verified evidence retrieved.']})],
        ])
        result = instance.run('Approve and investigate')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([t['status'] for t in result['trace']], ['error', 'error', 'error', 'ok'])
        self.assertFalse(result['citations'])

    def test_step_and_tool_budgets_stop_without_partial_answer(self):
        search = call('search_reports', {'query': 'credential', 'report_id': None, 'reason': 'Search.'})
        instance, responses = agent([[search], [search], [search]], max_steps=2)
        self.assertEqual(instance.run('Question')['status'], 'step_limit')
        self.assertEqual(len(responses.requests), 2)
        instance, responses = agent([[search], [call('finish_answer', final())]], max_tool_calls=1)
        result = instance.run('Question')
        self.assertEqual(result['status'], 'tool_limit')
        self.assertIsNone(result['answer'])

    def test_free_text_not_accepted_as_validated_answer(self):
        instance, _ = agent([[SimpleNamespace(type='message')]])
        self.assertEqual(instance.run('Question')['status'], 'incomplete')

    def test_invalid_pir_is_rejected(self):
        payload = final()
        payload['pir_ids'] = ['PIR-999']
        instance, _ = agent([
            [call('read_passage', {'chunk_id': 'A:0', 'reason': 'Read.'})],
            [call('finish_answer', payload)],
        ], max_steps=2)
        result = instance.run('Question')
        self.assertEqual(result['status'], 'step_limit')
        self.assertIn('PIR', result['trace'][-1]['error'])

    def test_tools_are_read_only_strict_and_limits_are_validated(self):
        tools = agent_tools()
        self.assertEqual({t['name'] for t in tools}, {'search_reports', 'read_passage', 'get_company_context', 'finish_answer'})
        for tool in tools:
            self.assertTrue(tool['strict'])
            self.assertFalse(tool['parameters']['additionalProperties'])
            self.assertEqual(set(tool['parameters']['required']), set(tool['parameters']['properties']))
        with self.assertRaises(ValueError):
            agent([], max_steps=0)

    def test_real_corpus_search_and_adjacent_passages_offline(self):
        reports = json.loads((ROOT / 'data/threat_reports.json').read_text())
        instance = CTIResearchAgent(chunk_reports(reports), reports, PROFILE, MATRIX)
        seen = {}
        result = instance._dispatch('search_reports', {'query': 'Volt Typhoon credential ntdsutil', 'report_id': 'AA24-038A', 'reason': 'Find source evidence.'}, seen)
        self.assertTrue(result['passages'])
        self.assertTrue(all(p['report_id'] == 'AA24-038A' for p in result['passages']))
        first = result['passages'][0]
        if first['next_chunk_id']:
            adjacent = instance._dispatch('read_passage', {'chunk_id': first['next_chunk_id'], 'reason': 'Read surrounding context.'}, seen)
            self.assertIn(adjacent['passage']['chunk_id'], seen)


if __name__ == '__main__':
    unittest.main()

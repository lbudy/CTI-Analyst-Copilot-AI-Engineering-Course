import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cti_workflow import (Workflow, TriageAssessment, ProcessedReport, chunk_reports,
                          calculate_score, validate_triage, fingerprint)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / 'data/organization_profile.json').read_text())
MATRIX = json.loads((ROOT / 'data/risk_matrix.json').read_text())
REPORT = {'report_id': 'TEST', 'title': 'Synthetic test report', 'publisher': 'Fixture',
          'published': '2024-01-01', 'source_url': 'https://example.org/test',
          'content': 'Synthetic chemical sector incident. CVE-2099-0001 was reported.'}
CHUNKS = chunk_reports([REPORT])
EVIDENCE = {'chunk_id': 'TEST:0', 'quote': 'Synthetic chemical sector incident.'}


def assessment():
    ratings = [None, 4, 3, 3, 2, 3, 4, None, 4]
    return TriageAssessment.model_validate({
        'report_id': 'TEST',
        'criteria': [{'criterion_id': c['criterion_id'], 'rating': r,
                      'rationale': 'Synthetic test reasoning',
                      'judgment': 'unknown' if r is None else 'inference',
                      'confidence': 'low', 'evidence': [] if r is None else [EVIDENCE],
                      'profile_fields': ['sector'],
                      'unknowns': ['Missing exposure'] if r is None else []}
                     for c, r in zip(MATRIX['criteria'], ratings)],
        'pir_mappings': [{'pir_id': 'PIR-01', 'rationale': 'Test sector match',
                          'answers': 'Fixture', 'gaps': [], 'confidence': 'low',
                          'evidence': [EVIDENCE]}],
        'escalations': [], 'evidence_gaps': ['Synthetic fixture only']})


def processed():
    return ProcessedReport.model_validate({
        'report_id': 'TEST', 'summary': 'Synthetic incident.', 'summary_evidence': [EVIDENCE],
        'facts': [{'category': 'cve', 'value': 'CVE-2099-0001', 'explanation': 'Fixture identifier',
                   'evidence': [{'chunk_id': 'TEST:0', 'quote': 'CVE-2099-0001 was reported.'}]}],
        'proposed_actions': [{'team': 'hunting', 'proposal': 'Review relevant logs',
                              'required_telemetry': ['Authentication logs'],
                              'evidence': [EVIDENCE], 'limitations': ['No real incident']}],
        'evidence_gaps': []})


class FakeResponses:
    def __init__(self):
        self.calls = []
        self.bad_entity = False

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        result = assessment() if kwargs['text_format'] is TriageAssessment else processed()
        if self.bad_entity and isinstance(result, ProcessedReport):
            result.facts[0].value = 'CVE-2099-9999'
        return SimpleNamespace(output_parsed=result,
                               usage=SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150))


class WorkflowTests(unittest.TestCase):
    def workflow(self, audit=None):
        self.fake = FakeResponses()
        return Workflow([copy.deepcopy(REPORT)], copy.deepcopy(PROFILE), copy.deepcopy(MATRIX),
                        audit_path=audit, client=SimpleNamespace(responses=self.fake))

    def test_unknown_range_and_priority(self):
        result = calculate_score(assessment(), MATRIX)
        self.assertEqual(result['minimum_score'], 63.25)
        self.assertEqual(result['maximum_score'], 86.25)
        self.assertEqual(result['evidence_coverage_percent'], 77)
        self.assertEqual(result['proposed_priority'], 'P2')
        self.assertEqual(result['possible_priority'], 'P1')
        self.assertTrue(result['priority_uncertain'])

    def test_unsupported_quote_pir_and_criterion_rejected(self):
        for mutate in [lambda a: setattr(a.criteria[1].evidence[0], 'quote', 'Invented text'),
                       lambda a: setattr(a.pir_mappings[0], 'pir_id', 'PIR-99'),
                       lambda a: a.criteria.pop()]:
            a = assessment()
            mutate(a)
            with self.assertRaises(ValueError):
                validate_triage(a, CHUNKS, PROFILE, MATRIX)

    def test_unknown_not_allowed_to_be_silent_zero(self):
        a = assessment()
        a.criteria[0].rating = 0
        with self.assertRaises(ValueError):
            validate_triage(a, CHUNKS, PROFILE, MATRIX)

    def test_gates_token_usage_and_local_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            w = self.workflow(Path(directory) / 'audit.json')
            with self.assertRaises(ValueError):
                w.process_report('TEST')
            self.assertFalse(self.fake.calls)
            w.triage_all()
            payload = json.loads(self.fake.calls[0]['input'][1]['content'])
            self.assertEqual(payload['report_chunks'], CHUNKS)
            w.review_report('TEST', 'defer', 'Analyst', 'Need more information')
            with self.assertRaises(ValueError):
                w.process_report('TEST')
            w.review_report('TEST', 'approve', 'Analyst', 'Reviewed', priority='P1')
            w.process_report('TEST')
            with self.assertRaises(ValueError):
                w.export_reviewed('TEST', Path(directory) / 'export.json')
            w.review_output('TEST', 'approve', 'Analyst', 'Evidence checked')
            w.export_reviewed('TEST', Path(directory) / 'export.json')
            self.assertTrue((Path(directory) / 'export.json').exists())
            self.assertEqual(len(json.loads((Path(directory) / 'audit.json').read_text())), 3)
            self.assertEqual(sum(u['total_tokens'] for u in w.usage), 300)
            w.review_report('TEST', 'reject', 'Analyst', 'Reconsidered')
            with self.assertRaises(ValueError):
                w.export_reviewed('TEST', Path(directory) / 'other.json')

    def test_changed_profile_invalidates_approval(self):
        w = self.workflow()
        w.triage_report('TEST')
        w.review_report('TEST', 'approve', 'Analyst', 'Reviewed')
        w.profile['sector'] = 'Changed'
        with self.assertRaises(ValueError):
            w.process_report('TEST')

    def test_invented_identifier_rejected(self):
        w = self.workflow()
        w.triage_report('TEST')
        w.review_report('TEST', 'approve', 'Analyst', 'Reviewed')
        self.fake.bad_entity = True
        with self.assertRaises(ValueError):
            w.process_report('TEST')
        self.assertNotIn('TEST', w.processed)

    def test_failed_report_remains_visible(self):
        w = self.workflow()
        self.fake.parse = lambda **kwargs: (_ for _ in ()).throw(ValueError('Fixture failure'))
        rows = w.triage_all()
        self.assertEqual(rows[0]['status'], 'failed')
        with self.assertRaises(ValueError):
            w.review_report('TEST', 'approve', 'Analyst', 'Cannot approve failure')

    def test_complete_real_corpus_preserves_chunking_and_retrieval(self):
        from minsearch import Index
        reports = json.loads((ROOT / 'data/threat_reports.json').read_text())
        chunks = chunk_reports(reports)
        index = Index(text_fields=['title', 'content'], keyword_fields=['report_id', 'chunk_id'])
        index.fit(chunks)
        results = index.search('Volt Typhoon Windows credential access persistence', num_results=5)
        self.assertEqual(len(results), 5)
        self.assertTrue(any('Volt Typhoon' in c['content'] for c in results))
        w = Workflow(reports, PROFILE, MATRIX, documents=chunks)
        for report in reports:
            selected = w._chunks(report['report_id'])
            self.assertTrue(selected)
        print(f'Offline corpus verification: {len(reports)} reports, {len(chunks)} chunks.')


if __name__ == '__main__':
    unittest.main()

class ConservativeEvidenceTests(unittest.TestCase):
    def test_unverifiable_rating_is_unknown_with_warning(self):
        from cti_workflow import prepare_assessment
        a = assessment()
        a.criteria[1].evidence[0].quote = 'Invented text'
        warnings = prepare_assessment(a, CHUNKS)
        self.assertIsNone(a.criteria[1].rating)
        self.assertEqual(a.criteria[1].judgment, 'unknown')
        self.assertTrue(warnings)
        validate_triage(a, CHUNKS, PROFILE, MATRIX)

    def test_whitespace_restoration_preserves_original_passage(self):
        from cti_workflow import prepare_assessment
        a = assessment()
        chunks = copy.deepcopy(CHUNKS)
        chunks[0]['content'] = 'Synthetic chemical\nsector incident. CVE-2099-0001 was reported.'
        prepare_assessment(a, chunks)
        self.assertEqual(a.criteria[1].evidence[0].quote, 'Synthetic chemical\nsector incident.')
        validate_triage(a, chunks, PROFILE, MATRIX)

    def test_snapshot_can_be_reused_and_changes_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            w = Workflow([REPORT], PROFILE, MATRIX)
            a = assessment()
            entry = {'assessment': a.model_dump(), 'score': calculate_score(a, MATRIX),
                     'validation_warnings': [], 'report_hash': fingerprint(REPORT),
                     'context_hash': w.context_hash}
            entry['triage_hash'] = fingerprint(entry)
            path = Path(directory) / 'snapshot.json'
            path.write_text(json.dumps({'triage': {'TEST': entry}, 'usage': []}))
            self.assertEqual(w.load_unreviewed(path)[0]['status'], 'triaged')
            self.assertIsNone(w.queue()[0]['analyst_decision'])
            entry['score']['minimum_score'] = 100
            path.write_text(json.dumps({'triage': {'TEST': entry}, 'usage': []}))
            with self.assertRaises(ValueError):
                w.load_unreviewed(path)

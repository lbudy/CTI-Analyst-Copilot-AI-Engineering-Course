"""Verify every new PDF uses the original report → chunk → index → RAG contracts."""
import ast
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest

from cti_workflow import (Workflow, Evidence, ProcessedReport, analyst_citations,
                          chunk_reports, validate_evidence, validate_reports)

ROOT = Path(__file__).resolve().parents[1]
CORE_FIELDS = {'report_id', 'title', 'publisher', 'published', 'source_url', 'content'}
QUERIES = {
    'AA24-109A': 'Akira ransomware VMware ESXi',
    'AA24-242A': 'RansomHub ransomware',
    'AA24-131A': 'Black Basta ransomware',
    'AA23-320A': 'Scattered Spider social engineering',
    'AA23-319A': 'Rhysida ransomware',
    'AA25-071A': 'Medusa ransomware',
    'AA23-165A': 'LockBit ransomware',
    'AA23-136A': 'BianLian data extortion',
    'AA23-335A': 'IRGC Unitronics PLC',
    'AA23-061A': 'BlackSuit Royal ransomware',
}


def foundation_namespace(path):
    notebook = json.loads(path.read_text())
    namespace = {'__name__': '__main__'}
    with contextlib.redirect_stdout(io.StringIO()):
        for cell in notebook['cells']:
            source = ''.join(cell['source'])
            if cell['cell_type'] == 'markdown' and source.startswith('## 4.'):
                break
            if cell['cell_type'] == 'code':
                exec(compile(source, str(path), 'exec'), namespace)
    return namespace


class CorpusPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespaces = {p.name: foundation_namespace(p) for p in (ROOT / 'notebooks').glob('02-rag*.ipynb')}
        cls.reports = json.loads((ROOT / 'data/threat_reports.json').read_text())

    def test_all_reports_share_the_original_contract_and_exact_chunking(self):
        canonical = chunk_reports(self.reports)
        self.assertEqual(len(canonical), 242)
        for namespace in self.namespaces.values():
            self.assertEqual(namespace['documents'], canonical)
            self.assertEqual(len(namespace['pipeline_audit']), 13)
            for report in self.reports:
                self.assertTrue(CORE_FIELDS <= report.keys())
                chunks = [c for c in namespace['documents'] if c['report_id'] == report['report_id']]
                restored = chunks[0]['content'] + ''.join(c['content'][500:] for c in chunks[1:])
                self.assertEqual(restored, report['content'])
                for chunk in chunks:
                    offset = int(chunk['chunk_id'].rsplit(':', 1)[1])
                    self.assertEqual(chunk['content'], report['content'][offset:offset + 3000])
                    self.assertLessEqual(len(chunk['content']), 3000)
                    self.assertIn('section_headings', chunk)
                    for field in CORE_FIELDS - {'content'}:
                        self.assertEqual(chunk[field], report[field])

    def test_all_ten_are_retrieved_by_original_search_and_enter_original_prompt(self):
        for namespace in self.namespaces.values():
            for report_id, question in QUERIES.items():
                matches = namespace['search'](question)
                self.assertEqual(len(matches), 5)
                self.assertIn(report_id, {c['report_id'] for c in matches})
                prompt = namespace['build_prompt'](question, matches)
                self.assertIn(question, prompt)
                self.assertIn('<ORGANIZATION_PROFILE>', prompt)
                data = json.loads(prompt.split('<REPORT_CHUNKS>')[1].split('</REPORT_CHUNKS>')[0])
                self.assertEqual(data, matches)
                target = next(c for c in data if c['report_id'] == report_id)
                report = next(r for r in self.reports if r['report_id'] == report_id)
                self.assertEqual(target['source_url'], report['source_url'])
                self.assertEqual(target.get('updated'), report.get('updated'))
                self.assertIn('exact supporting quotation', namespace['instructions'])

    def test_original_rag_chain_runs_for_each_new_report_with_a_stub_llm(self):
        for namespace in self.namespaces.values():
            calls = []
            original = namespace['llm']
            def fake_llm(prompt, instructions=None):
                calls.append((prompt, instructions))
                return 'Offline pipeline verification only; no generated threat assessment.'
            namespace['llm'] = fake_llm
            try:
                for report_id, question in QUERIES.items():
                    result = namespace['rag'](question)
                    self.assertIn('Offline pipeline verification', result)
                    self.assertIn(report_id, calls[-1][0])
                    self.assertEqual(calls[-1][1], namespace['instructions'])
                self.assertEqual(len(calls), 10)
            finally:
                namespace['llm'] = original

    def test_new_reports_fit_evidence_and_processing_structures_without_bypassing_review(self):
        profile = json.loads((ROOT / 'data/organization_profile.json').read_text())
        matrix = json.loads((ROOT / 'data/risk_matrix.json').read_text())
        documents = chunk_reports(self.reports)
        workflow = Workflow(self.reports, profile, matrix, documents=documents)
        for report_id in QUERIES:
            chunks = workflow._chunks(report_id)
            evidence = Evidence(chunk_id=chunks[0]['chunk_id'], quote=chunks[0]['content'][:100])
            validate_evidence([evidence], chunks)
            # This is a shape/provenance check, not a model-produced assessment.
            record = ProcessedReport(report_id=report_id, summary=evidence.quote,
                                     summary_evidence=[evidence], facts=[], proposed_actions=[], evidence_gaps=[])
            citations = analyst_citations(record.model_dump(), chunks, self.reports)
            self.assertEqual(len(citations), 1)
            self.assertEqual(citations[0]['quote'], evidence.quote)
            self.assertEqual(citations[0]['report_id'], report_id)
            with self.assertRaisesRegex(ValueError, 'approval'):
                workflow.process_report(report_id)
        self.assertIsNone(workflow.client)
        self.assertFalse(workflow.processed)

    def test_invalid_report_contract_fails_before_indexing(self):
        valid = self.reports[0]
        for mutate in [lambda r: r.pop('source_url'), lambda r: r.update(content=' '),
                       lambda r: r.update(published='not a date'),
                       lambda r: r.update(source_url='not a URL')]:
            changed = copy.deepcopy(valid)
            mutate(changed)
            with self.assertRaises(ValueError):
                validate_reports([changed])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_reports([valid, valid])

    def test_pdf_heading_case_is_preserved_and_revisions_are_visible(self):
        report = next(r for r in self.reports if r['report_id'] == 'AA24-109A')
        from cti_workflow import report_sections, render_evidence_html
        sections = report_sections(report)
        self.assertTrue(any(s['heading'] == 'Summary' for s in sections))
        chunk = chunk_reports([report])[0]
        record = {'chunk_id': chunk['chunk_id'], 'quote': chunk['content'][:100]}
        html = render_evidence_html(record, [chunk], [report])
        self.assertIn('Updated 2025-11-13', html)

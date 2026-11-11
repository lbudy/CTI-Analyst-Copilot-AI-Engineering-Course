import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.ingest_report_pdfs import extract_report, ingest
from cti_workflow import chunk_reports

ROOT = Path(__file__).resolve().parents[1]


class PDFCorpusTests(unittest.TestCase):
    def test_ten_original_pdfs_and_provenance_match_corpus(self):
        catalog = json.loads((ROOT / 'data/report_sources.json').read_text())
        manifest = json.loads((ROOT / 'data/source_reports/manifest.json').read_text())
        reports = json.loads((ROOT / 'data/threat_reports.json').read_text())
        self.assertEqual(len(catalog), 10)
        self.assertEqual(len(manifest), 10)
        self.assertEqual(len(reports), 13)
        self.assertEqual(len({r['report_id'] for r in reports}), 13)
        by_id = {r['report_id']: r for r in reports}
        self.assertTrue({'AA24-038A', 'AA23-144A', 'AA23-158A'} <= by_id.keys())
        for entry in manifest:
            raw = (ROOT / entry['local_pdf']).read_bytes()
            self.assertTrue(raw.startswith(b'%PDF-'))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['pdf_sha256'])
            content = by_id[entry['report_id']]['content']
            self.assertEqual(hashlib.sha256(content.encode()).hexdigest(), entry['content_sha256'])
            self.assertEqual(len(entry['page_spans']), entry['page_count'])
            self.assertEqual(entry['page_spans'][0]['start'], 0)
            self.assertEqual(entry['page_spans'][-1]['end'], len(content))
        self.assertEqual(len(chunk_reports(reports)), 242)

    def test_offline_ingestion_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'pdfs'
            source.mkdir()
            for path in (ROOT / 'data/source_reports').glob('*.pdf'):
                shutil.copyfile(path, source / path.name)
            corpus = folder / 'reports.json'
            shutil.copyfile(ROOT / 'data/threat_reports.json', corpus)
            before = json.loads(corpus.read_text())
            result = ingest(ROOT / 'data/report_sources.json', corpus, source)
            self.assertEqual(result['added'], 0)
            self.assertEqual(json.loads(corpus.read_text()), before)

    def test_wrong_advisory_id_is_rejected(self):
        spec = json.loads((ROOT / 'data/report_sources.json').read_text())[0]
        spec['report_id'] = 'AA99-999Z'
        with self.assertRaisesRegex(ValueError, 'Advisory ID'):
            extract_report(spec, ROOT / 'data/source_reports/AA24-109A.pdf')

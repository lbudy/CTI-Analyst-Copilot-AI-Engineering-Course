"""Load downloaded public PDFs into the existing corpus without changing old records.

Offline rebuild: uv run python scripts/ingest_report_pdfs.py
Explicit re-download: uv run python scripts/ingest_report_pdfs.py --download
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def extract_report(spec, pdf_path):
    raw = pdf_path.read_bytes()
    if not raw.startswith(b'%PDF-'):
        raise ValueError(f'{pdf_path.name} is not a PDF.')
    reader = PdfReader(pdf_path)
    pages = [(page.extract_text() or '').strip() for page in reader.pages]
    content = '\n\n'.join(pages)
    # Validate the advisory identity from the actual PDF, not its filename or URL.
    compact = re.sub(r'\s+', '', content[:12000]).replace('—', '-').replace('–', '-')
    if spec['report_id'] not in compact:
        raise ValueError(f'Advisory ID does not match PDF: {spec["report_id"]}')
    if len(content) < 3000 or any(not page for page in pages):
        raise ValueError(f'Insufficient text extraction: {pdf_path.name}; inspect for scanned pages.')
    for field in ['published', 'snapshot_date']:
        date.fromisoformat(spec[field])
    if spec.get('updated'):
        date.fromisoformat(spec['updated'])
    report = {k: spec[k] for k in ['report_id', 'title', 'publisher', 'published', 'source_url']}
    report.update({
        'content': content,
        'updated': spec.get('updated'),
        'retrieved_on': spec['snapshot_date'],
        'source_format': 'pdf',
        'local_pdf': f'data/source_reports/{pdf_path.name}',
        'page_count': len(pages),
        'extraction_method': 'pypdf: per-page extract_text, strip outer whitespace, join with two newlines',
    })
    offset = 0
    page_spans = []
    for number, text in enumerate(pages, 1):
        page_spans.append({'page': number, 'start': offset, 'end': offset + len(text)})
        offset += len(text) + 2
    provenance = {
        'report_id': spec['report_id'], 'source_url': spec['source_url'],
        'snapshot_date': spec['snapshot_date'], 'local_pdf': report['local_pdf'],
        'pdf_sha256': sha256(raw), 'content_sha256': sha256(content.encode()),
        'bytes': len(raw), 'page_count': len(pages), 'text_characters': len(content),
        'page_spans': page_spans,
    }
    return report, provenance


def ingest(catalog_path=ROOT / 'data/report_sources.json',
           corpus_path=ROOT / 'data/threat_reports.json',
           source_dir=ROOT / 'data/source_reports', download=False):
    catalog = json.loads(Path(catalog_path).read_text())
    corpus_path, source_dir = Path(corpus_path), Path(source_dir)
    reports = json.loads(corpus_path.read_text())
    by_id = {r['report_id']: r for r in reports}
    if len(by_id) != len(reports) or len({s['report_id'] for s in catalog}) != len(catalog):
        raise ValueError('Duplicate report IDs in corpus or catalog.')
    source_dir.mkdir(parents=True, exist_ok=True)
    additions, manifest = [], []
    for spec in catalog:
        if not re.fullmatch(r'AA\d{2}-\d{3}[A-Z]', spec['report_id']):
            raise ValueError('Invalid advisory ID.')
        pdf_path = source_dir / f'{spec["report_id"]}.pdf'
        if download:
            # Download only the explicitly selected official publisher URL.
            parsed = urllib.parse.urlparse(spec['source_url'])
            if parsed.scheme != 'https' or parsed.hostname != 'www.ic3.gov':
                raise ValueError('Expected an official HTTPS IC3 source URL.')
            request = urllib.request.Request(spec['source_url'], headers={'User-Agent': 'CTI-Course-Research/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(20_000_001)
            if len(data) > 20_000_000 or not data.startswith(b'%PDF-'):
                raise ValueError('Invalid or oversized PDF download.')
            if pdf_path.exists() and sha256(pdf_path.read_bytes()) != sha256(data):
                raise ValueError('Publisher PDF changed; review a new snapshot before replacing it.')
            pdf_path.write_bytes(data)
        report, provenance = extract_report(spec, pdf_path)
        # Existing evidence is immutable; a revision requires explicit separate handling.
        if report['report_id'] in by_id:
            if by_id[report['report_id']] != report:
                raise ValueError(f'Existing report differs: {report["report_id"]}; refusing to overwrite.')
        else:
            additions.append(report)
        manifest.append(provenance)
    # Only update the corpus after every source has passed validation.
    corpus_path.write_text(json.dumps(reports + additions, indent=2, ensure_ascii=False) + '\n')
    (source_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for record in manifest:
        rid = record['report_id']
        text = next(r['content'] for r in reports + additions if r['report_id'] == rid)
        (source_dir / f'{rid}.txt').write_text(text + '\n')
    return {'added': len(additions), 'total_reports': len(reports) + len(additions),
            'pdfs_verified': len(manifest)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Explicitly download selected PDFs; default is offline extraction.')
    print(json.dumps(ingest(download=parser.parse_args().download), indent=2))

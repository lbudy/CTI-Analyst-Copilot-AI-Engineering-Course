"""Course project module: validated local CTI reports, search, and full-text retrieval."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from minsearch import AppendableIndex, Highlighter, Tokenizer
from minsearch.tokenizer import DEFAULT_ENGLISH_STOP_WORDS
from cti_workflow import validate_reports
from pydantic_search_tools import SearchTools

ROOT = Path(__file__).resolve().parent


def load_reports(path=None):
    return validate_reports(json.loads(Path(path or ROOT / 'data/threat_reports.json').read_text()))


def build_index(reports):
    documents = [{**r, 'filename': f"{r['report_id']}.txt",
                  'description': r.get('publisher', '')} for r in reports]
    index = AppendableIndex(text_fields=['title', 'description', 'content'], keyword_fields=['filename'])
    index.fit(documents)
    return index, {d['filename']: d['content'] for d in documents}


def create_highlighter():
    return Highlighter(highlight_fields=['content'], max_matches=3, snippet_size=50,
                       tokenizer=Tokenizer(stemmer='snowball', stop_words=DEFAULT_ENGLISH_STOP_WORDS))


@lru_cache(maxsize=4)
def _tools_for_snapshot(path, digest):
    reports = load_reports(path)
    index, file_index = build_index(reports)
    return SearchTools(index, create_highlighter(), file_index)


def create_documentation_tools_cached(path=None):
    """Content-keyed memory cache; changed corpus automatically rebuilds the index."""
    path = Path(path or ROOT / 'data/threat_reports.json').resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return _tools_for_snapshot(str(path), digest)

"""Run analytical production only using current skill, source and saved upstream records."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from cti_workflow import Workflow, fingerprint, validate_evidence, ProcessedReport
from models import RAGResponse
from tools import load_reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-id', default='AA24-109A')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    output = ROOT / 'outputs/skill_runs' / args.report_id
    profile = json.loads((ROOT / 'data/organization_profile.json').read_text())
    matrix = json.loads((ROOT / 'data/risk_matrix.json').read_text())
    workflow = Workflow(load_reports(), profile, matrix, audit_path=output/'analyst_decisions.json')
    workflow.load_unreviewed(output/'unreviewed_triage.json')
    workflow._require_approval(args.report_id)
    chunks = workflow._chunks(args.report_id)
    processed = ProcessedReport.model_validate(json.loads((output/'technical_extraction.json').read_text()))
    validate_evidence(processed.summary_evidence, chunks)
    for fact in processed.facts:
        validate_evidence(fact.evidence, chunks)
    skill_path = ROOT / 'skills/cti-analytical-production/SKILL.md'
    skill = skill_path.read_text()
    notes = {}
    for filename in ['quality_review.json', 'downstream_quality_notes.json']:
        path = output/filename
        if path.exists():
            notes[filename] = json.loads(path.read_text())
    payload = {'report': workflow.reports[args.report_id], 'report_chunks': chunks,
        'organization_profile': profile, 'risk_matrix': matrix,
        'triage': workflow.triage[args.report_id], 'technical_extraction': processed.model_dump(),
        'upstream_quality_review': notes,
        'analyst_decisions': workflow.events,
        'technical_record_paths': ['technical_extraction.md','technical_extraction.json']}
    print('Running updated analytical-production skill on',args.report_id,flush=True)
    result = workflow._call(RAGResponse, skill + '''

Return the complete draft in answer, following every requested section.
The supplied original report and chunks are authoritative over generated upstream summaries.
Prior review identified unsupported chemical-specific targeting and missing extracted TTPs.
Do not inherit those errors. Preserve upstream scoring verbatim and label it provisional,
not a probability or an established urgency rating. Treat approval to process as distinct
from finished-output approval. Quote short exact source substrings and identify report/chunk.
''',payload,'analytical-production',args.report_id)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = output/f'analytical_production_{run_id}.md'
    path.write_text(result.answer+'\n')
    (output/'analytical_production_updated.md').write_text(result.answer+'\n')
    (output/f'analytical_production_{run_id}.json').write_text(result.model_dump_json(indent=2)+'\n')
    headings=['BLUF','Description','So what','Tradecraft review','Sourcing','Evidence references','Open review issues']
    checks={'requested_sections_present':{h:h.lower() in result.answer.lower() for h in headings},
            'content_review':'pending; section checks do not establish factual correctness'}
    manifest={'run_id':run_id,'report_id':args.report_id,'skill_path':str(skill_path.relative_to(ROOT)),
              'skill_hash':fingerprint(skill),'source_hash':fingerprint(workflow.reports[args.report_id]),
              'upstream_triage_hash':workflow.triage[args.report_id]['triage_hash'],
              'upstream_extraction_hash':fingerprint(processed.model_dump()),
              'model':workflow.model,'usage':workflow.usage[-1:], 'checks':checks,
              'output':str(path.relative_to(ROOT)), 'output_review':'pending'}
    (output/f'analytical_run_{run_id}.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2),flush=True)


if __name__=='__main__':
    main()

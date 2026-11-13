"""Continue a saved triage through technical and BLUF skills after recorded approval."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from cti_workflow import Workflow, fingerprint, ProcessedReport, SupportedFact, ProposedAction
from pydantic import BaseModel, ConfigDict
from models import RAGResponse
from tools import load_reports


class EvidenceChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    passage_id: str


class FactDraft(SupportedFact):
    evidence: list[EvidenceChoice]


class ActionDraft(ProposedAction):
    evidence: list[EvidenceChoice]


class ExtractionDraft(ProcessedReport):
    summary_evidence: list[EvidenceChoice]
    facts: list[FactDraft]
    proposed_actions: list[ActionDraft]


class SkillProcessingWorkflow(Workflow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.skill_runs = []
        self.evidence_repairs = []

    def _call(self, schema, instructions, payload, stage, report_id):
        names = {'processing': 'cti-technical-extraction', 'production': 'cti-analytical-production'}
        path = ROOT / 'skills' / names[stage] / 'SKILL.md'
        skill = path.read_text()
        if stage == 'processing':
            passages = {chunk['chunk_id']: {'chunk_id': chunk['chunk_id'], 'quote': chunk['content']}
                        for chunk in self._chunks(report_id)}
            payload = {**payload}
            payload.pop('report_chunks', None)
            payload['evidence_passages'] = [{'passage_id': key, **value} for key,value in passages.items()]
            instructions += ("\nFor this call, select passage_id values from evidence_passages instead of copying quotations. "
                             "Code resolves them to exact source text. Each named fact.value must occur exactly "
                             "in its selected passage. Do not invent IDs. Select evidence relevant to the claim.")
            draft = super()._call(ExtractionDraft, instructions+'\n\n'+skill, payload, stage, report_id)
            data = draft.model_dump()
            def resolve(items):
                return [passages[item['passage_id']] for item in items]
            data['summary_evidence'] = resolve(data['summary_evidence'])
            for item in data['facts'] + data['proposed_actions']:
                item['evidence'] = resolve(item['evidence'])
            result = ProcessedReport.model_validate(data)
        else:
            result = super()._call(schema, instructions+'\n\n'+skill, payload, stage, report_id)
        self.skill_runs.append({'stage': stage, 'skill_path': str(path.relative_to(ROOT)),
                                'skill_hash': fingerprint(skill)})
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-id', default='AA24-109A')
    parser.add_argument('--approve-processing', action='store_true')
    parser.add_argument('--analyst', required=True)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    if not args.approve_processing:
        parser.error('Explicit --approve-processing is required to record the analyst decision.')
    load_dotenv(ROOT / '.env')
    output = ROOT / 'outputs/skill_runs' / args.report_id
    profile = json.loads((ROOT / 'data/organization_profile.json').read_text())
    matrix = json.loads((ROOT / 'data/risk_matrix.json').read_text())
    workflow = SkillProcessingWorkflow(load_reports(), profile, matrix,
                                      audit_path=output / 'analyst_decisions.json')
    workflow.load_unreviewed(output / 'unreviewed_triage.json')
    workflow.review_report(args.report_id, 'approve', args.analyst, args.reason)
    print('Recorded processing approval. Running technical extraction skill...', flush=True)
    processed = workflow.process_report(args.report_id)
    (output / 'technical_extraction.json').write_text(json.dumps(processed, indent=2)+'\n')
    report = workflow.reports[args.report_id]
    lines = [f"# Technical extraction — {args.report_id}", '', '**Draft — not approved for distribution.**',
             '', processed['summary'], '', f"Source: {report['source_url']}", '']
    for fact in processed['facts']:
        lines.extend([f"## {fact['category']}: {fact['value']}", '', fact['explanation'], ''])
        for evidence in fact['evidence']:
            lines.extend(['> '+evidence['quote'].replace('\n', '\n> '), ''])
    lines.extend(['## Proposed actions', '', json.dumps(processed['proposed_actions'],indent=2),
                  '', '## Gaps', '', *['- '+gap for gap in processed['evidence_gaps']]])
    (output / 'technical_extraction.md').write_text('\n'.join(lines)+'\n')
    print(f"Validated extraction saved: {len(processed['facts'])} facts. Running analytical production skill...", flush=True)
    workflow._require_approval(args.report_id)
    quality_path = output / 'quality_review.json'
    quality = json.loads(quality_path.read_text()) if quality_path.exists() else {}
    result = workflow._call(RAGResponse, '''
Produce the BLUF-led analytical draft using the analytical production skill.
Place BLUF, 5Ws + How, So what?, Tradecraft review, citations and open issues in answer.
Keep upstream score values unchanged and explicitly provisional due to supplied quality concerns.
Do not repeat claims flagged as unsupported without marking the deficiency.
Use the processed source evidence. This is a demonstration draft, never finished intelligence.
The technical companion files are technical_extraction.md and technical_extraction.json.
''', {'report': {k:v for k,v in report.items() if k!='content'},
      'organization_profile': profile, 'triage': workflow.triage[args.report_id],
      'triage_quality_concerns': quality, 'technical_extraction': processed}, 'production', args.report_id)
    (output / 'analytical_production.json').write_text(result.model_dump_json(indent=2)+'\n')
    (output / 'analytical_production.md').write_text('**Demonstration draft — awaiting analyst validation.**\n\n'+result.answer+'\n')
    (output / 'processing_skill_run.json').write_text(json.dumps({'skills':workflow.skill_runs,
        'usage':workflow.usage,'evidence_repairs':workflow.evidence_repairs,
        'processing_bindings':workflow.processing_bindings, 'output_review':'pending'},indent=2)+'\n')
    # Preserve the original quality warnings and update only the workflow status in the review.
    review_path=output/'triage_review.md'
    text=review_path.read_text().replace(
        '**Analyst decision: pending. Technical extraction and analytical production have not run.**',
        '**Analyst approved processing for demonstration. Technical extraction and analytical production ran; output review remains pending.**')
    review_path.write_text(text)
    print(json.dumps({'facts':len(processed['facts']), 'skills_run':workflow.skill_runs,
                      'usage':workflow.usage,'draft':str(output/'analytical_production.md')},indent=2),flush=True)


if __name__=='__main__':
    main()

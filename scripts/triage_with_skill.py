"""Run the project's triage SKILL.md on one report; leave analyst approval pending."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from cti_workflow import Workflow, fingerprint
from tools import load_reports


class SkillTriageWorkflow(Workflow):
    def __init__(self, *args, skill_text, **kwargs):
        super().__init__(*args, **kwargs)
        self.skill_text = skill_text

    def _call(self, schema, instructions, payload, stage, report_id):
        if stage != 'triage':
            raise ValueError('This runner performs triage only; analyst selection is required for subsequent skills.')
        return super()._call(schema, instructions + '\n\n' + self.skill_text,
                             payload, stage, report_id)


def render_review(report, entry, profile, matrix, documents):
    assessment, score = entry['assessment'], entry['score']
    chunks = {c['chunk_id']: c for c in documents}
    criteria = {c['criterion_id']: c for c in matrix['criteria']}
    pirs = {p['pir_id']: p for p in profile['priority_intelligence_requirements']}
    lines = [f"# Analyst triage review — {report['report_id']}", '', report['title'], '',
             f"Source: {report['source_url']}", f"Published: {report['published']}",
             f"Revision: {report.get('updated', 'Not supplied')}", '',
             '**Analyst decision: pending. Technical extraction and analytical production have not run.**', '',
             '## Prioritization', '',
             f"Score range: **{score['minimum_score']}–{score['maximum_score']} / 100**. "
             f"Evidence coverage: **{score['evidence_coverage_percent']}%**. "
             f"Proposed priority: **{score['proposed_priority']}**; possible priority: **{score['possible_priority']}**.",
             f"Priority uncertain: {score['priority_uncertain']}. Immediate review: {score['immediate_review']}.", '',
             'This is report prioritization, not attack probability. The company and its incidents are fictional.', '',
             '## Relevance and risk indicators', '']
    def evidence(items):
        for e in items:
            chunk = chunks[e['chunk_id']]
            section = chunk.get('section_heading') or chunk.get('section') or 'Section not identified'
            lines.extend(['', f"Supporting source — {report['title']} | {section} | {report['source_url']}", '',
                          '> ' + e['quote'].replace('\n', '\n> '), ''])
    for item in assessment['criteria']:
        criterion = criteria[item['criterion_id']]
        lines.extend([f"### {criterion['name']}", '',
            f"Weight: {criterion['weight']}%. Rating: {item['rating'] if item['rating'] is not None else 'Unknown'}/4. "
            f"Judgment: {item['judgment']}. Confidence: {item['confidence']}.", '', item['rationale']])
        evidence(item['evidence'])
        lines.extend(['Gap: ' + gap for gap in item['unknowns']])
    lines.extend(['', '## PIR mapping', ''])
    for mapping in assessment['pir_mappings']:
        lines.extend([f"### {mapping['pir_id']} — {pirs[mapping['pir_id']]['title']}", '',
                      'Question: ' + pirs[mapping['pir_id']]['question'], '',
                      'Contribution: ' + mapping['answers'], '', 'Relevance: ' + mapping['rationale'],
                      'Confidence: ' + mapping['confidence']])
        evidence(mapping['evidence'])
        lines.extend(['Gap: ' + gap for gap in mapping['gaps']])
    if not assessment['pir_mappings']:
        lines.append('No supported PIR matches.')
    lines.extend(['', '## Evidence gaps', '', *['- '+g for g in assessment['evidence_gaps']],
                  '', '## Validation warnings', '', *['- '+w for w in entry['validation_warnings']]])
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-id', default='AA24-109A')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    reports = load_reports()
    report = next((r for r in reports if r['report_id'] == args.report_id), None)
    if report is None:
        parser.error('Unknown report ID')
    profile = json.loads((ROOT / 'data/organization_profile.json').read_text())
    matrix = json.loads((ROOT / 'data/risk_matrix.json').read_text())
    skill_path = ROOT / 'skills/cti-report-triage/SKILL.md'
    skill = skill_path.read_text()
    output = ROOT / 'outputs/skill_runs' / args.report_id
    output.mkdir(parents=True, exist_ok=True)
    workflow = SkillTriageWorkflow(reports, profile, matrix, skill_text=skill,
                                    audit_path=output / 'analyst_decisions.json')
    print(f"Running {skill_path.relative_to(ROOT)} on {args.report_id}", flush=True)
    entry = workflow.triage_report(args.report_id)
    snapshot = {'triage': workflow.triage, 'usage': workflow.usage}
    (output / 'unreviewed_triage.json').write_text(json.dumps(snapshot, indent=2)+'\n')
    (output / 'skill_run.json').write_text(json.dumps({
        'skill_path': str(skill_path.relative_to(ROOT)), 'skill_hash': fingerprint(skill),
        'report_id': args.report_id, 'analyst_decision': 'pending', 'stages_run': ['triage'],
        'usage': workflow.usage}, indent=2)+'\n')
    review_path = output / 'triage_review.md'
    review_path.write_text(render_review(report, entry, profile, matrix, workflow.documents))
    print(json.dumps({'score': entry['score'], 'pirs': [p['pir_id'] for p in entry['assessment']['pir_mappings']],
                      'validation_warnings': entry['validation_warnings'], 'review_file': str(review_path)}, indent=2), flush=True)


if __name__ == '__main__':
    main()

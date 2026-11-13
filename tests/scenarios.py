"""Turn a user-session wishlist into reviewable, parameterized test cases."""
import ast
import json
from pathlib import Path
import re
from pydantic import BaseModel, ConfigDict, Field, model_validator
from tests.utils import collect_tools

ROOT=Path(__file__).resolve().parents[1]


class UserScenario(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    case_id: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$',max_length=64)
    query: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)
    require_references: bool = False
    require_empty_references: bool = False
    require_python: bool = False
    require_checks: bool = False
    require_search: bool = False
    forbid_file_reads: bool = False
    expected_found_answer: bool | None = None
    maximum_confidence: float | None = Field(default=None,ge=0,le=1)
    notes: str = ''

    @model_validator(mode='after')
    def coherent_case(self):
        if any(not c.strip() for c in self.criteria) or len(set(self.criteria))!=len(self.criteria):
            raise ValueError('Criteria must be nonempty and unique.')
        if self.require_references and self.require_empty_references:
            raise ValueError('A case cannot require both present and empty references.')
        return self


def load_scenarios(path=None):
    rows=json.loads(Path(path or ROOT/'evals/data/user_session_cases.json').read_text())
    cases=[UserScenario.model_validate(row) for row in rows]
    if not cases or len({case.case_id for case in cases})!=len(cases):
        raise ValueError('Supply a nonempty catalog with unique case IDs.')
    return cases


def assert_scenario_contract(result,case,reports):
    """Deterministic companions to the English judge; never execute generated code."""
    output=result.output
    known={f"{r['report_id']}.txt" for r in reports}
    calls=collect_tools(result.new_messages())
    opened={call.args.get('filename') for call in calls if call.name=='get_file'}
    if case.require_search:
        assert any(call.name=='search' for call in calls), 'Confirm scope with at least one search.'
    if case.forbid_file_reads:
        assert not opened, 'Do not read unrelated reports for a confirmed off-topic query.'
    for reference in output.references:
        assert reference.file_path in known, f'Invented reference path: {reference.file_path}'
        assert reference.file_path in opened, f'Reference was not opened: {reference.file_path}'
    if case.require_references:
        assert output.references, 'This scenario requires source references.'
    if case.require_empty_references:
        assert not output.references, 'Off-topic answers must not cite irrelevant reports.'
    if case.expected_found_answer is not None:
        assert output.found_answer is case.expected_found_answer
    if case.maximum_confidence is not None:
        assert output.confidence<=case.maximum_confidence, 'Confidence exceeds the scenario limit.'
    if case.require_checks:
        assert output.checks, 'Self-verification checks are required for this scenario.'
        assert all(check.passed for check in output.checks), 'Correct reported self-check failures before final submission.'
    if case.require_python:
        blocks=re.findall(r'```python[^\n]*\n(.*?)```',output.answer,re.DOTALL)
        assert blocks, 'The wishlist scenario requires a Python example.'
        for block in blocks:
            assert block.strip(), 'Empty Python block.'
            try:
                ast.parse(block)
            except SyntaxError as exc:
                raise AssertionError(f'Python example has invalid syntax: {exc.msg}') from exc

"""Application response extends the earlier six-field course schema with references."""
from pydantic import BaseModel, ConfigDict, Field
from course_structured_agent import RAGResponse as CourseRAGResponse


class Reference(BaseModel):
    """A retrieved report actually used to support the answer."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    file_path: str = Field(min_length=1, description='Exact filename opened with get_file, e.g. AA24-038A.txt')
    explanation: str = Field(min_length=1, description='How the report was relevant and used to support this answer')


class Check(BaseModel):
    """Model-reported compliance with a rule; not an independent quality verdict."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    rule: str = Field(min_length=1, description='The applicable response rule being checked.')
    passed: bool = Field(strict=True, description='Whether the final response complies with this rule.')
    explanation: str = Field(min_length=1,
        description='Brief observable evidence in the response that supports compliance or identifies a remaining violation.')


class RAGResponse(CourseRAGResponse):
    # A default keeps earlier saved six-field records readable. New provider
    # responses are instructed to supply references; scenario tests enforce them.
    references: list[Reference] = Field(default_factory=list,
        description='Reports actually opened and used for the answer; never invented paths. Empty when no evidence was used.')

    checks: list[Check] = Field(default_factory=list,
        description='Self-verification for applicable rules. Correct the response before submitting when a check identifies a violation. Not independent verification.')

    def to_string(self):
        parts = [self.answer, '', f'found_answer: {self.found_answer}',
                 f'confidence: {self.confidence}', f'confidence_explanation: {self.confidence_explanation}',
                 f'answer_type: {self.answer_type}']
        parts += [f'reference: {ref.file_path} — {ref.explanation}' for ref in self.references]
        parts += [f'follow_up_question: {question}' for question in self.followup_questions]
        parts += [f'self_check: [{"+" if check.passed else "-"}] {check.rule} — {check.explanation}'
                  for check in self.checks]
        return '\n'.join(parts)

    def __str__(self):
        return self.to_string()


__all__ = ['RAGResponse', 'Reference', 'Check']

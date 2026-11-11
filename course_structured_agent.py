"""The course's three structured-output approaches, using the existing Agent."""
import copy
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from course_agent import Agent


class RAGResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer: str = Field(description="The main answer to the analyst's question in markdown")
    found_answer: bool = Field(description="Whether relevant evidence was found in the retrieved reports")
    confidence: float = Field(ge=0.0, le=1.0, description="Model-reported confidence, not a calibrated probability")
    confidence_explanation: str = Field(description="Explain confidence using evidence and limitations")
    answer_type: Literal['how-to', 'explanation', 'troubleshooting', 'comparison', 'reference']
    followup_questions: list[str] = Field(description="Suggested follow-up questions for the analyst")


class SimpleStructuredAgent(Agent):
    """Approach 1: pass output_type to parse on every model iteration."""
    def __init__(self, llm_client, model, instructions, tools, output_type=None,
                 tool_functions=None, max_iterations=6):
        super().__init__(llm_client, model, instructions, tools, tool_functions, max_iterations)
        self.output_type = output_type
        self.last_output = None
        # The SDK parse helper requires strict function tools. Do not mutate originals.
        if output_type:
            for tool in self.tools:
                tool['strict'] = True
                tool['parameters']['additionalProperties'] = False

    def loop(self, user_prompt, message_history=None):
        if self.llm_client is None:
            raise ValueError('Configure llm_client before running the agent.')
        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ValueError('Provide a nonempty question.')
        if not message_history:
            message_history = [
                {'role': 'system', 'content': self.instructions},
            ]
        message_history.append({'role': 'user', 'content': user_prompt})
        self.message_history = message_history
        self.turn_number += 1
        self.last_output = None
        self.last_status = 'running'
        self.last_answer = None
        iteration_number = 1

        while True:
            if iteration_number > self.max_iterations:
                self.last_status = 'iteration_limit'
                print('Stopped at the iteration limit. Research is incomplete.')
                break

            if self.output_type:
                response = self.llm_client.responses.parse(
                    model=self.model,
                    input=message_history,
                    tools=self.tools,
                    text_format=self.output_type,
                )
            else:
                response = self.llm_client.responses.create(
                    model=self.model,
                    input=message_history,
                    tools=self.tools,
                )
            print(f'iteration number {iteration_number}...')
            message_history.extend(response.output)
            if response.usage:
                self.usage.append({
                    'turn': self.turn_number,
                    'iteration': iteration_number,
                    'input_tokens': response.usage.input_tokens,
                    'output_tokens': response.usage.output_tokens,
                    'total_tokens': response.usage.total_tokens,
                })

            has_function_calls = False
            iteration_text = []
            for message in response.output:
                if message.type == 'function_call':
                    print(f'executing {message.name}({message.arguments})...')
                    tool_call_output = self.make_call(message)
                    message_history.append(tool_call_output)
                    print('Tool result preview:', tool_call_output['output'][:250])
                    self.trace.append({
                        'turn': self.turn_number,
                        'iteration': iteration_number,
                        'tool': message.name,
                        'arguments': message.arguments,
                        'call_id': message.call_id,
                        'result_preview': tool_call_output['output'][:250],
                    })
                    has_function_calls = True

                if message.type == 'message':
                    for part in message.content:
                        if part.type == 'output_text':
                            print('ASSISTANT:', part.text)
                            iteration_text.append(part.text)

            iteration_number += 1
            print()
            if not has_function_calls:
                self.last_answer = '\n'.join(iteration_text) or None
                if self.output_type:
                    parsed = getattr(response, 'output_parsed', None)
                    if parsed is not None:
                        self.last_output = self.output_type.model_validate(parsed)
                        self.last_status = 'structured_unreviewed'
                        self.last_answer = getattr(self.last_output, 'answer', self.last_answer)
                    else:
                        self.last_status = 'incomplete'
                        self.last_answer = None
                else:
                    self.last_status = 'answered_unreviewed' if self.last_answer else 'incomplete'
                break

        return message_history


class StructuredAgent1(Agent):
    """Approach 2: complete the normal loop, then structure it in one extra request."""
    def __init__(self, llm_client, model, instructions, tools, output_type,
                 tool_functions=None, max_iterations=6):
        super().__init__(llm_client, model, instructions, tools, tool_functions, max_iterations)
        self.output_type = output_type
        self.last_output = None

    def structured_loop(self, user_prompt, message_history=None):
        self.last_output = None
        message_history = self.loop(user_prompt, message_history)
        if self.last_status != 'answered_unreviewed':
            return message_history, None

        response = self.llm_client.responses.parse(
            model=self.model,
            input=message_history,
            text_format=self.output_type,
        )
        message_history.extend(response.output)
        if response.usage:
            self.usage.append({
                'turn': self.turn_number,
                'stage': 'structure_final_answer',
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'total_tokens': response.usage.total_tokens,
            })
        parsed = response.output_parsed
        if parsed is None:
            self.last_status = 'incomplete'
            self.last_answer = None
            print('No complete structured output returned. Inspect the response/refusal.')
            return message_history, None
        self.last_output = self.output_type.model_validate(parsed)
        self.last_status = 'structured_unreviewed'
        self.last_answer = getattr(self.last_output, 'answer', self.last_answer)
        return message_history, self.last_output

    def qna(self):
        message_history = [{'role': 'system', 'content': self.instructions}]
        self.message_history = message_history
        while True:
            try:
                user_prompt = input('You:')
            except (EOFError, KeyboardInterrupt):
                print('\nQ&A stopped.')
                break
            if user_prompt.lower().strip() == 'stop':
                print('Q&A stopped.')
                break
            if not user_prompt.strip():
                continue
            message_history, output = self.structured_loop(user_prompt, message_history)
            if output is not None:
                print(output.model_dump_json(indent=2))
        return message_history


def create_fake_tool(output_type, name='structure_result'):
    schema = copy.deepcopy(output_type.model_json_schema())
    schema['type'] = 'object'
    schema['additionalProperties'] = False
    return {
        'type': 'function',
        'name': name,
        'description': 'Call when research is complete to submit the final structured answer. This does not write data or execute an external action.',
        'strict': True,
        'parameters': schema,
    }


class StructuredAgent2(StructuredAgent1):
    """Approach 3: finish the tool-call loop with a structured-result pseudo-tool."""
    FAKE_TOOL_NAME = 'structure_result'

    def __init__(self, llm_client, model, instructions, tools, output_type,
                 tool_functions=None, max_iterations=6):
        if any(tool['name'] == self.FAKE_TOOL_NAME for tool in tools):
            raise ValueError('structure_result is reserved for the final answer.')
        instructions += '\nWhen research is complete, submit the final answer using structure_result. If evidence is missing, state that in the result; do not invent findings.'
        super().__init__(llm_client, model, instructions,
                         list(tools) + [create_fake_tool(output_type, self.FAKE_TOOL_NAME)],
                         output_type, tool_functions, max_iterations)

    def loop(self, user_prompt, message_history=None):
        if self.llm_client is None:
            raise ValueError('Configure llm_client before running the agent.')
        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ValueError('Provide a nonempty question.')
        if not message_history:
            message_history = [{'role': 'system', 'content': self.instructions}]
        message_history.append({'role': 'user', 'content': user_prompt})
        self.message_history = message_history
        self.turn_number += 1
        self.last_output = None
        self.last_answer = None
        self.last_status = 'running'
        iteration_number = 1

        while True:
            if iteration_number > self.max_iterations:
                self.last_status = 'iteration_limit'
                print('Stopped at the iteration limit. No structured output accepted.')
                break
            response = self.llm_client.responses.create(
                model=self.model,
                input=message_history,
                tools=self.tools,
            )
            print(f'iteration number {iteration_number}...')
            message_history.extend(response.output)
            if response.usage:
                self.usage.append({
                    'turn': self.turn_number,
                    'iteration': iteration_number,
                    'input_tokens': response.usage.input_tokens,
                    'output_tokens': response.usage.output_tokens,
                    'total_tokens': response.usage.total_tokens,
                })
            output = None
            calls = [item for item in response.output if item.type == 'function_call']
            for message in response.output:
                if message.type == 'function_call':
                    print(f'executing {message.name}({message.arguments})...')
                    if message.name == self.FAKE_TOOL_NAME:
                        try:
                            if len(calls) != 1:
                                raise ValueError('Submit structure_result alone after completing other tools.')
                            output = self.output_type.model_validate_json(message.arguments)
                            result = {'accepted': True}
                        except ValueError as error:
                            result = {'error': str(error)}
                        # Acknowledge even the pseudo-tool so follow-up history is valid.
                        tool_call_output = {
                            'type': 'function_call_output',
                            'call_id': message.call_id,
                            'output': json.dumps(result),
                        }
                    else:
                        tool_call_output = self.make_call(message)
                    message_history.append(tool_call_output)
                    self.trace.append({
                        'turn': self.turn_number,
                        'iteration': iteration_number,
                        'tool': message.name,
                        'arguments': message.arguments,
                        'call_id': message.call_id,
                        'result_preview': tool_call_output['output'][:250],
                    })
                if message.type == 'message':
                    for part in message.content:
                        if part.type == 'output_text':
                            print('ASSISTANT:', part.text)
            iteration_number += 1
            print()
            if output is not None:
                self.last_output = output
                self.last_status = 'structured_unreviewed'
                self.last_answer = getattr(output, 'answer', None)
                break

        return message_history, self.last_output

    def structured_loop(self, user_prompt, message_history=None):
        return self.loop(user_prompt, message_history)

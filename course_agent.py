"""Small course-style Agent library: tool-call loop inside an interactive Q&A loop."""
import copy
import json


class Agent:
    def __init__(self, llm_client, model, instructions, tools, tool_functions=None,
                 max_iterations=6):
        if type(max_iterations) is not int or max_iterations < 1:
            raise ValueError('max_iterations must be a positive integer.')
        self.llm_client = llm_client
        self.model = model
        self.instructions = instructions
        self.tools = copy.deepcopy(tools)
        # Inject Python implementations so the library does not depend on notebook globals.
        self.tool_functions = dict(tool_functions or {})
        self.max_iterations = max_iterations
        self.usage = []
        self.trace = []
        self.message_history = []
        self.turn_number = 0
        self.last_status = 'not_run'
        self.last_answer = None

    def make_call(self, tool_call):
        name = tool_call.name
        try:
            arguments = json.loads(tool_call.arguments)
            if not isinstance(arguments, dict):
                raise ValueError('Tool arguments must be a JSON object.')
            available = {tool['name'] for tool in self.tools}
            if name in available and name in self.tool_functions:
                result = self.tool_functions[name](**arguments)
            else:
                result = {'error': f'not found tool "{name}"'}
        except (ValueError, TypeError) as error:
            result = {'error': str(error)}

        return {
            'type': 'function_call_output',
            'call_id': tool_call.call_id,
            'output': json.dumps(result, ensure_ascii=False),
        }

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
        self.last_status = 'running'
        self.last_answer = None
        iteration_number = 1

        while True:
            if iteration_number > self.max_iterations:
                self.last_status = 'iteration_limit'
                print('Stopped at the iteration limit. Research is incomplete.')
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
                self.last_status = 'answered_unreviewed' if self.last_answer else 'incomplete'
                break

        return message_history

    def qna(self):
        message_history = [
            {'role': 'system', 'content': self.instructions},
        ]
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
            message_history = self.loop(user_prompt, message_history)
        return message_history

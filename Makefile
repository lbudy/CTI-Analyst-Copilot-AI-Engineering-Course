.PHONY: tests run judge judge-live

tests:
	uv run pytest

run:
	uv run python main.py

judge:
	uv run pytest tests/test_judge.py tests/test_judge_contract.py -s

judge-live:
	uv run pytest tests/test_judge.py -m live --run-live -s

.PHONY: scenarios scenarios-live
scenarios:
	uv run pytest tests/test_user_scenarios.py -s

scenarios-live:
	uv run pytest tests/test_user_scenarios.py -m live --run-live -s


.PHONY: tests-judge tests-judge-live
# Default parallel runs remain offline; live scenarios require an explicit target.
tests-judge:
	uv run pytest tests/test_judge.py tests/test_judge_contract.py tests/test_user_scenarios.py -n 4

tests-judge-live:
	uv run pytest tests/test_judge.py tests/test_user_scenarios.py -m live --run-live -n 4

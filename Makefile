.PHONY: install demo test lint clean

install:
	pip install -r requirements.txt -r requirements-dev.txt

demo:
	python -m src.cli demo

test:
	pytest -v --tb=short

lint:
	ruff check src tests
	ruff format --check src tests

clean:
	rm -rf output/*.html output/*.xlsx .cache __pycache__ .pytest_cache .ruff_cache


.PHONY: setup setup-all refs smoke notebook

setup:
	bash scripts/bootstrap.sh

setup-all:
	bash scripts/bootstrap.sh --with-colmap

refs:
	bash scripts/fetch_references.sh

smoke:
	conda run --no-capture-output -n ai6121-sfm python -m pytest -q tests/test_environment.py

notebook:
	conda run --no-capture-output -n ai6121-sfm jupyter lab main.ipynb


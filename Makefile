.PHONY: install test smoke validate-examples build

install:
	python -m pip install -e .

test:
	python -m unittest discover -s tests -v

smoke:
	./scripts/golden_smoke.sh

validate-examples:
	ontle validate examples/business/manufacturing-quality-world
	ontle validate examples/business/quality-transition-world-model
	ontle validate examples/physical-ai/mobile-manipulation-world
	ontle validate examples/physical-ai/multimodal-action-world-model

build:
	python -m pip install build
	python -m build

.PHONY: install test smoke validate-examples build

install:
	python -m pip install -e .

test:
	@python -c "import yaml" 2>/dev/null || { echo "PyYAML is not installed; run 'make install' (python -m pip install -e .)"; exit 1; }
	python -m unittest discover -s tests -v

smoke:
	./scripts/golden_smoke.sh

validate-examples:
	ontle validate examples/business/manufacturing-quality-world
	ontle validate --resolve --source examples examples/business/manufacturing-quality-world
	ontle validate examples/business/quality-transition-world-model
	ontle validate examples/physical-ai/mobile-manipulation-world
	ontle validate examples/physical-ai/multimodal-action-world-model
	ontle validate examples/business/sales-prioritization-world
	ontle validate examples/ontology/quality-ontology

build:
	python -m pip install build
	python -m build

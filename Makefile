.PHONY: test install install-symlink uninstall lint-json

PYTHON ?= python3

test: lint-json
	$(PYTHON) -m unittest discover -s tests -v

lint-json:
	$(PYTHON) -m json.tool skills/swarm-planner/examples/swarm-guardrails-plugin.json > /dev/null
	$(PYTHON) -m json.tool skills/swarm-planner/examples/swarm-guardrails-hooks.json > /dev/null

install: test
	./scripts/install.sh

install-symlink: test
	./scripts/install.sh --symlink

uninstall:
	./scripts/install.sh --uninstall

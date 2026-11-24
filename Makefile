.PHONY: test install install-symlink install-status uninstall lint-json lint-shell

PYTHON ?= python3
ifeq ($(strip $(PYTHON)),)
override PYTHON := python3
endif
export PYTHON
INSTALL_FLAGS ?=

test: lint-json lint-shell
	PYTHONDONTWRITEBYTECODE=1 "$(PYTHON)" -B -m unittest discover -s tests -v

lint-json:
	PYTHONDONTWRITEBYTECODE=1 "$(PYTHON)" -B -m json.tool skills/swarm-planner/examples/swarm-guardrails-plugin.json > /dev/null
	PYTHONDONTWRITEBYTECODE=1 "$(PYTHON)" -B -m json.tool skills/swarm-planner/examples/swarm-guardrails-hooks.json > /dev/null

lint-shell:
	bash -n scripts/install.sh

install: test
	./scripts/install.sh --copy --skip-tests $(INSTALL_FLAGS)

install-symlink: test
	./scripts/install.sh --symlink --skip-tests $(INSTALL_FLAGS)

install-status:
	./scripts/install.sh --status

uninstall:
	./scripts/install.sh --uninstall

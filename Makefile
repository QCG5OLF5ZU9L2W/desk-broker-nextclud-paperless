PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PROJECT_DIR := $(CURDIR)
NAUTILUS_SCRIPT := $(HOME)/.local/share/nautilus/scripts/An Paperless senden
LOCAL_BIN := $(HOME)/.local/bin/paperless-nc-import

.PHONY: venv install run-gui doctor test lint clean install-bin install-nautilus

venv:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install -U pip

install: venv
	$(BIN)/python -m pip install -e .

run-gui:
	$(BIN)/paperless-nc-import --gui --startup-log

doctor:
	$(BIN)/paperless-nc-import --doctor --startup-log

test:
	$(BIN)/python -m pytest -q

lint:
	$(BIN)/python -m compileall paperless_nc_import

install-bin:
	install -d "$(HOME)/.local/bin"
	printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'exec "$(PROJECT_DIR)/$(BIN)/paperless-nc-import" "$$@"' > "$(LOCAL_BIN)"
	chmod 0755 "$(LOCAL_BIN)"

install-nautilus: install
	./integrations/nautilus/install-nautilus.sh

clean:
	rm -rf build dist *.egg-info .pytest_cache

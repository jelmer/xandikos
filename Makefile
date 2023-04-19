export PYTHON ?= python3
COVERAGE ?= $(PYTHON) -m coverage
COVERAGE_RUN_OPTIONS ?=
COVERAGE_RUN ?= $(COVERAGE) run $(COVERAGE_RUN_OPTIONS)
TESTSUITE = xandikos.tests.test_suite
LITMUS_TESTS ?= basic http
CALDAVTESTER_TESTS ?= CalDAV/delete.xml \
		      CalDAV/options.xml \
		      CalDAV/vtodos.xml
XANDIKOS_COVERAGE ?= $(COVERAGE_RUN) -a --rcfile=$(shell pwd)/.coveragerc --source=xandikos -m xandikos.web

check:
	$(PYTHON) -m unittest $(TESTSUITE)

style:
	$(PYTHON) -m flake8
	isort --check .

typing:
	$(PYTHON) -m mypy xandikos

web:
	$(PYTHON) -m xandikos.web

check-litmus-all:
	./compat/xandikos-litmus.sh "basic copymove http props locks"

check-litmus:
	./compat/xandikos-litmus.sh "${LITMUS_TESTS}"

check-pycaldav:
	./compat/xandikos-pycaldav.sh

coverage-pycaldav:
	XANDIKOS="$(XANDIKOS_COVERAGE)" ./compat/xandikos-pycaldav.sh

coverage-litmus:
	XANDIKOS="$(XANDIKOS_COVERAGE)" ./compat/xandikos-litmus.sh "${LITMUS_TESTS}"

check-vdirsyncer:
	./compat/xandikos-vdirsyncer.sh

coverage-vdirsyncer:
	XANDIKOS="$(XANDIKOS_COVERAGE)" ./compat/xandikos-vdirsyncer.sh

check-all: check check-vdirsyncer check-litmus check-pycaldav style

coverage-all: coverage coverage-litmus coverage-vdirsyncer

coverage:
	$(COVERAGE_RUN) --source=xandikos -m unittest $(TESTSUITE)

coverage-html: coverage
	$(COVERAGE) html

docs:
	$(MAKE) -C docs html

.PHONY: docs

docker:
	buildah build -t jvernooij/xandikos -t ghcr.io/jelmer/xandikos .
	buildah push jvernooij/xandikos
	buildah push ghcr.io/jelmer/xandikos

reformat:
	isort .

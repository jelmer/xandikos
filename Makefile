export PYTHON ?= python3
COVERAGE ?= $(PYTHON) -m coverage
COVERAGE_RUN_OPTIONS ?=
COVERAGE_RUN ?= $(COVERAGE) run $(COVERAGE_RUN_OPTIONS)
TESTSUITE = xandikos.tests.test_suite
LITMUS_TESTS ?= basic http

check:
	$(PYTHON) -m unittest $(TESTSUITE)

style:
	flake8 --exclude=compat/vdirsyncer/

web:
	$(PYTHON) -m xandikos.web

check-litmus-all:
	./compat/xandikos-litmus.sh "basic copymove http props locks"

check-litmus:
	./compat/xandikos-litmus.sh "${LITMUS_TESTS}"

coverage-litmus:
	XANDIKOS="$(COVERAGE_RUN) -a --rcfile=$(shell pwd)/.coveragerc --source=xandikos -m xandikos.web" ./compat/xandikos-litmus.sh "${LITMUS_TESTS}"

check-vdirsyncer:
	./compat/xandikos-vdirsyncer.sh

coverage-vdirsyncer:
	PYTEST_ARGS="--cov-config $(shell pwd)/.coveragerc --cov-append --cov $(shell pwd)/xandikos" ./compat/xandikos-vdirsyncer.sh
	$(COVERAGE) combine -a compat/vdirsyncer/.coverage

check-caldavtester:
	./compat/xandikos-caldavtester.sh

check-all: check check-vdirsyncer check-litmus

coverage-all: coverage coverage-litmus coverage-vdirsyncer

coverage:
	$(COVERAGE_RUN) --source=xandikos -m unittest $(TESTSUITE)

coverage-html: coverage
	$(COVERAGE) html

export PYTHON ?= python3
COVERAGE ?= $(PYTHON) -m coverage
COVERAGE_RUN_OPTIONS ?=
COVERAGE_RUN ?= $(COVERAGE) run $(COVERAGE_RUN_OPTIONS)
TESTSUITE = xandikos.tests.test_suite
LITMUS_TESTS ?= basic http
CALDAVTESTER_TESTS ?= CalDAV/delete.xml \
		      CalDAV/schedulenomore.xml \
		      CalDAV/options.xml \
		      CalDAV/vtodos.xml
XANDIKOS_COVERAGE ?= $(COVERAGE_RUN) -a --rcfile=$(shell pwd)/.coveragerc --source=xandikos -m xandikos.web

check:
	$(PYTHON) -m unittest $(TESTSUITE)

style:
	flake8 --exclude=compat/vdirsyncer/,.tox,compat/ccs-caldavtester

web:
	$(PYTHON) -m xandikos.web

check-litmus-all:
	./compat/xandikos-litmus.sh "basic copymove http props locks"

check-litmus:
	./compat/xandikos-litmus.sh "${LITMUS_TESTS}"

coverage-litmus:
	XANDIKOS="$(XANDIKOS_COVERAGE)" ./compat/xandikos-litmus.sh "${LITMUS_TESTS}"

check-vdirsyncer:
	./compat/xandikos-vdirsyncer.sh

coverage-vdirsyncer:
	PYTEST_ARGS="--cov-config $(shell pwd)/.coveragerc --cov-append --cov $(shell pwd)/xandikos" ./compat/xandikos-vdirsyncer.sh
	$(COVERAGE) combine -a compat/vdirsyncer/.coverage

check-caldavtester:
	TESTS="$(CALDAVTESTER_TESTS)" ./compat/xandikos-caldavtester.sh

coverage-caldavtester:
	TESTS="$(CALDAVTESTER_TESTS)" XANDIKOS="$(XANDIKOS_COVERAGE)" ./compat/xandikos-caldavtester.sh

check-caldavtester-all:
	./compat/xandikos-caldavtester.sh

coverage-caldavtester-all:
	XANDIKOS="$(XANDIKOS_COVERAGE)" ./compat/xandikos-caldavtester.sh

check-all: check check-vdirsyncer check-litmus check-caldavtester style

coverage-all: coverage coverage-litmus coverage-vdirsyncer coverage-caldavtester

coverage:
	$(COVERAGE_RUN) --source=xandikos -m unittest $(TESTSUITE)

coverage-html: coverage
	$(COVERAGE) html

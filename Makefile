export PYTHON ?= python3
COVERAGE ?= $(PYTHON) -m coverage
COVERAGE_RUN_OPTIONS ?=
TESTSUITE = xandikos.tests.test_suite

check:
	$(PYTHON) -m unittest $(TESTSUITE)

style:
	flake8 --exclude=compat/vdirsyncer/

web:
	$(PYTHON) -m xandikos.web

check-litmus-all:
	./compat/xandikos-litmus.sh

check-litmus:
	./compat/xandikos-litmus.sh "basic"

check-vdirsyncer:
	./compat/xandikos-vdirsyncer.sh

check-caldavtester:
	cd compat && ./all.sh

check-all: check check-vdirsyncer check-litmus

coverage:
	$(COVERAGE) run $(COVERAGE_RUN_OPTIONS) --source=xandikos -m unittest $(TESTSUITE)

coverage-html: coverage
	$(COVERAGE) html

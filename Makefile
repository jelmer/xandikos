PYTHON ?= python3
COVERAGE ?= python3-coverage
TESTSUITE = xandikos.tests.test_suite

check:
	$(PYTHON) -m unittest $(TESTSUITE)

web:
	$(PYTHON) -m xandikos.web

check-litmus-all:
	./compat/xandikos-litmus.sh

check-litmus:
	./compat/xandikos-litmus.sh "basic"

check-caldavtester:
	cd compat && ./all.sh

check-all: check check-caldavtester check-litmus

coverage:
	$(COVERAGE) run --source=xandikos -m unittest $(TESTSUITE)

coverage-html: coverage
	$(COVERAGE) html

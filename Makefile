PYTHON ?= python3
COVERAGE ?= python3-coverage
TESTSUITE = xandikos.tests.test_suite

check:
	$(PYTHON) -m unittest $(TESTSUITE)

web:
	$(PYTHON) -m xandikos.web

check-compat:
	cd compat && ./all.sh

check-all: check check-compat

coverage:
	$(COVERAGE) run --source=xandikos -m unittest $(TESTSUITE)

coverage-html: coverage
	$(COVERAGE) html

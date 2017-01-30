PYTHON ?= python3

check:
	$(PYTHON) -m unittest xandikos.tests.test_suite

web:
	$(PYTHON) -m xandikos.web

check-compat:
	cd compat && ./all.sh

check-all: check check-compat


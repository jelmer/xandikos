PYTHON ?= python3

check:
	$(PYTHON) -m unittest dystros.tests.test_suite

web:
	$(PYTHON) -m dystros.web

check-compat:
	cd compat && ./all.sh

check-all: check check-compat


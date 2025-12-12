export PYTHON ?= python3
COVERAGE ?= $(PYTHON) -m coverage
COVERAGE_RUN_OPTIONS ?=
COVERAGE_RUN ?= $(COVERAGE) run $(COVERAGE_RUN_OPTIONS)
TESTSUITE = tests.test_suite
LITMUS_TESTS ?= basic http copymove
CALDAVTESTER_TESTS ?= CalDAV/delete.xml \
		      CalDAV/options.xml \
		      CalDAV/vtodos.xml
XANDIKOS_COVERAGE ?= $(COVERAGE_RUN) -a --rcfile=$(shell pwd)/.coveragerc --source=xandikos -m xandikos.web

check:
	$(PYTHON) -m unittest $(TESTSUITE)

style:
	$(PYTHON) -m ruff check .

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

check-caldav-server-tester:
	./compat/xandikos-caldav-server-tester.sh

coverage-pycaldav:
	XANDIKOS="$(XANDIKOS_COVERAGE)" ./compat/xandikos-pycaldav.sh

coverage-caldav-server-tester:
	XANDIKOS="$(XANDIKOS_COVERAGE)" ./compat/xandikos-caldav-server-tester.sh

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

docker: docker
	@echo "Please use 'make container' rather than 'make docker'"

container:
	buildah build -t jvernooij/xandikos -t ghcr.io/jelmer/xandikos .
	buildah push jvernooij/xandikos
	buildah push ghcr.io/jelmer/xandikos

reformat:
	ruff format .

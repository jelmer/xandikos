#!/bin/sh
set -e

REPO_DIR="$(realpath $(dirname $0)/..)"
TMPDIR="$(mktemp -d)"

cd "$TMPDIR"
git clone https://github.com/pimutils/vdirsyncer
cd vdirsyncer
make \
    COVERAGE=true \
    PYTEST_ARGS="--cov-config $REPO_DIR/.coveragerc --cov-append --cov xandikos" \
    DAV_SERVER=xandikos \
    install-dev install-test test

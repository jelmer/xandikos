#!/bin/sh
set -e

cd "$(dirname $0)"
REPO_DIR="$(readlink -f ..)"

if [ ! -d vdirsyncer ]; then
    git clone https://github.com/pimutils/vdirsyncer
fi
cd vdirsyncer
make \
    COVERAGE=true \
    PYTEST_ARGS="--cov-config $REPO_DIR/.coveragerc --cov-append --cov $REPO_DIR/xandikos tests/storage/dav/" \
    DAV_SERVER=xandikos \
    install-dev install-test test

cd "$REPO_DIR"
coverage combine compat/vdirsyncer/.coverage

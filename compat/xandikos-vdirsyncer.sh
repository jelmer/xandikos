#!/bin/bash
set -e

readonly BRANCH=master

[ -z "$PYTHON" ] && PYTHON=python3

cd "$(dirname $0)"
REPO_DIR="$(readlink -f ..)"

if [ ! -d vdirsyncer ]; then
    git clone -b $BRANCH https://github.com/pimutils/vdirsyncer
else
    pushd vdirsyncer
    git pull --ff-only origin $BRANCH
    popd
fi
cd vdirsyncer
if [ -z "${VIRTUAL_ENV}" ]; then
    virtualenv venv -p${PYTHON}
    source venv/bin/activate
    export PYTHONPATH=${REPO_DIR}
    pushd ${REPO_DIR} && ${PYTHON} setup.py develop && popd
fi
make \
    COVERAGE=true \
    PYTEST_ARGS="${PYTEST_ARGS} tests/storage/dav/" \
    DAV_SERVER=xandikos \
    install-dev install-test test

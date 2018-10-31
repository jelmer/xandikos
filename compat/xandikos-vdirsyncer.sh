#!/bin/bash

. $(dirname $0)/common.sh

set -e

readonly BRANCH=master

run_xandikos 5001 --autocreate

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

if [ -z "${CARGO_HOME}" ]; then
    export CARGO_HOME="$(readlink -f .)/cargo"
    export RUSTUP_HOME="$(readlink -f .)/cargo"
fi
curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly --no-modify-path
. ${CARGO_HOME}/env
rustup update nightly

# Add --ignore=tests/system/utils/test_main.py since it fails in travis,
# and isn't testing anything relevant to Xandikos.
make \
    PYTEST_ARGS="${PYTEST_ARGS} tests/storage/dav/ --ignore=tests/system/utils/test_main.py" \
    DAV_SERVER=xandikos \
    install-dev install-test test
exit 0

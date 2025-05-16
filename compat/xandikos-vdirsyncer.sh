#!/bin/bash

. $(dirname $0)/common.sh

set -e

readonly BRANCH=main
VENV_DIR=$(dirname $0)/vdirsyncer-venv

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

# Always use our own virtual environment for better isolation
if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment for vdirsyncer"
    ${PYTHON} -m venv "${VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"

# Install dependencies in virtual environment
cd vdirsyncer
pip install -e '.[test]'
cd ..

# Deactivate venv before running xandikos so it uses system Python
deactivate

# Now run xandikos with system Python on port 8000 (what tests expect)
run_xandikos 8000 --autocreate

# Reactivate virtual environment for running tests
source "${VENV_DIR}/bin/activate"

cd vdirsyncer

if [ -z "${CARGO_HOME}" ]; then
    export CARGO_HOME="$(readlink -f .)/cargo"
    export RUSTUP_HOME="$(readlink -f .)/cargo"
fi
curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain nightly --no-modify-path
. ${CARGO_HOME}/env
rustup update nightly

# Export xandikos URL for tests
export DAV_SERVER=xandikos
export DAV_SERVER_URL=http://localhost:8000/

# Patch the conftest.py to use our local xandikos instead of Docker
cp tests/storage/conftest.py tests/storage/conftest.py.bak

# Set up trap to restore conftest.py on exit
restore_conftest() {
    if [ -f tests/storage/conftest.py.bak ]; then
        mv tests/storage/conftest.py.bak tests/storage/conftest.py
    fi
}
trap restore_conftest EXIT

cat >> tests/storage/conftest.py << 'EOF'

# Override the xandikos_server fixture to use our local instance
import pytest

@pytest.fixture(scope="session")
def xandikos_server():
    """Use the locally running xandikos instead of Docker."""
    # Our xandikos is already running on port 5001
    # The tests expect it on port 8000, but we'll handle that in the server config
    yield
EOF

# Run the tests
pytest tests/storage/dav/ --ignore=tests/system/utils/test_main.py --no-cov -v --tb=short

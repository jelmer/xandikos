#!/bin/bash
# Run python-caldav tests against Xandikos.
set -e

. $(dirname $0)/common.sh

BRANCH=master
PYCALDAV_REF=v1.2.1
VENV_DIR=$(dirname $0)/pycaldav-venv
[ -z "$PYTHON" ] && PYTHON=python3

if [ ! -d $(dirname $0)/pycaldav ]; then
    git clone --branch $PYCALDAV_REF https://github.com/python-caldav/caldav $(dirname $0)/pycaldav
else
    pushd $(dirname $0)/pycaldav
    git fetch origin
    git reset --hard $PYCALDAV_REF
    popd
fi

# Set up virtual environment
if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment for pycaldav"
    ${PYTHON} -m venv "${VENV_DIR}"
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# Install pycaldav and test dependencies in the virtual environment
pushd $(dirname $0)/pycaldav
pip install -e . pytest
popd

# Deactivate venv before running xandikos so it uses system Python
deactivate

cat <<EOF>$(dirname $0)/pycaldav/tests/conf_private.py
# Only run tests against my private caldav servers.
only_private = True

caldav_servers = [
    {'url': 'http://localhost:5233/',
     'incompatibilities': ['no_scheduling', 'text_search_not_working'],
    }
]
EOF

run_xandikos 5233 5234 --defaults

# Reactivate the virtual environment to run pycaldav tests
source "${VENV_DIR}/bin/activate"

pushd $(dirname $0)/pycaldav
pytest tests "$@"
popd

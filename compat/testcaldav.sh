#!/bin/bash -e

BRANCH=master

cd $(readlink -f ..)

if [ ! -d ccs-caldavtester ]; then
    git clone https://github.com/apple/ccs-caldavtester.git
else
    pushd ccs-caldavtester
    git pull --ff-only origin $BRANCH
    popd
fi

PYTHON2=$((which python2 || which python2.7 || python2.6 || which python) | tail -1)

echo "Using ${PYTHON2}"

cd ccs-caldavtester
${PTYHON2} ./testcaldav.py "$@"

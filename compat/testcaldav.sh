#!/bin/bash -e

BRANCH=master

cd $(dirname $0)

if [ ! -d ccs-caldavtester ]; then
    git clone https://github.com/apple/ccs-caldavtester.git
else
    pushd ccs-caldavtester
    git pull --ff-only origin $BRANCH
    popd
fi

cd ccs-caldavtester
python2 ./testcaldav.py "$@"

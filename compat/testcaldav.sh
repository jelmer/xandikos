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

cd ccs-caldavtester
./testcaldav.py "$@"

#!/bin/bash
# Run caldavtester tests against Xandikos.
set -e

. $(dirname $0)/common.sh

TESTS=

CFGDIR=$(readlink -f $(dirname $0))

run_xandikos --defaults

testcaldav -s ${CFGDIR}/serverinfo.xml ${TESTS}

#!/bin/bash
# Run caldavtester tests against Xandikos.
set -e

. $(dirname $0)/common.sh

CFGDIR=$(readlink -f $(dirname $0))

run_xandikos --defaults

TESTCALDAV="$(dirname $0)/testcaldav.sh"
$TESTCALDAV -s ${CFGDIR}/serverinfo.xml ${TESTS}

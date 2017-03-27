#!/bin/bash
# Run caldavtester tests against Xandikos.
set -e

. $(dirname $0)/common.sh

CFGDIR=$(readlink -f $(dirname $0))

run_xandikos --defaults

if which testcaldav >/dev/null; then
	TESTCALDAV=testcaldav
else
	TESTCALDAV="$(dirname $0)/testcaldav.sh"
fi

$TESTCALDAV -s ${CFGDIR}/serverinfo.xml ${TESTS}

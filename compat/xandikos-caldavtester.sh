#!/bin/bash
# Run caldavtester tests against Xandikos.
set -e

. $(dirname $0)/common.sh

CFGDIR=$(readlink -f $(dirname $0))

if which testcaldav >/dev/null; then
	TESTCALDAV=testcaldav
else
	TESTCALDAV="$(dirname $0)/testcaldav.sh"
fi

function mkcol() {
	p="$1"
	t="$2"
	git init -q "${SERVEDIR}/$p"
	if [[ -n "$t" ]]; then
		echo "[xandikos]" >> "${SERVEDIR}/$p/.git/config"
		echo "	type = $t" >> "${SERVEDIR}/$p/.git/config"
	fi
}

function mkcalendar() {
	p="$1"
	mkcol "$p" "calendar"
}

function mkaddressbook() {
	p="$1"
	mkcol "$p" "addressbook"
}

mkcol addressbooks
mkcol addressbooks/__uids__
for I in `seq 1 40`; do
    mkcol "addressbooks/__uids__/user$(printf %02d $I)"
    mkaddressbook addressbooks/__uids__/user$(printf %02d $I)/addressbook
done
mkcol principals
mkcol principals/__uids__
mkcol principals/__uids__/user01/

run_xandikos --defaults

$TESTCALDAV --print-details-onfail -s ${CFGDIR}/serverinfo.xml ${TESTS}

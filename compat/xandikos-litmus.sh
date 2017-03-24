#!/bin/bash -x
# Run litmus against xandikos

TESTS="$1"

XANDIKOS_PID=
DAEMON_LOG=$(mktemp)
SERVEDIR=$(mktemp -d)
if [ -z "${XANDIKOS}" ]; then
	XANDIKOS=$(dirname $0)/../bin/xandikos
fi

set -e

cleanup() {
	[ -z ${XANDIKOS_PID} ] || kill ${XANDIKOS_PID}
	rm --preserve-root -rf ${SERVEDIR}
	cat ${DAEMON_LOG}
	wait
}

run_xandikos()
{
	${XANDIKOS} -p5233 -llocalhost -d ${SERVEDIR} --autocreate 2>&1 >$DAEMON_LOG &
	XANDIKOS_PID=$!
	sleep 4
}

trap cleanup 0 EXIT

run_xandikos

if which litmus >/dev/null; then
	LITMUS=litmus
else
	LITMUS="$(dirname $0)/litmus.sh"
fi

TESTS="$TESTS" $LITMUS http://localhost:5233/

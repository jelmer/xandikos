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
	[ -z ${XANDIKOS_PID} ] || kill -TERM ${XANDIKOS_PID}
	rm --preserve-root -rf ${SERVEDIR}
	cat ${DAEMON_LOG}
}

run_xandikos()
{
	${XANDIKOS} -p5233 -llocalhost -d ${SERVEDIR} --autocreate 2>&1 >$DAEMON_LOG &
	XANDIKOS_PID=$!
	i=0
	while [ $i -lt 10 ]
	do
		if curl http://localhost:5233/ >/dev/null; then
			break
		fi
		sleep 1
		let i+=1
	done
}

trap cleanup 0 EXIT

run_xandikos

if which litmus >/dev/null; then
	LITMUS=litmus
else
	LITMUS="$(dirname $0)/litmus.sh"
fi

TESTS="$TESTS" $LITMUS http://localhost:5233/
exit 0

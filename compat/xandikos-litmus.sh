#!/bin/bash -x
# Run litmus against xandikos

XANDIKOS_PID=
DAEMON_LOG=$(mktemp)
SERVEDIR=$(mktemp -d)

set -e

cleanup() {
    [ -z ${XANDIKOS_PID} ] || kill ${XANDIKOS_PID}
   rm --preserve-root -rf ${SERVEDIR}
   cat ${DAEMON_LOG}
}

run_xandikos()
{
	$(dirname $0)/../bin/xandikos -p5233 -llocalhost -d ${SERVEDIR} --autocreate 2>&1 >$DAEMON_LOG &
	XANDIKOS_PID=$!
	sleep 2
}

trap cleanup 0 EXIT

run_xandikos

$(dirname $0)/litmus.sh http://localhost:5233/

#!/bin/bash
# Common functions for running xandikos in compat tests

XANDIKOS_PID=
DAEMON_LOG=$(mktemp)
SERVEDIR=$(mktemp -d)
if [ -z "${XANDIKOS}" ]; then
	XANDIKOS=$(dirname $0)/../bin/xandikos
fi

set -e

xandikos_cleanup() {
	[ -z ${XANDIKOS_PID} ] || kill -INT ${XANDIKOS_PID}
	rm --preserve-root -rf ${SERVEDIR}
	cat ${DAEMON_LOG}
	wait ${XANDIKOS_PID} || true
}

run_xandikos()
{
	PORT="$1"
	shift 1
	${XANDIKOS} -p${PORT} -llocalhost -d ${SERVEDIR} "$@" 2>&1 >$DAEMON_LOG &
	XANDIKOS_PID=$!
	trap xandikos_cleanup 0 EXIT
	i=0
	while [ $i -lt 10 ]
	do
		if curl http://localhost:${PORT}/ >/dev/null; then
			break
		fi
		sleep 1
		let i+=1
	done
}

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
	[ -z ${XANDIKOS_PID} ] || kill -INT ${XANDIKOS_PID} 2>/dev/null || true
	rm -rf ${SERVEDIR}
	mkdir -p ${SERVEDIR}
	cat ${DAEMON_LOG}
	wait ${XANDIKOS_PID} 2>/dev/null || true
}

run_xandikos()
{
	PORT="$1"
	shift 1

	# Check if second argument is a port number
	if [[ $1 =~ ^[0-9]+$ ]]; then
		METRICS_PORT="$1"
		shift 1
		METRICS_ARGS="--metrics-port=${METRICS_PORT}"
		HEALTH_URL="http://localhost:${METRICS_PORT}/health"
	else
		METRICS_ARGS=""
		HEALTH_URL="http://localhost:${PORT}/"
	fi

	echo "Writing daemon log to $DAEMON_LOG"
	echo "Running: ${XANDIKOS} serve --no-detect-systemd --port=${PORT} ${METRICS_ARGS} -l localhost -d ${SERVEDIR} $@"

	${XANDIKOS} serve --no-detect-systemd --port=${PORT} ${METRICS_ARGS} -l localhost -d ${SERVEDIR} "$@" >$DAEMON_LOG 2>&1 &
	XANDIKOS_PID=$!
	trap xandikos_cleanup 0 EXIT
	i=0
	while [ $i -lt 50 ]
	do
		if [ -n "${METRICS_PORT}" ]; then
		# Check metrics health endpoint
			if [ "$(curl -s http://localhost:${METRICS_PORT}/health)" = "ok" ]; then
				break
			fi
		else
			# Check if main port is responding
			if curl -s -f http://localhost:${PORT}/ >/dev/null 2>&1; then
				break
			fi
		fi
		sleep 1
		let i+=1
	done

	if [ $i -eq 50 ]; then
		echo "WARNING: xandikos may not have started properly. Check the daemon log."
		cat $DAEMON_LOG
	fi
}

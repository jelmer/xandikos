#!/bin/bash

# Copied from debian/tests/caldav in calypso-1.5 by Guido Gunther.

DYSTROS_PID=
DAEMON_LOG=$(mktemp)
TESTS=

set -e

cleanup() {
    [ -z ${DYSTROS_PID} ] || kill ${DYSTROS_PID}
   rm --preserve-root -rf ${SERVEDIR}
   cat ${DAEMON_LOG}
}

run_dystros()
{
    PYTHONPATH=$PWD/.. python3 -m dystros.web -p5233 -llocalhost -d ${SERVEDIR} 2>&1 >$DAEMON_LOG &
    DYSTROS_PID=$!
    sleep 2
}

SERVEDIR=$(mktemp -d)
trap cleanup 0 INT QUIT ABRT PIPE TERM

run_dystros

testcaldav -s $PWD/serverinfo.xml ${TESTS}

#!/bin/bash -x
# Run litmus against xandikos

. $(dirname $0)/common.sh

TESTS="$1"

set -e

run_xandikos 5233 5234 --autocreate

if which litmus >/dev/null; then
	LITMUS=litmus
else
	LITMUS="$(dirname $0)/litmus.sh"
fi

TESTS="$TESTS" $LITMUS http://localhost:5233/
exit 0

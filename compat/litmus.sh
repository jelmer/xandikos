#!/bin/bash -e
URL="$1"
if [ -z "$URL" ]; then
	echo "Usage: $0 URL"
	exit 1
fi
if [ -n "$TESTS" ]; then
	TEST_ARG=TESTS="$TESTS"
fi
SRCPATH="$(dirname $(readlink -m $0))"
VERSION=${LITMUS_VERSION:-0.13}
LITMUS_URL="${LITMUS_URL:-http://www.webdav.org/neon/litmus/litmus-${VERSION}.tar.gz}"

scratch=$(mktemp -d)
function finish() {
	rm -rf "${scratch}"
}
trap finish EXIT
pushd "${scratch}"

if [ -f "${SRCPATH}/litmus-${VERSION}.tar.gz" ]; then
	cp "${SRCPATH}/litmus-${VERSION}.tar.gz" .
else
	wget -O "litmus-${VERSION}.tar.gz" "${LITMUS_URL}"
fi
sha256sum ${SRCPATH}/litmus-${VERSION}.tar.gz.sha256sum
tar xvfz litmus-${VERSION}.tar.gz
pushd litmus-${VERSION}
./configure
make
make URL="$URL" $TEST_ARG check

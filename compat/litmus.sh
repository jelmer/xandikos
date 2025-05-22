#!/bin/bash -e
URL="$1"
if [ -z "$URL" ]; then
	echo "Usage: $0 URL"
	exit 1
fi
if [ -n "$TESTS" ]; then
	TEST_ARG=TESTS="$TESTS"
fi
# Use realpath if available, otherwise fall back to a compatible approach
if which realpath >/dev/null 2>&1; then
    SRCPATH="$(dirname $(realpath $0))"
else
    # macOS compatible way
    SRCPATH="$(cd $(dirname $0) && pwd)"
fi
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
	curl -L -o "litmus-${VERSION}.tar.gz" "${LITMUS_URL}"
fi
# Use shasum on macOS, sha256sum on Linux
if which sha256sum >/dev/null 2>&1; then
	sha256sum -c ${SRCPATH}/litmus-${VERSION}.tar.gz.sha256sum
else
	shasum -a 256 -c ${SRCPATH}/litmus-${VERSION}.tar.gz.sha256sum
fi
tar xvfz litmus-${VERSION}.tar.gz
pushd litmus-${VERSION}
# Configure with macOS-specific flags if needed
if [ "$(uname)" = "Darwin" ]; then
	# Fix socket() test for macOS - configure uses socket() without parameters
	# Replace both instances of socket(); and the socket test code
	sed -i '' 's/socket();/int s = socket(AF_INET, SOCK_STREAM, 0);/g' configure
	sed -i '' 's/ne__code="socket();"/ne__code="int s = socket(AF_INET, SOCK_STREAM, 0);"/g' configure
	sed -i '' 's/__stdcall socket();/__stdcall socket(AF_INET, SOCK_STREAM, 0);/g' configure
	./configure LDFLAGS="-framework CoreFoundation -framework Security" CFLAGS="-I/usr/include -I/usr/include/sys"
else
	./configure
fi
make
make URL="$URL" $TEST_ARG check

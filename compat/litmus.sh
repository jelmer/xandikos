#!/bin/bash -e
URL="$1"
if [ -z "$URL" ]; then
	echo "Usage: $0 URL"
	exit 1
fi
if [ -n "$TESTS" ]; then
	TEST_ARG=TESTS="$TESTS"
fi
VERSION=${LITMUS_VERSION:-0.17}
LITMUS_REPO="${LITMUS_REPO:-https://github.com/notroj/litmus.git}"

scratch=$(mktemp -d)
function finish() {
	rm -rf "${scratch}"
}
trap finish EXIT
pushd "${scratch}"

git clone --recurse-submodules --depth=1 --branch="${VERSION}" "${LITMUS_REPO}" "litmus-${VERSION}"
pushd litmus-${VERSION}
# Generate configure script if not present (GitHub archive)
if [ ! -f configure ] && [ -f autogen.sh ]; then
	./autogen.sh
fi
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

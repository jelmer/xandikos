#!/bin/bash -e
URL="$1"
if [ -z "$URL" ]; then
	echo "Usage: $0 URL"
	exit 1
fi
SRCPATH="$(realpath $(dirname $0))"
VERSION=0.13

scratch=$(mktemp -d)
function finish() {
	rm -rf "${scratch}"
}
trap finish EXIT
pushd "${scratch}"

wget -O "litmus-${VERSION}.tar.gz" http://www.webdav.org/neon/litmus/litmus-${VERSION}.tar.gz
sha256sum ${SRCPATH}/litmus-${VERSION}.tar.gz.sha256sum
tar xvfz litmus-${VERSION}.tar.gz
pushd litmus-${VERSION}
./configure
make
make URL="$URL" check

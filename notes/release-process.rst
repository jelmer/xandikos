Release Process
===============

1. Update version in setup.py
2. Update version in xandikos/__init__.py
3. git commit -a -m "Release $VERSION"
4. git tag -as -m "Release $VERSION" v$VERSION
5. ./setup.py sdist upload --sign

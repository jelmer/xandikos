Xandikos has a fairly clear distinction between different components.

Modules
=======

The core WebDAV implementation lives in xandikos.webdav. This just implements
the WebDAV protocol, and provides abstract classes for WebDAV resources that can be
implemented by other code.

Several WebDAV extensions (access, CardDAV, CalDAV) live in their own
Python file. They build on top of the WebDAV module, and provide extra
reporter and property implementations as defined in those specifications.

Store is a simple object-store implementation on top of a Git repository, which
has several properties that make it useful as a WebDAV backend.

The business logic lives in xandikos.web; it ties together the other modules,


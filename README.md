[![Build Status](https://travis-ci.org/jelmer/xandikos.png?branch=master)](https://travis-ci.org/jelmer/xandikos)

Xandikos is a CardDAV/CalDAV server that backs onto a Git repository.

Xandikos (Ξανδικός or Ξανθικός) takes its name from the name of the March month
in the ancient Macedonian calendar, used in Macedon in the first millennium BC.

Implemented standards
=====================

The following standards are implemented:

 - RFC4918/RFC2518 (Core WebDAV) - *implemented, except for COPY/MOVE/LOCK operations*
 - RFC4791 (CalDAV) - *fully implemented*
 - RFC6352 (CardDAV) - *fully implemented*
 - RFC5397 (Current Principal) - *fully implemented*
 - RFC3253 (Versioning Extensions) - *partially implemented, only the REPORT method and {DAV:}expand-property property*
 - RFC3744 (Access Control) - *partially implemented*
 - RFC5995 (POST to create members) - *fully implemented*
 - RFC7809 (CalDAV Time Zone Extensions) - *not implemented*

See [[notes/dav-compliance.md]] for more detail on specification compliancy.

Limitations
-----------

 - No multi-user support
 - No support for CalDAV scheduling extensions

Supported clients
=================

Xandikos has been tested and works with the following clients:

 - vdirsyncer
 - caldavzap/carddavmate
 - evolution
 - davdroid
 - sogo connector for Icedove/Thunderbird
 - aCALdav syncer for Android
 - pycardsyncer

Clients that are known not to work:

 - CalDAV-Sync
 - CardDAV-Sync

Running
=======

To run a standalone (low-performance) instance of Xandikos, simply create a
directory to store your data (say *$HOME/dav*) and run it:

```shell
mkdir -p $HOME/dav
./bin/xandikos -d $HOME/dav
```

A server should now be running on _localhost:8080_.

Help
====

There is a *#xandikos* IRC channel on the [Freenode](https://www.freenode.net/)
IRC network, and a [xandikos](https://groups.google.com/forum/#!forum/xandikos)
mailing list.

Dependencies
============

At the moment, Xandikos supports Python 3.5 and higher as well as Pypy 3. It
also uses dulwich, icalendar and defusedxml.

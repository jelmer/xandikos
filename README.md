[![Build Status](https://travis-ci.org/jelmer/xandikos.png?branch=master)](https://travis-ci.org/jelmer/xandikos)

Xandikos is a CardDAV/CalDAV server that backs onto a Git repository.

Xandikos (Ξανδικός or Ξανθικός) takes its name from the name of the March month
in the ancient Macedonian calendar, used in Macedon in the first millennium BC.

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

Help
====

There is a *#xandikos* IRC channel on the [Freenode](https://www.freenode.net/)
IRC network, and a [xandikos](https://groups.google.com/forum/#!forum/xandikos)
mailing list.

Dependencies
============

At the moment, Dulwich supports Python 3.5 and higher as well as Pypy 3. It
also uses dulwich, icalendar and defusedxml.

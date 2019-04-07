.. image:: https://travis-ci.org/jelmer/xandikos.png?branch=master
   :target: https://travis-ci.org/jelmer/xandikos
   :alt: Build Status

.. image:: https://ci.appveyor.com/api/projects/status/fjqtsk8agwmwavqk/branch/master?svg=true
   :target: https://ci.appveyor.com/project/jelmer/xandikos/branch/master
   :alt: Windows Build Status


Xandikos is a lightweight yet complete CardDAV/CalDAV server that backs onto a Git repository.

Xandikos (Ξανδικός or Ξανθικός) takes its name from the name of the March month
in the ancient Macedonian calendar, used in Macedon in the first millennium BC.

Implemented standards
=====================

The following standards are implemented:

- :RFC:`4918`/:RFC:`2518` (Core WebDAV) - *implemented, except for COPY/MOVE/LOCK operations*
- :RFC:`4791` (CalDAV) - *fully implemented*
- :RFC:`6352` (CardDAV) - *fully implemented*
- :RFC:`5397` (Current Principal) - *fully implemented*
- :RFC:`3253` (Versioning Extensions) - *partially implemented, only the REPORT method and {DAV:}expand-property property*
- :RFC:`3744` (Access Control) - *partially implemented*
- :RFC:`5995` (POST to create members) - *fully implemented*
- :RFC:`5689` (Extended MKCOL) - *fully implemented*

The following standards are not implemented:

- :RFC:`6638` (CalDAV Scheduling Extensions) - *not implemented*
- :RFC:`7809` (CalDAV Time Zone Extensions) - *not implemented*
- :RFC:`7529` (WebDAV Quota) - *not implemented*
- :RFC:`4709` (WebDAV Mount) - `intentionally <https://github.com/jelmer/xandikos/issues/48>`_ *not implemented*
- :RFC:`5546` (iCal iTIP) - *not implemented*
- :RFC:`4324` (iCAL CAP) - *not implemented*
- :RFC:`7953` (iCal AVAILABILITY) - *not implemented*

See `DAV compliance <notes/dav-compliance.rst>`_ for more detail on specification compliancy.

Limitations
-----------

- No multi-user support
- No support for CalDAV scheduling extensions

Supported clients
=================

Xandikos has been tested and works with the following CalDAV/CardDAV clients:

- `Vdirsyncer <https://github.com/pimutils/vdirsyncer>`_
- `caldavzap <https://www.inf-it.com/open-source/clients/caldavzap/>`_/`carddavmate <https://www.inf-it.com/open-source/clients/carddavmate/>`_
- `evolution <https://wiki.gnome.org/Apps/Evolution>`_
- `DAVx5 <https://www.davx5.com/>`_ (formerly DAVDroid)
- `sogo connector for Icedove/Thunderbird <http://v2.sogo.nu/english/downloads/frontends.html>`_
- `aCALdav syncer for Android <https://play.google.com/store/apps/details?id=de.we.acaldav&hl=en>`_
- `pycardsyncer <https://github.com/geier/pycarddav>`_
- `akonadi <https://community.kde.org/KDE_PIM/Akonadi>`_
- `CalDAV-Sync <https://dmfs.org/caldav/>`_
- `CardDAV-Sync <https://dmfs.org/carddav/>`_
- `Calendarsync <https://play.google.com/store/apps/details?id=com.icalparse>`_
- `Tasks <https://github.com/tasks/tasks/tree/caldav>`_
- `AgendaV <http://agendav.org/>`_
- `CardBook <https://gitlab.com/cardbook/cardbook/>`_
- Apple's iOS

Dependencies
============

At the moment, Xandikos supports Python 3.4 and higher as well as Pypy 3. It
also uses `Dulwich <https://github.com/dulwich/dulwich>`_,
`Jinja2 <http://jinja.pocoo.org/>`_,
`icalendar <https://github.com/collective/icalendar>`_, and
`defusedxml <https://github.com/tiran/defusedxml>`_.

E.g. to install those dependencies on Debian:

.. code:: shell

  sudo apt install python3-dulwich python3-defusedxml python3-icalendar python3-jinja2

Or to install them using pip:

.. code:: shell

  python setup.py develop

Docker
------

A Dockerfile is also provided; see the comments on the top of the file for
configuration instructions.

Running
=======

Testing
-------

To run a standalone (low-performance, no authentication) instance of Xandikos,
with a pre-created calendar and addressbook (storing data in *$HOME/dav*):

.. code:: shell

  ./bin/xandikos --defaults -d $HOME/dav

A server should now be listening on `localhost:8080 <http://localhost:8080/>`_.

Note that Xandikos does not create any collections unless --defaults is
specified. You can also either create collections from your CalDAV/CardDAV client,
or by creating git repositories under the *contacts* or *calendars* directories
it has created.

Production
----------

The easiest way to run Xandikos in production is using
`uWSGI <https://uwsgi-docs.readthedocs.io/en/latest/>`_.

One option is to setup uWSGI with a server like
`Apache <http://uwsgi-docs.readthedocs.io/en/latest/Apache.html>`_,
`Nginx <http://uwsgi-docs.readthedocs.io/en/latest/Nginx.html>`_ or another web
server that can authenticate users and forward authorized requests to
Xandikos in uWSGI. See `examples/uwsgi.ini <examples/uwsgi.ini>`_ for an
example uWSGI configuration.

Alternatively, you can run uWSGI standalone and have it authenticate and
directly serve HTTP traffic. An example configuration for this can be found in
`examples/uwsgi-standalone.ini <examples/uwsgi-standalone.ini>`_.

This will start a server on `localhost:8080 <http://localhost:8080/>`_ with username *user1* and password
*password1*.

.. code:: shell

  mkdir -p $HOME/dav
  uwsgi examples/uwsgi-standalone.ini

Client instructions
===================

Some clients can automatically discover the calendars and addressbook URLs from
a DAV server (if they support RFC:`5397`). For such clients you can simply
provide the base URL to Xandikos during setup.

Clients that lack such automated discovery (e.g. Thunderbird Lightning) require
the direct URL to a calendar or addressbook. In this case you
should provide the full URL to the calendar or addressbook; if you initialized
Xandikos using the ``--defaults`` argument mentioned in the previous section,
these URLs will look something like this::

  http://dav.example.com/user/calendars/calendar

  http://dav.example.com/user/contacts/addressbook


Contributing
============

Contributions to Xandikos are very welcome. If you run into bugs or have
feature requests, please file issues `on GitHub
<https://github.com/jelmer/xandikos/issues/new>`_. If you're interested in
contributing code or documentation, please read `CONTRIBUTING
<CONTRIBUTING.rst>`_. Issues that are good for new contributors are tagged
`new-contributor <https://github.com/jelmer/xandikos/labels/new-contributor>`_
on GitHub.

Help
====

There is a *#xandikos* IRC channel on the `Freenode <https://www.freenode.net/>`_
IRC network, and a `Xandikos <https://groups.google.com/forum/#!forum/xandikos>`_
mailing list.

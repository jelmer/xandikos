Per-collection configuration
============================

Xandikos needs to store several piece of per-collection metadata.

Goals
-----

Find a place to store per-collection metadata.

Some of these can be inferred from other sources.

For starters, for each collection:

- resource types: principal, calendar, addressbook

At the moment, Xandikos is storing some of this information in git configuration. However, this means:

* it is not versioned
* there is a 1-1 relationship between collections and git repositories
* some users object to mixing in this metadata in their git config

Per resource type-specific properties
-------------------------------------

Generic
~~~~~~~

- ACLs
- owner?

Principal
~~~~~~~~~

Per principal configuration settings:

- calendar home sets
- addressbook home sets
- user address set
- infit settings

Calendar
~~~~~~~~

Need per calendar config:

- color
- description (can be inferred from .git/description)
- inbox URL
- outbox URL
- max instances
- max attendees per instance
- calendar timezone
- calendar schedule transparency

Addressbook
~~~~~~~~~~~

Need per addressbook config:

- max image size
- max resource size
- color
- description (can be inferred from .git/description)

Schedule Inbox
~~~~~~~~~~~~~~
- default-calendar-URL

Proposed format
---------------

Store a ini-style .xandikos file in the directory hosting the Collection (or
Tree in case of a Git repository).

All properties mentioned above are simple key/value pairs. For simplicity, it
may make sense to use an ini-style format so that users can edit metadata using their editor.

Example
-------
# This is a standard Python configobj file, so it's mostly ini-style, and comments
# can appear preceded by #.

color = 030003

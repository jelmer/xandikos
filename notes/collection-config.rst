Per-collection configuration
============================

Xandikos needs to store several piece of per-collection metadata.

Some of these can be inferred from other sources.

For starters, for each collection:

- resource types: principal, calendar, addressbook

Per resource type-specific properties
-------------------------------------

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

Example
-------
# This is a standard Python configobj file, so it's mostly ini-style, and comments
# can appear preceded by #.

color = 030003



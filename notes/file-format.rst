===========================
File Format Specification
===========================

Overview
========

Xandikos stores WebDAV/CalDAV/CardDAV collections as either Git repositories or plain
vdir-format directories on disk. This document specifies the format requirements and
configuration options.

Storage Backends
================

Git Backend
-----------

Collections are represented as Git repositories. Version control enables:

* **Collection version tracking**: A specific version is represented as a commit id
* **Collection tag (ctag)**: The ctag for a collection is taken from the tree id of the
  collection root tree
* **Entity tags (etag)**: The etag for a resource is taken from the blob id of the blob
  representing that resource. These are strong entity tags since blobs are compared by
  octet equality (see RFC 2616 Section 3.11)

Vdir Backend
------------

Collections are represented as plain directories following the vdir format specification
(see https://github.com/pimutils/vdirsyncer/blob/master/docs/vdir.rst).

vdir Format Constraints
========================

Both Git and vdir storage backends follow the vdir format for individual files:

File Requirements
-----------------

* Each ``.ics`` file MUST contain exactly one calendar object (VEVENT, VTODO, VJOURNAL, or VFREEBUSY)
* Each ``.vcf`` file MUST contain exactly one addressbook object (VCARD)
* All components within a single file MUST share the same UID property
* Each UID within a collection MUST be unique across all files
* File names MUST use the appropriate extension:

  - ``.ics`` for calendar files (``text/calendar`` MIME type)
  - ``.vcf`` for vCard files (``text/vcard`` MIME type)

* All items in a collection MUST be well-formed and valid so that they do not require
  validation when served

Validation
----------

These constraints are enforced during file import. Files that violate these requirements
will be rejected with a validation error:

* **Missing UID**: ``Calendar file must contain at least one component with a UID``
* **Inconsistent UIDs**: ``Calendar file must have consistent UID across all components, found: <list>``
* **Duplicate UID**: Files with duplicate UIDs within a collection are rejected
* **Invalid format**: Files with syntax errors or invalid iCalendar/vCard data are rejected

Metadata Storage
================

Collection metadata (colors, descriptions, display names, etc.) is stored differently
depending on the storage backend.

Git Backend Metadata
--------------------

For Git-backed collections, metadata is stored in ``.git/config`` under the ``[xandikos]``
section using Git's INI-style configuration format.

Example::

    [xandikos]
        type = calendar
        displayname = My Calendar
        color = #FF5733
        source = https://example.com/calendar.ics
        refreshrate = PT1H
        comment = Personal calendar for work events

File-based Backend Metadata
----------------------------

For file-based (vdir) collections, metadata is stored in the ``.xandikos/`` directory:

* ``.xandikos/config`` - INI-format configuration file (Python configparser format)
* ``.xandikos/availability.ics`` - Optional calendar availability information (RFC 6638)

Legacy format: The ``.xandikos`` file (plain file, not directory) is supported for
backwards compatibility but SHOULD NOT be used for new collections.

Example ``.xandikos/config``::

    [DEFAULT]
    type = calendar
    displayname = My Calendar
    description = Personal calendar for work events
    color = #FF5733
    source = https://example.com/calendar.ics
    refreshrate = PT1H
    comment = Calendar synchronized from external source

    [calendar]
    order = 10

Metadata files and directories (anything matching ``.xandikos``, ``.xandikos/``, or
``.xandikos/*``) are automatically hidden from collection listings and are not exposed
as collection members to CalDAV/CardDAV clients.

Configuration Properties
=========================

Common Properties
-----------------

These properties apply to all collection types:

``type`` (required)
    Collection type identifier. Valid values:

    * ``calendar`` - CalDAV calendar collection (RFC 4791)
    * ``addressbook`` - CardDAV addressbook collection (RFC 6352)
    * ``principal`` - WebDAV principal collection
    * ``schedule-inbox`` - CalDAV scheduling inbox (RFC 6638)
    * ``schedule-outbox`` - CalDAV scheduling outbox (RFC 6638)
    * ``subscription`` - Calendar subscription
    * ``other`` - Other collection type

    **Format**: String

    **WebDAV mapping**: Collection resource type

``displayname`` (optional)
    Human-readable name for the collection.

    **Format**: UTF-8 string

    **WebDAV mapping**: ``DAV:displayname`` property (RFC 4918 Section 15.2)

``description`` (optional)
    Longer description of the collection's purpose or contents.

    **Format**: UTF-8 string

    **Git backend**: Stored in ``.git/description`` (repository description)

    **File backend**: Stored as ``description`` in ``[DEFAULT]`` section

    **CalDAV mapping**: ``CALDAV:calendar-description`` property (RFC 4791 Section 5.2.1)

``comment`` (optional)
    Additional comments or notes about the collection.

    **Format**: UTF-8 string

    **WebDAV mapping**: Not exposed via WebDAV properties (internal use only)

``color`` (optional)
    Display color for the collection, typically used by calendar/contact clients.

    **Format**: CSS color value (e.g., ``#FF5733``, ``rgb(255,87,51)``)

    **WebDAV mapping**: ``{http://apple.com/ns/ical/}calendar-color`` property (Apple extension)

``source`` (optional)
    Source URL for subscribed or synchronized collections.

    **Format**: Absolute URL (e.g., ``https://example.com/calendar.ics``)

    **WebDAV mapping**: ``{http://calendarserver.org/ns/}source`` property

Calendar-Specific Properties
-----------------------------

These properties only apply to calendar collections (``type = calendar``):

``refreshrate`` (optional)
    Recommended refresh interval for clients to re-fetch the collection.

    **Format**: ISO 8601 duration (e.g., ``PT1H`` = 1 hour, ``P1D`` = 1 day)

    **WebDAV mapping**: ``{http://apple.com/ns/ical/}refreshrate`` property (Apple CalendarServer extension)

``timezone`` (optional)
    Default timezone for the calendar collection.

    **Format**: Complete iCalendar VTIMEZONE component as a string (RFC 5545)

    **Example**::

        BEGIN:VTIMEZONE\r\nTZID:America/New_York\r\nEND:VTIMEZONE

    **WebDAV mapping**: ``CALDAV:calendar-timezone`` property (RFC 4791 Section 5.2.3)

``order`` (optional)
    Display ordering hint for calendar clients.

    **Format**: Integer as string (e.g., ``10``, ``20``)

    **Git backend**: Stored as ``calendar-order`` in ``[xandikos]`` section

    **File backend**: Stored as ``order`` in ``[calendar]`` section

    **WebDAV mapping**: ``{http://apple.com/ns/ical/}calendar-order`` property (Apple extension)

Property Storage Details
========================

Git Backend Storage
-------------------

In ``.git/config``::

    [xandikos]
        type = <type>
        displayname = <displayname>
        color = <color>
        comment = <comment>
        source = <source>
        refreshrate = <refreshrate>
        timezone = <timezone>
        calendar-order = <order>

Description is stored in ``.git/description`` (Git's native repository description).

File Backend Storage
--------------------

In ``.xandikos/config``::

    [DEFAULT]
    type = <type>
    displayname = <displayname>
    description = <description>
    color = <color>
    comment = <comment>
    source = <source>
    refreshrate = <refreshrate>
    timezone = <timezone>

    [calendar]
    order = <order>

Open Questions
==============

* How to handle subtrees? Are they just subcollections?

File structure
==============

Collections are represented as Git repositories on disk.

A specific version is represented as a commit id. The 'ctag' for a calendar is taken from the
tree id of the calendar root tree.

The `entity tag`_ for an event is taken from the blob id of the Blob representing that EVENT. These kinds
of entity tags are strong, since blobs are equivalent by octet equality.

.. _entity tag: https://tools.ietf.org/html/rfc2616#section-3.11

The file name of calendar events shall be <NAME>.ics / <NAME>.vcf. Because of
this, every file MUST only contain one UID and thus MUST contain exactly one
VEVENT, VTODO, VJOURNAL or VFREEBUSY.

All items in a collection *must* be well formed, so that they do not have to be validated when served.

When new items are added, the collection should verify no existing items have the same UID.

Open questions:

- How to handle subtrees? Are they just subcollections?
- Where should collection metadata (e.g. colors, description) be stored? .git/config?

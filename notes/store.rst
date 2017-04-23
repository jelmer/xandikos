Dulwich Store
=============

The main building blocks are vCard (.vcf) and iCalendar (.ics) files. Storage
happens in Git repositories.

Most items are identified by a UID and a filename, both of which are unique for
the store. Items can have multiple versions, which are identified by an ETag.
Each store maps to a single Git repository, and can not contain directories. In
the future, a store could map to a subtree in a Git repository.

Stores are responsible for making sure that:

- their contents are validly formed calendars/contacts
- UIDs are unique (where relevant)

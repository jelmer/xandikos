Indexes
=======

There are several API calls that would be good to speed up. In particular,
querying an entire calendar with filters is quite slow because it involves
scanning all the items.

There are a couple of common filters:

 Component filters that filter for only VTODO or VEVENT items
 Property filters that filter for a specific UID
 Property filters that filter for another property
 Property filters that do complex text searches, e.g. in DESCRIPTION

Indexes are an implementation detail of the Store. This is necessary so that
e.g. the Git stores can take advantage that they have a tree hash.

One option would be to serialize the filter and then to keep a list of results
per (tree_id, filter_hash). Unfortunately this by itself is not enough, since
it doesn't help when we get repeated queries for different UIDs.

Options considered:

* Have some pre-set indexes. Perhaps components, and UID?
* Cache but use the rightmost value as a key in a dict
* Always just cache everything that was queried. This is probably actually fine.

Filter Performance
==================

There are several API calls that would be good to speed up. In particular,
querying an entire calendar with filters is quite slow because it involves
scanning all the items.

Common Filters
~~~~~~~~~~~~~~

There are a couple of common filters:

 Component filters that filter for only VTODO or VEVENT items
 Property filters that filter for a specific UID
 Property filters that filter for another property
 Property filters that do complex text searches, e.g. in DESCRIPTION
 Property filters that filter for some time range.

But these are by no means the only possible filters, and there is no
predicting what clients will scan for.

Indexes are an implementation detail of the Store. This is necessary so that
e.g. the Git stores can take advantage of the fact that they have a tree hash.

One option would be to serialize the filter and then to keep a list of results
per (tree_id, filter_hash). Unfortunately this by itself is not enough, since
it doesn't help when we get repeated queries for different UIDs.

Options considered:

* Have some pre-set indexes. Perhaps components, and UID?
* Cache but use the rightmost value as a key in a dict
* Always just cache everything that was queried. This is probably actually fine.
* Count how often a particular index is used

Open Questions
~~~~~~~~~~~~~~

* How are indexes identified?

Proposed API
~~~~~~~~~~~~

class Filter(object):

    def check_slow(self, name, resource):
       """Check whether this filter applies to a resources based on the actual
       resource.

       This is the naive, slow, fallback implementation.

       Args:
         resource: Resource to check
       """
       raise NotImplementedError(self.check_slow)

    def check_index(self, values):
       """Check whether this filter applies to a resources based on index values.

       Args:
         values: Dictionary mapping indexes to index values
       """
       raise NotImplementedError(self.check_index)

    def required_indexes(self):
       """Return a list of indexes that this Filter needs to function.

       Returns: List of ORed options, similar to a Depends line in Debian
       """
       raise NotImplementedError(self.required_indexes)


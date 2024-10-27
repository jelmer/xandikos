use crate::store::File;
use std::collections::HashMap;

pub enum IndexValueElement {
    Bytes(Vec<u8>),
    Bool(bool),
}

pub type IndexKey = String;
pub type IndexValue = Vec<IndexValueElement>;
pub type IndexValueIterator = Box<dyn Iterator<Item = IndexValueElement>>;
pub type IndexDict = HashMap<IndexKey, IndexValue>;

pub trait IndexableFile: File {
    /// Obtain an index for this file.
    ///
    /// # Arguments
    /// * `key` - Index key
    ///
    /// # Returns
    /// Iterator over index values
    fn get_index(&self, key: &IndexKey) -> IndexValueIterator;

    /// Obtain indexes for this file.
    ///
    /// # Arguments
    /// * `keys` - Iterable of index keys
    ///
    /// # Returns
    /// Dictionary mapping key names to values
    fn get_indexes(&self, keys: Vec<IndexKey>) -> IndexDict {
        let mut ret = IndexDict::new();
        for k in keys {
            let v = self.get_index(&k).collect::<Vec<_>>();
            ret.insert(k, v);
        }
        ret
    }
}

/// A filter that can be used to query for certain resources.
///
/// Filters are often resource-type specific.
pub trait Filter {
    /// The content type that this filter applies to.
    fn content_type() -> &'static str;

    /// Check if this filter applies to a resource.
    ///
    /// # Arguments
    /// * `name` - Name of the resource
    /// * `resource` - File object
    fn check(&self, name: &str, resource: &dyn File) -> bool;

    /// Returns a list of indexes that could be used to apply this filter.
    ///
    /// # Returns:
    /// AND-list of OR-options
    fn index_keys(&self) -> Vec<IndexKey>;

    /// Check from a set of indexes whether a resource matches.
    ///
    /// # Arguments
    /// * `name` - Name of the resource
    /// * `indexes` - Dictionary mapping index names to values
    fn check_from_indexes(&self, name: &str, indexes: IndexDict) -> bool;
}

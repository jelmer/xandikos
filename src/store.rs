pub enum Error {
    /// The file is not valid.
    InvalidFileContents,

    /// The file does not contain a UID.
    NoUID,
}

/// A file type handler.
pub trait File {
    fn content_type(&self) -> &str;
    fn content(&self) -> &[Vec<u8>];

    /// Verify that file contents are valid.
    fn validate(&self) -> Result<(), Error>;

    /// Return a normalized version of the file.
    fn normalized(&self) -> Vec<Vec<u8>>;

    /// Describe the contents of this file.
    ///
    /// Used in e.g. commit messages.
    fn describe(&self, name: &str) -> String;

    /// Return UID.
    ///
    /// Raises:
    /// * NotImplementedError: If UIDs aren't supported for this format
    /// * NoUID: If there is no UID set on this file
    /// * InvalidFileContents: If the file is misformatted
    fn get_uid(&self) -> Result<String, Error>;

    /// Describe the important difference between this and previous one.
    ///
    /// # Arguments
    /// * `name` - File name
    /// * `previous` - Previous file to compare to.
    fn describe_delta(&self, name: &str, previous: Option<&dyn File>) -> Vec<String> {
        let item_description = self.describe(name);
        if previous.is_none() {
            vec!["Added ".to_string() + &item_description]
        } else {
            vec!["Modified ".to_string() + &item_description]
        }
    }
}

use pyo3::create_exception;
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};
use std::iter::FromIterator;

create_exception!(
    xandikos,
    NotAcceptableError,
    pyo3::exceptions::PyException,
    "NotAcceptableError"
);

#[pyfunction]
/// Parse a content-type style header.
///
/// Args:
///   content_type: type to parse
/// Returns: Tuple with base name and dict with params
fn pick_content_types(
    py: Python,
    accepted_content_types: Vec<(String, HashMap<String, String>)>,
    available_content_types: PyObject,
) -> PyResult<Vec<String>> {
    let available_content_types: HashSet<String> =
        HashSet::from_iter(available_content_types.extract::<Vec<String>>(py)?);
    let iter =
        xandikos::webdav::pick_content_types(accepted_content_types, available_content_types);

    let ret = iter.collect::<Vec<String>>();

    if ret.is_empty() {
        return Err(NotAcceptableError::new_err("No acceptable content types"));
    }

    Ok(ret)
}

#[pyfunction]
/// Parse a HTTP Accept or Accept-Language header.
///
/// Args:
///  accept: Accept header contents
/// Returns: List of (content_type, params) tuples
fn parse_accept_header(accept: &str) -> PyResult<Vec<(String, HashMap<String, String>)>> {
    let iter = xandikos::webdav::parse_accept_header(accept);
    Ok(iter)
}

#[pyfunction]
fn parse_type(content_type: &str) -> PyResult<(String, HashMap<String, String>)> {
    let (type_, params) = xandikos::webdav::parse_type(content_type);
    Ok((type_, params))
}

#[pyfunction]
/// Check if an etag matches an If-Matches condition.
///
/// Args:
///   condition: Condition (e.g. '*', '"foo"' or '"foo", "bar"'
///   actual_etag: ETag to compare to. None nonexistant
/// Returns: bool indicating whether condition matches
#[pyo3(signature = (condition=None, actual_etag=None))]
fn etag_matches(condition: Option<&str>, actual_etag: Option<&str>) -> PyResult<bool> {
    Ok(xandikos::webdav::etag_matches(condition, actual_etag))
}

#[pymodule]
fn _xandikos_rs(py: Python, m: &Bound<PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(pick_content_types, m)?)?;
    m.add_function(wrap_pyfunction!(parse_type, m)?)?;
    m.add_function(wrap_pyfunction!(parse_accept_header, m)?)?;
    m.add_function(wrap_pyfunction!(etag_matches, m)?)?;
    m.add("NotAcceptableError", py.get_type::<NotAcceptableError>())?;
    Ok(())
}

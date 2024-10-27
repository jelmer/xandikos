use std::collections::HashMap;

/// Parse a content-type style header.
///
/// # Arguments
/// * `content_type` - type to parse
///
/// # Returns
/// Tuple with base name and dict with params
pub fn parse_type(content_type: &str) -> (String, HashMap<String, String>) {
    let mut params = HashMap::new();
    match content_type.trim().split_once(';') {
        Some((ct, rest)) => {
            for param in rest.split(';') {
                let (key, val) = match param.split_once('=') {
                    Some((k, v)) => (k, v),
                    None => (param, ""),
                };
                params.insert(key.trim().to_string(), val.trim().to_string());
            }
            (ct.to_string(), params)
        }
        Option::None => (content_type.trim().to_string(), params),
    }
}

/// Parse a HTTP Accept or Accept-Language header.
///
/// # Arguments
/// * `accept` - Accept header contents
///
/// # Returns
/// List of (content_type, params) tuples
pub fn parse_accept_header(accept: &str) -> Vec<(String, HashMap<String, String>)> {
    let mut ret = Vec::new();
    for part in accept.split(',') {
        if part.is_empty() {
            continue;
        }
        let (base, params) = parse_type(part);
        ret.push((base, params));
    }
    ret
}

/// Pick best content types for a client.
///
/// # Arguments
/// * `accepted_content_types` - Accept variable (as name, params tuples)
/// * `available_content_types` - List of available content types
///
/// # Returns
/// List of content types that are acceptable, in order of preference
pub fn pick_content_types(
    accepted_content_types: Vec<(String, HashMap<String, String>)>,
    mut available_content_types: std::collections::HashSet<String>,
) -> impl Iterator<Item = String> + 'static {
    let mut acceptable_by_q = Vec::new();
    for (ct, params) in accepted_content_types.into_iter() {
        let q = params
            .get("q")
            .unwrap_or(&"1".to_string())
            .parse::<f64>()
            .unwrap();

        acceptable_by_q.push((q, ct.clone()));
    }
    acceptable_by_q.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
    acceptable_by_q.reverse();

    acceptable_by_q
        .into_iter()
        .filter(move |(q, _)| *q > 0.0)
        .flat_map(move |(_, pat)| {
            let pat = glob::Pattern::new(&pat).unwrap();
            let mut matched_types = Vec::new();
            for ct in available_content_types.iter() {
                if pat.matches(ct) {
                    matched_types.push(ct.clone());
                }
            }
            matched_types.sort();
            for ct in matched_types.iter() {
                available_content_types.remove(ct);
            }
            matched_types
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_type() {
        let (base, params) = parse_type("text/plain; charset=utf-8");
        assert_eq!(base, "text/plain");
        assert_eq!(params.get("charset").unwrap(), "utf-8");

        let (base, params) = parse_type("text/plain");
        assert_eq!(base, "text/plain");
        assert_eq!(params.len(), 0);
    }

    #[test]
    fn test_parse_accept_header() {
        let accept = "text/plain; q=0.5, text/html, text/x-dvi; q=0.8, text/x-c";
        let parsed = parse_accept_header(accept);
        assert_eq!(parsed.len(), 4);
        assert_eq!(parsed[0].0, "text/plain");
        assert_eq!(parsed[0].1.get("q").unwrap(), "0.5");
        assert_eq!(parsed[1].0, "text/html");
        assert_eq!(parsed[1].1.len(), 0);
        assert_eq!(parsed[2].0, "text/x-dvi");
        assert_eq!(parsed[2].1.get("q").unwrap(), "0.8");
        assert_eq!(parsed[3].0, "text/x-c");
        assert_eq!(parsed[3].1.len(), 0);
    }

    #[test]
    fn test_pick_content_types_simple() {
        let accepted = vec![
            ("text/*".to_string(), HashMap::new()),
            ("text/plain".to_string(), HashMap::new()),
            ("text/*".to_string(), HashMap::new()),
            ("text/*".to_string(), HashMap::new()),
        ];
        let available = [
            "text/plain".to_string(),
            "text/html".to_string(),
            "text/x-dvi".to_string(),
            "text/x-c".to_string(),
        ]
        .iter()
        .cloned()
        .collect();
        let picked =
            pick_content_types(accepted, available).collect::<std::collections::HashSet<_>>();
        let expected = [
            "text/plain".to_string(),
            "text/html".to_string(),
            "text/x-dvi".to_string(),
            "text/x-c".to_string(),
        ]
        .into_iter()
        .collect::<std::collections::HashSet<_>>();
        assert_eq!(picked, expected);
    }

    #[test]
    fn test_pick_content_types_with_q() {
        let accepted = vec![
            ("text/*".to_string(), {
                let mut ps = HashMap::new();
                ps.insert("q".to_string(), "0.5".to_string());
                ps
            }),
            ("text/plain".to_string(), {
                let mut ps = HashMap::new();
                ps.insert("q".to_string(), "0.8".to_string());
                ps
            }),
        ];
        let available = [
            "text/plain".to_string(),
            "text/html".to_string(),
            "text/x-dvi".to_string(),
            "text/x-c".to_string(),
        ]
        .iter()
        .cloned()
        .collect();
        let picked = pick_content_types(accepted, available).collect::<Vec<_>>();
        assert_eq!(
            picked,
            vec![
                "text/plain".to_string(),
                "text/html".to_string(),
                "text/x-c".to_string(),
                "text/x-dvi".to_string(),
            ]
        );
    }
}

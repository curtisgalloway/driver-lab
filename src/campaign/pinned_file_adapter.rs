use serde_json::{json, Value};
use sha2::{Digest, Sha256};

pub fn check_blob(content: &[u8], expected: Option<&str>) -> serde_json::Map<String, Value> {
    let mut hasher = Sha256::new();
    hasher.update(content);
    let actual = hex::encode(hasher.finalize());
    let mut map = serde_json::Map::new();
    map.insert("actual".to_string(), json!(actual));
    if let Some(exp) = expected {
        map.insert(
            "status".to_string(),
            json!(if actual == exp { "ok" } else { "drift" }),
        );
    } else {
        map.insert("status".to_string(), json!("ok"));
    }
    map
}

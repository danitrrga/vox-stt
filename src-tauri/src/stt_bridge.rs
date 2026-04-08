use serde_json::Value;
use std::sync::OnceLock;
use std::time::Duration;

const BASE_URL: &str = "http://127.0.0.1:9876";

fn client() -> &'static reqwest::Client {
    static CLIENT: OnceLock<reqwest::Client> = OnceLock::new();
    CLIENT.get_or_init(|| reqwest::Client::builder().build().unwrap())
}

pub async fn get_status() -> Result<Value, Box<dyn std::error::Error>> {
    let resp = client()
        .get(format!("{BASE_URL}/api/status"))
        .timeout(Duration::from_secs(5))
        .send()
        .await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

pub async fn start_recording() -> Result<Value, Box<dyn std::error::Error>> {
    let resp = client()
        .post(format!("{BASE_URL}/api/record/start"))
        .timeout(Duration::from_secs(5))
        .send()
        .await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

pub async fn stop_recording(format: bool) -> Result<Value, Box<dyn std::error::Error>> {
    let resp = client()
        .post(format!("{BASE_URL}/api/record/stop?format={format}"))
        .timeout(Duration::from_secs(300))
        .send()
        .await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

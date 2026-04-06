use serde_json::Value;

const BASE_URL: &str = "http://127.0.0.1:9876";

pub async fn get_status() -> Result<Value, Box<dyn std::error::Error>> {
    let resp = reqwest::get(format!("{BASE_URL}/api/status")).await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

pub async fn start_recording() -> Result<Value, Box<dyn std::error::Error>> {
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{BASE_URL}/api/record/start"))
        .send()
        .await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

pub async fn stop_recording(format: bool) -> Result<Value, Box<dyn std::error::Error>> {
    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{BASE_URL}/api/record/stop?format={format}"))
        .send()
        .await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

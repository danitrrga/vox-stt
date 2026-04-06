use std::sync::Arc;
use tauri::async_runtime::Mutex;

/// Simple toggle state for the hotkey.
/// Press once to start recording, press again to stop and transcribe.
pub struct HotkeyState {
    pub recording: bool,
}

impl HotkeyState {
    pub fn new() -> Arc<Mutex<Self>> {
        Arc::new(Mutex::new(Self { recording: false }))
    }

    pub fn toggle(&mut self) -> HotkeyAction {
        if self.recording {
            self.recording = false;
            HotkeyAction::StopAndTranscribe
        } else {
            self.recording = true;
            HotkeyAction::StartRecording
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum HotkeyAction {
    StartRecording,
    StopAndTranscribe,
}

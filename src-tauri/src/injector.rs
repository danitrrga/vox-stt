use arboard::Clipboard;
use enigo::{Enigo, Key, Keyboard, Settings};
use std::thread;
use std::time::Duration;

/// Inject text into the active window via clipboard + Ctrl+V.
/// Saves and restores the previous clipboard content.
pub fn inject_text(text: &str) -> Result<(), String> {
    if text.is_empty() {
        return Ok(());
    }

    let mut clipboard = Clipboard::new().map_err(|e| format!("Clipboard error: {e}"))?;

    // Save current clipboard
    let previous = clipboard.get_text().ok();

    // Write new text
    clipboard
        .set_text(text)
        .map_err(|e| format!("Failed to set clipboard: {e}"))?;

    // Small delay to ensure clipboard is ready
    thread::sleep(Duration::from_millis(50));

    // Simulate Ctrl+V
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| format!("Enigo error: {e}"))?;
    enigo
        .key(Key::Control, enigo::Direction::Press)
        .map_err(|e| format!("Key press error: {e}"))?;
    enigo
        .key(Key::Unicode('v'), enigo::Direction::Click)
        .map_err(|e| format!("Key click error: {e}"))?;
    enigo
        .key(Key::Control, enigo::Direction::Release)
        .map_err(|e| format!("Key release error: {e}"))?;

    // Restore previous clipboard after a short delay
    thread::sleep(Duration::from_millis(150));
    if let Some(prev) = previous {
        let _ = clipboard.set_text(prev);
    }

    Ok(())
}

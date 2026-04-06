mod hotkey;
mod injector;
mod stt_bridge;

use hotkey::{HotkeyAction, HotkeyState};
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

#[tauri::command]
async fn get_status() -> Result<serde_json::Value, String> {
    stt_bridge::get_status().await.map_err(|e| e.to_string())
}

#[tauri::command]
async fn start_recording() -> Result<serde_json::Value, String> {
    stt_bridge::start_recording().await.map_err(|e| e.to_string())
}

#[tauri::command]
async fn stop_recording(format: bool) -> Result<serde_json::Value, String> {
    stt_bridge::stop_recording(format).await.map_err(|e| e.to_string())
}

#[tauri::command]
fn inject_text(text: String) -> Result<(), String> {
    injector::inject_text(&text)
}

pub fn run() {
    let hotkey_state = HotkeyState::new();

    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            get_status,
            start_recording,
            stop_recording,
            inject_text,
        ])
        .setup(move |app| {
            // --- Tray ---
            let show = MenuItem::with_id(app, "show", "Show Vox", true, None::<&str>)?;
            let separator = PredefinedMenuItem::separator(app)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &separator, &quit])?;

            TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(false)
                .tooltip("Vox — Speech to Text")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            // --- Global Shortcut: Ctrl+Shift+Space ---
            let shortcut = Shortcut::new(
                Some(Modifiers::CONTROL | Modifiers::SHIFT),
                Code::Space,
            );
            let state = hotkey_state.clone();
            let handle = app.handle().clone();

            app.global_shortcut().on_shortcut(shortcut, move |_app, _shortcut, event| {
                // Only act on key press, ignore release
                if event.state == ShortcutState::Released {
                    return;
                }

                let state = state.clone();
                let handle = handle.clone();

                tauri::async_runtime::spawn(async move {
                    let mut s = state.lock().await;
                    let action = s.toggle();
                    drop(s);

                    let overlay = handle.get_webview_window("overlay");

                    match action {
                        HotkeyAction::StartRecording => {
                            if let Some(ref w) = overlay { let _ = w.show(); }
                            let _ = handle.emit("vox-state", "recording");
                            let _ = stt_bridge::start_recording().await;
                        }
                        HotkeyAction::StopAndTranscribe => {
                            let _ = handle.emit("vox-state", "processing");
                            match stt_bridge::stop_recording(true).await {
                                Ok(result) => {
                                    if let Some(text) = result.get("formatted").and_then(|v| v.as_str()) {
                                        if !text.is_empty() {
                                            let text = text.to_string();
                                            std::thread::spawn(move || {
                                                let _ = injector::inject_text(&text);
                                            });
                                            let _ = handle.emit("vox-result", &result);
                                        }
                                    }
                                    let _ = handle.emit("vox-state", "idle");
                                    // Hide overlay after "done" flash
                                    let overlay_hide = handle.get_webview_window("overlay");
                                    tauri::async_runtime::spawn(async move {
                                        tokio::time::sleep(std::time::Duration::from_millis(1800)).await;
                                        if let Some(w) = overlay_hide { let _ = w.hide(); }
                                    });
                                }
                                Err(e) => {
                                    eprintln!("Transcription error: {e}");
                                    let _ = handle.emit("vox-state", "idle");
                                    if let Some(ref w) = overlay { let _ = w.hide(); }
                                }
                            }
                        }
                    }
                });
            })?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Vox");
}

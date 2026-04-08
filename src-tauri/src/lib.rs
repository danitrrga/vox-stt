mod injector;
mod keyboard_hook;
mod stt_bridge;

use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex as StdMutex};
use std::time::Instant;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, RunEvent,
};

struct VoxState {
    current_shortcut: String,
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

#[tauri::command]
fn unregister_hotkey() -> Result<(), String> {
    keyboard_hook::set_enabled(false);
    Ok(())
}

#[tauri::command]
fn update_hotkey(
    state: tauri::State<'_, StdMutex<VoxState>>,
    hotkey: String,
) -> Result<String, String> {
    let vk_codes = keyboard_hook::parse_hotkey_to_vk(&hotkey);
    if vk_codes.is_empty() {
        return Err(format!("Invalid hotkey: {hotkey}"));
    }

    keyboard_hook::update_target(&hotkey);
    keyboard_hook::set_enabled(true);

    let mut vox = state.lock().map_err(|e| e.to_string())?;
    vox.current_shortcut = hotkey.clone();
    Ok(hotkey)
}


#[tauri::command]
fn set_run_on_startup(enabled: bool) -> Result<bool, String> {
    let vbs_path = r#"c:\Users\20252128\dev\Projects\LifeOS\scripts\vox_startup.vbs"#;
    let key_path = r"Software\Microsoft\Windows\CurrentVersion\Run";

    let hkcu = winreg::RegKey::predef(winreg::enums::HKEY_CURRENT_USER);
    let (run_key, _) = hkcu
        .create_subkey(key_path)
        .map_err(|e| format!("Registry error: {e}"))?;

    if enabled {
        let cmd = format!(r#"wscript.exe "{vbs_path}""#);
        run_key
            .set_value("Vox", &cmd)
            .map_err(|e| format!("Failed to set registry: {e}"))?;
        eprintln!("Startup enabled: {cmd}");
    } else {
        let _ = run_key.delete_value("Vox");
        eprintln!("Startup disabled");
    }
    Ok(enabled)
}

#[tauri::command]
fn get_run_on_startup() -> Result<bool, String> {
    let key_path = r"Software\Microsoft\Windows\CurrentVersion\Run";
    let hkcu = winreg::RegKey::predef(winreg::enums::HKEY_CURRENT_USER);
    match hkcu.open_subkey(key_path) {
        Ok(run_key) => {
            let val: Result<String, _> = run_key.get_value("Vox");
            Ok(val.is_ok())
        }
        Err(_) => Ok(false),
    }
}

/// Read hotkey from config.json on disk.
fn read_hotkey_from_disk() -> String {
    let default = "Ctrl+Shift+Space".to_string();
    let appdata = match std::env::var("APPDATA") {
        Ok(v) => v,
        Err(_) => return default,
    };
    let config_path = std::path::Path::new(&appdata).join("vox").join("config.json");
    let content = match std::fs::read_to_string(&config_path) {
        Ok(v) => v,
        Err(_) => return default,
    };
    let json: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(_) => return default,
    };
    json.get("hotkey")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .unwrap_or(default)
}

fn spawn_stt_server() -> Option<Child> {
    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    let project_root = std::path::Path::new(manifest_dir).parent()?;
    let server_dir = project_root.join("stt-server");
    let python = server_dir.join(".venv/Scripts/python.exe");

    match Command::new(&python)
        .arg("server.py")
        .current_dir(&server_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(child) => {
            eprintln!("STT server spawned (pid {})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("Failed to spawn STT server: {e}");
            None
        }
    }
}

pub fn run() {
    let server_process: Arc<StdMutex<Option<Child>>> = Arc::new(StdMutex::new(None));
    let server_for_exit = server_process.clone();

    let saved_hotkey = read_hotkey_from_disk();
    eprintln!("Loaded hotkey from config: {saved_hotkey}");

    tauri::Builder::default()

        .manage(StdMutex::new(VoxState {
            current_shortcut: saved_hotkey.clone(),
        }))
        .invoke_handler(tauri::generate_handler![
            start_recording,
            stop_recording,
            inject_text,
            update_hotkey,
            unregister_hotkey,
            set_run_on_startup,
            get_run_on_startup,
        ])
        .setup(move |app| {
            // --- Spawn STT Server ---
            if let Some(child) = spawn_stt_server() {
                *server_process.lock().unwrap() = Some(child);
            }

            // --- Tray ---
            let show = MenuItem::with_id(app, "show", "Show Vox", true, None::<&str>)?;
            let separator = PredefinedMenuItem::separator(app)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &separator, &quit])?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().cloned().expect("app icon missing"))
                .menu(&menu)
                .show_menu_on_left_click(false)
                .tooltip("Vox")
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

            // --- Keyboard Hook ---
            let rx = keyboard_hook::start_hook(&saved_hotkey);
            let handle = app.handle().clone();

            // --- Recording state machine (hold-to-talk + hands-free) ---
            //
            // States:
            //   Idle → HotkeyPressed → HoldRecording
            //   HoldRecording → HotkeyReleased (short) → WaitingForDoubleTap
            //   HoldRecording → HotkeyReleased (long) → stop & transcribe → Idle
            //   WaitingForDoubleTap → HotkeyPressed → HandsFree
            //   WaitingForDoubleTap → timeout 400ms → stop & transcribe → Idle
            //   HandsFree → HotkeyPressed → stop & transcribe → Idle

            #[derive(Debug, Clone)]
            enum RecMode {
                Idle,
                HoldRecording { press_time: Instant },
                WaitingForDoubleTap,
                HandsFree,
            }

            let mode = Arc::new(StdMutex::new(RecMode::Idle));
            let mode_for_thread = mode.clone();
            let processing = Arc::new(AtomicBool::new(false));
            let processing_for_thread = processing.clone();

            fn stop_and_transcribe(handle: AppHandle, processing: Arc<AtomicBool>) {
                processing.store(true, Ordering::Relaxed);
                tauri::async_runtime::spawn(async move {
                    let _ = handle.emit("vox-state", "processing");
                    match stt_bridge::stop_recording(true).await {
                        Ok(result) => {
                            if let Some(text) =
                                result.get("formatted").and_then(|v| v.as_str())
                            {
                                if !text.is_empty() {
                                    let text = text.to_string();
                                    tauri::async_runtime::spawn_blocking(move || {
                                        let _ = injector::inject_text(&text);
                                    });
                                    let _ = handle.emit("vox-result", &result);
                                }
                            }
                        }
                        Err(e) => {
                            let msg = e.to_string();
                            let user_msg = if msg.contains("timed out") || msg.contains("timeout") {
                                "Transcription timed out. Try a shorter recording or a faster model.".to_string()
                            } else {
                                msg.clone()
                            };
                            eprintln!("Transcription error: {msg}");
                            let _ = handle.emit("vox-error", &user_msg);
                        }
                    }
                    // Cleanup: always reset state + hide overlay
                    processing.store(false, Ordering::Relaxed);
                    let _ = handle.emit("vox-state", "idle");
                    let overlay = handle.get_webview_window("overlay");
                    tauri::async_runtime::spawn(async move {
                        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                        if let Some(w) = overlay {
                            let _ = w.hide();
                        }
                    });
                });
            }

            // Helper: start recording + show overlay
            fn begin_recording(handle: &AppHandle, state_name: &str) {
                let h = handle.clone();
                let sn = state_name.to_string();
                // Position + show pill INSTANTLY
                if let Some(ref w) = h.get_webview_window("overlay") {
                    // Position to bottom-center of primary monitor
                    if let Ok(Some(monitor)) = w.primary_monitor() {
                        let scale = monitor.scale_factor();
                        let size = monitor.size();
                        let sw = size.width as f64 / scale;
                        let sh = size.height as f64 / scale;
                        let x = (sw - 280.0) / 2.0;
                        let y = sh - 48.0 - 60.0;
                        let _ = w.set_position(tauri::LogicalPosition::new(x, y));
                    }
                    let _ = w.show();
                }
                let _ = h.emit("vox-state", sn.as_str());
                // Start recording in background (non-blocking)
                tauri::async_runtime::spawn(async move {
                    let _ = stt_bridge::start_recording().await;
                });
            }

            std::thread::spawn(move || {
                let mode = mode_for_thread;
                while let Ok(event) = rx.recv() {
                    let handle = handle.clone();
                    let mut m = mode.lock().unwrap();

                    match (&*m, &event) {
                        // ── Idle + Press → start recording, enter HoldRecording ──
                        (RecMode::Idle, keyboard_hook::HookEvent::HotkeyPressed) => {
                            if processing.load(Ordering::Relaxed) {
                                // Previous transcription still in flight — ignore
                            } else {
                                begin_recording(&handle, "recording");
                                *m = RecMode::HoldRecording { press_time: Instant::now() };
                            }
                        }

                        // ── HoldRecording + Release → check duration ──
                        (RecMode::HoldRecording { press_time }, keyboard_hook::HookEvent::HotkeyReleased) => {
                            let elapsed = press_time.elapsed();
                            if elapsed.as_millis() < 300 {
                                // Quick tap — wait for possible double-tap
                                *m = RecMode::WaitingForDoubleTap;
                                let mode_timer = mode.clone();
                                let handle_timer = handle.clone();
                                let proc_timer = processing.clone();
                                drop(m);
                                tauri::async_runtime::spawn(async move {
                                    tokio::time::sleep(std::time::Duration::from_millis(400)).await;
                                    let mut m = mode_timer.lock().unwrap();
                                    if matches!(&*m, RecMode::WaitingForDoubleTap) {
                                        *m = RecMode::Idle;
                                        drop(m);
                                        stop_and_transcribe(handle_timer, proc_timer);
                                    }
                                });
                            } else {
                                *m = RecMode::Idle;
                                let p = processing.clone();
                                drop(m);
                                stop_and_transcribe(handle, p);
                            }
                        }

                        // ── WaitingForDoubleTap + Press → enter hands-free! ──
                        (RecMode::WaitingForDoubleTap, keyboard_hook::HookEvent::HotkeyPressed) => {
                            *m = RecMode::HandsFree;
                            // Emit hands-free state (recording already running)
                            let _ = handle.emit("vox-state", "hands-free");
                        }

                        // ── HandsFree + Press → stop recording ──
                        (RecMode::HandsFree, keyboard_hook::HookEvent::HotkeyPressed) => {
                            *m = RecMode::Idle;
                            let p = processing.clone();
                            drop(m);
                            stop_and_transcribe(handle, p);
                        }

                        // ── Ignore releases in WaitingForDoubleTap and HandsFree ──
                        (RecMode::WaitingForDoubleTap, keyboard_hook::HookEvent::HotkeyReleased) => {}
                        (RecMode::HandsFree, keyboard_hook::HookEvent::HotkeyReleased) => {}

                        // ── Catch-all for unexpected transitions ──
                        _ => {
                            eprintln!("Unexpected state transition: {:?} + {:?}", *m, event);
                        }
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Vox")
        .run(move |_app, event| {
            // Prevent app from exiting when all windows are hidden (tray app)
            if let RunEvent::ExitRequested { api, .. } = &event {
                api.prevent_exit();
            }
            if let RunEvent::Exit = event {
                if let Ok(mut guard) = server_for_exit.lock() {
                    if let Some(ref mut child) = *guard {
                        eprintln!("Killing STT server (pid {})", child.id());
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        });
}

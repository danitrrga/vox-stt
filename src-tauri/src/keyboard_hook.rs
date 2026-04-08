//! Low-level keyboard hook for global hotkey detection on Windows.
//!
//! Uses SetWindowsHookEx(WH_KEYBOARD_LL) to intercept all keyboard events system-wide.
//! This bypasses RegisterHotKey() limitations, enabling combos like Ctrl+Win.

use std::collections::HashSet;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, OnceLock};
use windows_sys::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, GetMessageW, SetWindowsHookExW, UnhookWindowsHookEx, HHOOK, KBDLLHOOKSTRUCT,
    MSG, WH_KEYBOARD_LL, WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
};

/// Shared state accessible from the hook callback (must be global/static).
struct HookState {
    /// VK codes that make up the hotkey (e.g., [VK_CONTROL, VK_LWIN])
    target_keys: Mutex<Vec<u32>>,
    /// Currently held VK codes
    held_keys: Mutex<HashSet<u32>>,
    /// Whether the hotkey triggered a recording (waiting for release)
    recording: AtomicBool,
    /// Whether the hook should actively match keys
    enabled: AtomicBool,
    /// Channel to send events to the main thread
    sender: Mutex<Option<std::sync::mpsc::Sender<HookEvent>>>,
}

// Safety: HHOOK is only accessed from the hook thread
struct SendHHook(HHOOK);
unsafe impl Send for SendHHook {}

static HOOK_STATE: OnceLock<HookState> = OnceLock::new();
static HOOK_HANDLE: Mutex<Option<SendHHook>> = Mutex::new(None);

#[derive(Debug, Clone)]
pub enum HookEvent {
    HotkeyPressed,
    HotkeyReleased,
}

fn get_state() -> &'static HookState {
    HOOK_STATE.get_or_init(|| HookState {
        target_keys: Mutex::new(vec![]),
        held_keys: Mutex::new(HashSet::new()),
        recording: AtomicBool::new(false),
        enabled: AtomicBool::new(true),
        sender: Mutex::new(None),
    })
}

/// Parse a hotkey string like "Ctrl+Super" into a list of VK codes.
pub fn parse_hotkey_to_vk(hotkey: &str) -> Vec<u32> {
    hotkey
        .split('+')
        .filter_map(|part| {
            let vk = match part.trim().to_lowercase().as_str() {
                "ctrl" | "control" => 0x11,  // VK_CONTROL
                "shift" => 0x10,             // VK_SHIFT
                "alt" => 0x12,               // VK_MENU
                "super" | "win" | "meta" => 0x5B, // VK_LWIN
                "space" => 0x20,             // VK_SPACE
                "enter" | "return" => 0x0D,  // VK_RETURN
                "tab" => 0x09,               // VK_TAB
                "escape" | "esc" => 0x1B,    // VK_ESCAPE
                "backspace" => 0x08,         // VK_BACK
                "\\" | "backslash" => 0xDC,  // VK_OEM_5
                "`" | "backquote" | "dead" => 0xC0, // VK_OEM_3 (backtick/grave)
                ";" | "semicolon" => 0xBA,   // VK_OEM_1
                "," | "comma" => 0xBC,       // VK_OEM_COMMA
                "." | "period" => 0xBE,      // VK_OEM_PERIOD
                "/" | "slash" => 0xBF,        // VK_OEM_2
                "-" | "minus" => 0xBD,        // VK_OEM_MINUS
                "=" | "equal" => 0xBB,        // VK_OEM_PLUS
                "[" => 0xDB,                  // VK_OEM_4
                "]" => 0xDD,                  // VK_OEM_6
                "'" => 0xDE,                  // VK_OEM_7
                // Letters A-Z
                s if s.len() == 1 && s.as_bytes()[0].is_ascii_alphabetic() => {
                    (s.as_bytes()[0].to_ascii_uppercase()) as u32
                }
                // Digits 0-9
                s if s.len() == 1 && s.as_bytes()[0].is_ascii_digit() => {
                    s.as_bytes()[0] as u32
                }
                // F1-F12
                s if s.starts_with('f') => {
                    if let Ok(n) = s[1..].parse::<u32>() {
                        if (1..=12).contains(&n) {
                            0x6F + n // VK_F1=0x70, VK_F2=0x71, etc.
                        } else {
                            return None;
                        }
                    } else {
                        return None;
                    }
                }
                _ => return None,
            };
            Some(vk)
        })
        .collect()
}

/// Normalize VK codes: map left/right variants to generic codes for matching.
fn normalize_vk(vk: u32) -> u32 {
    match vk {
        0xA0 | 0xA1 => 0x10, // VK_LSHIFT/VK_RSHIFT → VK_SHIFT
        0xA2 | 0xA3 => 0x11, // VK_LCONTROL/VK_RCONTROL → VK_CONTROL
        0xA4 | 0xA5 => 0x12, // VK_LMENU/VK_RMENU → VK_MENU (Alt)
        0x5B | 0x5C => 0x5B, // VK_LWIN/VK_RWIN → VK_LWIN
        other => other,
    }
}

/// The low-level keyboard hook callback.
unsafe extern "system" fn hook_proc(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 {
        let kb = &*(lparam as *const KBDLLHOOKSTRUCT);
        let vk = normalize_vk(kb.vkCode);
        let state = get_state();

        if state.enabled.load(Ordering::Relaxed) {
            let is_down = wparam as u32 == WM_KEYDOWN || wparam as u32 == WM_SYSKEYDOWN;
            let is_up = wparam as u32 == WM_KEYUP || wparam as u32 == WM_SYSKEYUP;

            if is_down {
                if let Ok(mut held) = state.held_keys.lock() {
                    held.insert(vk);

                    // Check if all target keys are held
                    if !state.recording.load(Ordering::Relaxed) {
                        if let Ok(target) = state.target_keys.lock() {
                            if !target.is_empty() && target.iter().all(|k| held.contains(k)) {
                                state.recording.store(true, Ordering::Relaxed);
                                if let Ok(sender) = state.sender.lock() {
                                    if let Some(tx) = sender.as_ref() {
                                        let _ = tx.send(HookEvent::HotkeyPressed);
                                    }
                                }
                            }
                        }
                    }
                }
            } else if is_up {
                if state.recording.load(Ordering::Relaxed) {
                    // If a hotkey key was released while recording, stop
                    if let Ok(target) = state.target_keys.lock() {
                        if target.contains(&vk) {
                            state.recording.store(false, Ordering::Relaxed);
                            if let Ok(sender) = state.sender.lock() {
                                if let Some(tx) = sender.as_ref() {
                                    let _ = tx.send(HookEvent::HotkeyReleased);
                                }
                            }
                        }
                    }
                }

                if let Ok(mut held) = state.held_keys.lock() {
                    held.remove(&vk);
                }
            }
        }
    }

    unsafe { CallNextHookEx(std::ptr::null_mut(), code, wparam, lparam) }
}

/// Start the keyboard hook on a background thread. Returns a receiver for hook events.
pub fn start_hook(hotkey: &str) -> std::sync::mpsc::Receiver<HookEvent> {
    let (tx, rx) = std::sync::mpsc::channel();
    let vk_codes = parse_hotkey_to_vk(hotkey);

    let state = get_state();
    *state.target_keys.lock().unwrap() = vk_codes.clone();
    *state.sender.lock().unwrap() = Some(tx);
    state.enabled.store(true, Ordering::Relaxed);

    eprintln!(
        "Keyboard hook starting with VK codes: {:?} ({})",
        vk_codes, hotkey
    );

    std::thread::spawn(move || unsafe {
        let hook = SetWindowsHookExW(WH_KEYBOARD_LL, Some(hook_proc), std::ptr::null_mut(), 0);
        if hook.is_null() {
            eprintln!("Failed to install keyboard hook!");
            return;
        }

        *HOOK_HANDLE.lock().unwrap() = Some(SendHHook(hook));
        eprintln!("Keyboard hook installed.");

        // Message pump — required for the hook to work
        let mut msg: MSG = std::mem::zeroed();
        while GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) != 0 {}

        UnhookWindowsHookEx(hook);
        eprintln!("Keyboard hook removed.");
    });

    rx
}

/// Update the target hotkey at runtime.
pub fn update_target(hotkey: &str) {
    let vk_codes = parse_hotkey_to_vk(hotkey);
    let state = get_state();
    *state.target_keys.lock().unwrap() = vk_codes.clone();
    state.recording.store(false, Ordering::Relaxed);
    if let Ok(mut held) = state.held_keys.lock() {
        held.clear();
    }
    eprintln!("Keyboard hook updated to VK codes: {:?} ({})", vk_codes, hotkey);
}

/// Enable or disable the hook matching.
pub fn set_enabled(enabled: bool) {
    let state = get_state();
    state.enabled.store(enabled, Ordering::Relaxed);
    if !enabled {
        state.recording.store(false, Ordering::Relaxed);
        if let Ok(mut held) = state.held_keys.lock() {
            held.clear();
        }
    }
}

//! admincraft thin client — Rust side.
//!
//! The app is a web-first SPA; Tauri wraps it in a native window and adds
//! ONE thing the browser can't do securely: OS keychain storage for the AI
//! provider key (Windows Credential Manager / macOS Keychain / Secret
//! Service on Linux). All data stays with the Django backend.

use keyring::Entry;

const DEFAULT_SERVICE: &str = "admincraft";

#[tauri::command]
fn save_secret(service: String, key: String, value: String) -> Result<(), String> {
    Entry::new(&service, &key)
        .and_then(|e| e.set_password(&value))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn load_secret(service: String, key: String) -> Result<Option<String>, String> {
    match Entry::new(&service, &key).and_then(|e| e.get_password()) {
        Ok(v) => Ok(Some(v)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
fn delete_secret(service: String, key: String) -> Result<(), String> {
    match Entry::new(&service, &key).and_then(|e| e.delete_credential()) {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            save_secret,
            load_secret,
            delete_secret
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

// silence unused import warning for DEFAULT_SERVICE when tests don't use it
#[allow(dead_code)]
fn default_service() -> &'static str {
    DEFAULT_SERVICE
}

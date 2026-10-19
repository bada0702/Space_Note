mod sidecar;

use std::process::Child;
use std::sync::Mutex;

use serde::Serialize;
use tauri::{Manager, RunEvent};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendInfo {
    base_url: String,
    token: String,
}

struct Backend {
    info: BackendInfo,
    child: Mutex<Option<Child>>,
}

#[tauri::command]
fn backend_info(backend: tauri::State<'_, Backend>) -> BackendInfo {
    backend.info.clone()
}

/// 오류 대화상자를 띄우고, 닫으면 앱을 종료한다.
fn fail(app: &tauri::App, msg: String) {
    let handle = app.handle().clone();
    app.dialog()
        .message(msg)
        .title("SpaceNote")
        .kind(MessageDialogKind::Error)
        .show(move |_| handle.exit(1));
}

fn start_backend(app: &tauri::App) -> Result<Backend, String> {
    let path = app.path();
    let data_dir = path.data_dir().map_err(|e| e.to_string())?.join("SpaceNote");
    std::fs::create_dir_all(&data_dir).map_err(|e| format!("{}: {e}", data_dir.display()))?;
    let vault_dir = path.document_dir().map_err(|e| e.to_string())?.join("SpaceNote");

    if !sidecar::port_available(sidecar::PORT) {
        return Err(format!(
            "포트 {}이 이미 사용 중입니다. SpaceNote가 이미 실행 중인지 확인하세요.",
            sidecar::PORT
        ));
    }

    let exe_name = if cfg!(windows) { "spacenote-backend.exe" } else { "spacenote-backend" };
    let exe = path
        .resource_dir()
        .map_err(|e| e.to_string())?
        .join("spacenote-backend")
        .join(exe_name);
    let token = sidecar::new_token();
    let env = sidecar::backend_env(&token, &data_dir, &vault_dir);
    let child = sidecar::spawn(&exe, &env, &data_dir.join("backend.log"))
        .map_err(|e| format!("백엔드를 실행하지 못했습니다.\n{}\n{e}", exe.display()))?;

    Ok(Backend {
        info: BackendInfo { base_url: format!("http://127.0.0.1:{}", sidecar::PORT), token },
        child: Mutex::new(Some(child)),
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![backend_info])
        .setup(|app| {
            match start_backend(app) {
                Ok(backend) => {
                    app.manage(backend);
                }
                Err(msg) => fail(app, msg),
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            // 창을 닫으면 백엔드도 함께 종료해 다음 실행 때 포트 충돌을 막는다
            if let RunEvent::Exit = event {
                if let Some(backend) = app.try_state::<Backend>() {
                    if let Some(mut child) = backend.child.lock().unwrap().take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        });
}

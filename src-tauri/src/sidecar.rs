//! Windows 설치판: PyInstaller로 묶은 백엔드(spacenote-backend)를 실행·관리한다.

use std::fs::File;
use std::net::TcpListener;
use std::path::Path;
use std::process::{Child, Command, Stdio};

pub const PORT: u16 = 18001;

pub fn port_available(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

/// 실행마다 새로 만드는 API 토큰 (32바이트 → 64자 hex)
pub fn new_token() -> String {
    let mut buf = [0u8; 32];
    getrandom::getrandom(&mut buf).expect("OS 난수 생성 실패");
    buf.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn backend_env(token: &str, data_dir: &Path, vault_dir: &Path) -> Vec<(String, String)> {
    let s = |p: &Path| p.to_string_lossy().into_owned();
    vec![
        ("SPACENOTE_TOKEN".into(), token.into()),
        ("DB_PATH".into(), s(&data_dir.join("spacenote.db"))),
        ("VAULT_DIR".into(), s(vault_dir)),
        ("ALLOWED_ORIGIN".into(), "http://tauri.localhost".into()),
        // UTF-8 모드는 env(PYTHONUTF8)가 frozen 앱에서 무시되므로 spacenote-backend.spec 옵션으로 켠다
    ]
}

pub fn spawn(exe: &Path, env: &[(String, String)], log: &Path) -> std::io::Result<Child> {
    let out = File::create(log)?;
    let err = out.try_clone()?;
    let mut cmd = Command::new(exe);
    cmd.envs(env.iter().map(|(k, v)| (k, v)))
        // 파이프를 Child에 쥐고 있다가 앱이 죽으면 OS가 닫음 → 백엔드가 EOF를 보고 종료 (desktop_entry.watch_parent)
        .stdin(Stdio::piped())
        .stdout(out)
        .stderr(err);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd.spawn()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_is_64_hex_and_unique() {
        let (a, b) = (new_token(), new_token());
        assert_eq!(a.len(), 64);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }

    #[test]
    fn env_contains_required_keys() {
        let env = backend_env("tok", Path::new("D"), Path::new("V"));
        let get = |k: &str| env.iter().find(|(x, _)| x == k).map(|(_, v)| v.clone());
        assert_eq!(get("SPACENOTE_TOKEN").as_deref(), Some("tok"));
        assert_eq!(
            get("DB_PATH"),
            Some(Path::new("D").join("spacenote.db").to_string_lossy().into_owned())
        );
        assert_eq!(get("VAULT_DIR").as_deref(), Some("V"));
        assert_eq!(get("ALLOWED_ORIGIN").as_deref(), Some("http://tauri.localhost"));
    }

    #[cfg(unix)]
    #[test]
    fn spawn_passes_env_and_writes_log() {
        let log = std::env::temp_dir().join(format!("sidecar-test-{}.log", std::process::id()));
        let env = [("SPACENOTE_TOKEN".to_string(), "tok123".to_string())];
        let status = spawn(Path::new("/usr/bin/env"), &env, &log).unwrap().wait().unwrap();
        assert!(status.success());
        let out = std::fs::read_to_string(&log).unwrap();
        let _ = std::fs::remove_file(&log);
        assert!(out.contains("SPACENOTE_TOKEN=tok123"));
    }

    #[cfg(unix)]
    #[test]
    fn spawn_keeps_stdin_pipe_for_parent_watch() {
        let log = std::env::temp_dir().join(format!("sidecar-stdin-{}.log", std::process::id()));
        let mut child = spawn(Path::new("/bin/cat"), &[], &log).unwrap();
        assert!(child.stdin.is_some());
        drop(child.stdin.take()); // 부모가 파이프를 닫으면 자식(cat)은 EOF로 종료해야 한다
        assert!(child.wait().unwrap().success());
        let _ = std::fs::remove_file(&log);
    }

    #[test]
    fn port_in_use_is_reported() {
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        assert!(!port_available(l.local_addr().unwrap().port()));
    }
}

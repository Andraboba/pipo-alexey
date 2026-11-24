//! Python-сервер Пипо Алексея: запуск, ожидание готовности, запросы к API, мягкий выход.
//!
//! Сервер слушает только 127.0.0.1 и пускает к /api лишь с токеном этого запуска —
//! токен придумывает оболочка и передаёт серверу через PIPO_TOKEN.

use std::net::TcpListener;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde_json::Value;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
/// Тот же порт, что раньше: у страницы постоянный адрес, и её localStorage (масштаб, пройденный гайд) не теряется.
const PREFERRED_PORT: u16 = 47800;

#[cfg(not(debug_assertions))]
static SERVER_EXE: &[u8] = include_bytes!(env!("PIPO_SERVER_EXE"));

pub struct Backend {
    pub base: String,
    token: String,
    pub data_dir: PathBuf,
    child: Mutex<Child>,
    /// выходим по команде из трея — смерть сервера не ошибка
    pub quitting: AtomicBool,
}

impl Backend {
    pub fn start() -> Result<Self, String> {
        let (mut cmd, data_dir) = server_command()?;
        std::fs::create_dir_all(&data_dir).map_err(|e| format!("не удалось создать {}: {e}", data_dir.display()))?;
        let token = random_token();
        let port = free_port();
        cmd.args(["--server-only", "--no-admin", "--port", &port.to_string()])
            .args(["--parent-pid", &std::process::id().to_string()])
            .env("PIPO_TOKEN", &token)
            .env("PIPO_DATA_DIR", &data_dir)
            .creation_flags(CREATE_NO_WINDOW);
        let child = cmd.spawn().map_err(|e| format!("не удалось запустить сервер: {e}"))?;
        Ok(Self {
            base: format!("http://127.0.0.1:{port}"),
            token,
            data_dir,
            child: Mutex::new(child),
            quitting: AtomicBool::new(false),
        })
    }

    pub fn log_path(&self) -> PathBuf {
        self.data_dir.join("pipo.log")
    }

    /// Код выхода, если сервер уже завершился.
    pub fn exited(&self) -> Option<i32> {
        match self.child.lock().unwrap().try_wait() {
            Ok(Some(st)) => Some(st.code().unwrap_or(-1)),
            _ => None,
        }
    }

    pub fn wait_ready(&self, timeout: Duration) -> Result<(), String> {
        let end = Instant::now() + timeout;
        while Instant::now() < end {
            if let Some(code) = self.exited() {
                return Err(format!("Сервер завершился при запуске (код {code})"));
            }
            if self.get("/api/status").is_ok() {
                return Ok(());
            }
            std::thread::sleep(Duration::from_millis(150));
        }
        Err("Сервер не ответил за 30 секунд".into())
    }

    pub fn get(&self, path: &str) -> Result<Value, String> {
        self.call(ureq::get(&format!("{}{path}", self.base)).timeout(Duration::from_secs(10)))
    }

    pub fn post(&self, path: &str) -> Result<Value, String> {
        let req = ureq::post(&format!("{}{path}", self.base)).timeout(Duration::from_secs(60));
        let req = req.set("X-Pipo-Token", &self.token);
        match req.send_json(serde_json::json!({})) {
            Ok(r) => r.into_json().map_err(|e| e.to_string()),
            Err(e) => Err(error_text(e)),
        }
    }

    fn call(&self, req: ureq::Request) -> Result<Value, String> {
        match req.set("X-Pipo-Token", &self.token).call() {
            Ok(r) => r.into_json().map_err(|e| e.to_string()),
            Err(e) => Err(error_text(e)),
        }
    }

    /// Выход: сервер останавливает фоновую задачу (она возвращает запрет как было) и завершается сам.
    /// Не уложился — добиваем; незаконченный подбор вернёт запрет при следующем запуске.
    pub fn shutdown(&self) {
        self.quitting.store(true, Ordering::SeqCst);
        if self.exited().is_none() {
            let _ = self.post("/api/app/quit");
            let end = Instant::now() + Duration::from_secs(40);
            while self.exited().is_none() && Instant::now() < end {
                std::thread::sleep(Duration::from_millis(200));
            }
        }
        let mut child = self.child.lock().unwrap();
        if child.try_wait().ok().flatten().is_none() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn error_text(e: ureq::Error) -> String {
    match e {
        ureq::Error::Status(code, resp) => resp
            .into_json::<Value>()
            .ok()
            .and_then(|v| v.get("detail").and_then(|d| d.as_str().map(str::to_owned)))
            .unwrap_or_else(|| format!("HTTP {code}")),
        ureq::Error::Transport(t) => format!("нет связи с сервером: {t}"),
    }
}

fn exe_dir() -> Result<PathBuf, String> {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .ok_or_else(|| "не удалось определить папку программы".to_string())
}

/// Отладка (`cargo run`): сервер из исходников — python из .venv репозитория, данные в data репозитория.
#[cfg(debug_assertions)]
fn server_command() -> Result<(Command, PathBuf), String> {
    let _ = exe_dir;
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let python = repo.join(".venv").join("Scripts").join("python.exe");
    let mut cmd = Command::new(&python);
    cmd.arg(repo.join("main.py")).current_dir(&repo);
    Ok((cmd, repo.join("data")))
}

/// Релиз: вшитый pipo-server.exe распаковывается в data\runtime рядом с PipoAlexey.exe
/// (переписывается, только если изменился). Данные — в data рядом с exe, как раньше.
#[cfg(not(debug_assertions))]
fn server_command() -> Result<(Command, PathBuf), String> {
    let data = exe_dir()?.join("data");
    let dir = data.join("runtime");
    let exe = dir.join("pipo-server.exe");
    let same = std::fs::read(&exe).map(|b| b == SERVER_EXE).unwrap_or(false);
    if !same {
        std::fs::create_dir_all(&dir).map_err(|e| format!("не удалось создать {}: {e}", dir.display()))?;
        let tmp = dir.join("pipo-server.exe.new");
        std::fs::write(&tmp, SERVER_EXE).map_err(|e| format!("не удалось распаковать сервер: {e}"))?;
        std::fs::rename(&tmp, &exe).map_err(|e| {
            format!("не удалось обновить {} — возможно, ещё работает прошлый запуск: {e}", exe.display())
        })?;
    }
    let mut cmd = Command::new(&exe);
    cmd.current_dir(&dir);
    Ok((cmd, data))
}

fn free_port() -> u16 {
    for port in PREFERRED_PORT..PREFERRED_PORT + 20 {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return port;
        }
    }
    TcpListener::bind(("127.0.0.1", 0))
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(PREFERRED_PORT)
}

fn random_token() -> String {
    let mut buf = [0u8; 24];
    getrandom::fill(&mut buf).expect("системный генератор случайных чисел недоступен");
    buf.iter().map(|b| format!("{b:02x}")).collect()
}

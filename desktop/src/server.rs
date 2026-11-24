//! Python-сервер Пипо Алексея: запуск, ожидание готовности, запросы к API, мягкий выход.
//!
//! Сервер слушает только 127.0.0.1 и пускает к /api лишь с токеном этого запуска —
//! токен придумывает оболочка и передаёт серверу через PIPO_TOKEN.

use std::net::TcpListener;
use std::os::windows::io::AsRawHandle;
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
/// Код выхода сервера «порт, который дала оболочка, уже занят» — тогда пробуем другой (main.py).
const EXIT_PORT_BUSY: i32 = 3;

#[cfg(not(debug_assertions))]
static SERVER_EXE: &[u8] = include_bytes!(env!("PIPO_SERVER_EXE"));

pub struct Backend {
    token: String,
    pub data_dir: PathBuf,
    /// адрес и процесс меняются, если сервер пришлось перезапустить на другом порту
    base: Mutex<String>,
    child: Mutex<Child>,
    /// все процессы сервера: pipo-server.exe из PyInstaller — это загрузчик, Python работает в его дочернем процессе
    job: Job,
    /// выходим по команде из трея — смерть сервера не ошибка
    pub quitting: AtomicBool,
    /// сервер умер или не поднялся: окно больше не прячется в трей, крестик закрывает программу
    pub dead: AtomicBool,
}

impl Backend {
    pub fn start() -> Result<Self, String> {
        let data_dir = data_dir();
        std::fs::create_dir_all(&data_dir).map_err(|e| format!("не удалось создать {}: {e}", data_dir.display()))?;
        let token = random_token();
        let (base, child, job) = spawn(&token, &data_dir)?;
        Ok(Self {
            token,
            data_dir,
            base: Mutex::new(base),
            child: Mutex::new(child),
            job,
            quitting: AtomicBool::new(false),
            dead: AtomicBool::new(false),
        })
    }

    pub fn base(&self) -> String {
        self.base.lock().unwrap().clone()
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

    /// Ждать, пока сервер ответит. Порт успели занять между проверкой и запуском — перезапуск на другом.
    pub fn wait_ready(&self, timeout: Duration) -> Result<(), String> {
        let end = Instant::now() + timeout;
        let mut retries = 0;
        while Instant::now() < end {
            // «Выход» нажали, пока сервер поднимался: не ждём и не перезапускаем его
            if self.quitting.load(Ordering::SeqCst) {
                return Err("выход".into());
            }
            match self.exited() {
                Some(EXIT_PORT_BUSY) if retries < 5 => {
                    retries += 1;
                    let (base, child, job) = spawn(&self.token, &self.data_dir)?;
                    *self.base.lock().unwrap() = base;
                    *self.child.lock().unwrap() = child;
                    self.job.adopt(job);
                    continue;
                }
                Some(code) => return Err(format!("Сервер завершился при запуске (код {code})")),
                None => {}
            }
            if self.get("/api/status").is_ok() {
                return Ok(());
            }
            std::thread::sleep(Duration::from_millis(150));
        }
        Err("Сервер не ответил за 30 секунд".into())
    }

    pub fn get(&self, path: &str) -> Result<Value, String> {
        self.call(ureq::get(&format!("{}{path}", self.base())).timeout(Duration::from_secs(10)))
    }

    pub fn post(&self, path: &str) -> Result<Value, String> {
        let req = ureq::post(&format!("{}{path}", self.base())).timeout(Duration::from_secs(60));
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
    /// Не уложился — завершаем все его процессы; незаконченный подбор вернёт запрет при следующем запуске.
    pub fn shutdown(&self) {
        self.quitting.store(true, Ordering::SeqCst);
        // Сервер мог ещё не начать слушать порт (выход в первые секунды) — просим, пока не услышит.
        // Ответил — дальше он завершится сам, нам остаётся ждать.
        let end = Instant::now() + Duration::from_secs(40);
        let mut asked = false;
        while self.exited().is_none() && Instant::now() < end {
            if !asked {
                asked = self.post("/api/app/quit").is_ok();
            }
            std::thread::sleep(Duration::from_millis(if asked { 200 } else { 300 }));
        }
        // загрузчик PyInstaller мог выйти, а Python под ним — нет: добиваем всё задание целиком
        self.job.terminate();
        let mut child = self.child.lock().unwrap();
        if child.try_wait().ok().flatten().is_none() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Запустить сервер на свободном порту и сразу поместить в задание вместе с будущими дочерними процессами.
fn spawn(token: &str, data_dir: &Path) -> Result<(String, Child, Job), String> {
    let mut cmd = server_command()?;
    let port = free_port();
    cmd.args(["--server-only", "--no-admin", "--port", &port.to_string()])
        .args(["--parent-pid", &std::process::id().to_string()])
        .env("PIPO_TOKEN", token)
        .env("PIPO_DATA_DIR", data_dir);
    let (child, job) = spawn_in_job(&mut cmd).map_err(|e| format!("не удалось запустить сервер: {e}"))?;
    Ok((format!("http://127.0.0.1:{port}"), child, job))
}

/// Запустить процесс приостановленным, поместить в задание и только потом возобновить:
/// иначе загрузчик PyInstaller (или лаунчер python.exe из .venv) мог бы успеть породить Python вне задания.
fn spawn_in_job(cmd: &mut Command) -> std::io::Result<(Child, Job)> {
    const CREATE_SUSPENDED: u32 = 0x0000_0004;
    let mut child = cmd.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED).spawn()?;
    let job = Job::new();
    job.assign(&child);
    if let Err(e) = resume_process(child.id()) {
        let _ = child.kill();
        return Err(e);
    }
    Ok((child, job))
}

/// Возобновить потоки приостановленного процесса (у только что созданного — один, главный).
fn resume_process(pid: u32) -> std::io::Result<()> {
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::*;
    use windows_sys::Win32::System::Threading::{OpenThread, ResumeThread, THREAD_SUSPEND_RESUME};
    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        if snap == INVALID_HANDLE_VALUE {
            return Err(std::io::Error::last_os_error());
        }
        let mut entry: THREADENTRY32 = std::mem::zeroed();
        entry.dwSize = std::mem::size_of::<THREADENTRY32>() as u32;
        let mut resumed = 0;
        let mut ok = Thread32First(snap, &mut entry) != 0;
        while ok {
            if entry.th32OwnerProcessID == pid {
                let th = OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID);
                if !th.is_null() {
                    if ResumeThread(th) != u32::MAX {
                        resumed += 1;
                    }
                    CloseHandle(th);
                }
            }
            ok = Thread32Next(snap, &mut entry) != 0;
        }
        CloseHandle(snap);
        if resumed == 0 {
            return Err(std::io::Error::other("не удалось возобновить процесс сервера"));
        }
    }
    Ok(())
}

/// Объект задания Windows: TerminateJobObject завершает все процессы сервера разом.
/// Без KILL_ON_JOB_CLOSE — если оболочка упадёт, сервер сам заметит это и выйдет мягко (--parent-pid).
/// BREAKAWAY_OK — программы, которые сервер запускает для пользователя (прокси Telegram), могут выйти из задания.
pub struct Job(Mutex<isize>);

impl Job {
    pub fn new() -> Self {
        use windows_sys::Win32::System::JobObjects::*;
        unsafe {
            let h = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if !h.is_null() {
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_BREAKAWAY_OK;
                SetInformationJobObject(
                    h,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as *const _,
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
            }
            Self(Mutex::new(h as isize))
        }
    }

    pub fn assign(&self, child: &Child) {
        let h = *self.0.lock().unwrap();
        if h != 0 {
            unsafe {
                windows_sys::Win32::System::JobObjects::AssignProcessToJobObject(h as _, child.as_raw_handle() as _);
            }
        }
    }

    /// Взять задание нового запуска сервера вместо старого.
    fn adopt(&self, other: Job) {
        let mut mine = self.0.lock().unwrap();
        let mut theirs = other.0.lock().unwrap();
        std::mem::swap(&mut *mine, &mut *theirs);
        // other закроет старое задание в Drop
    }

    pub fn terminate(&self) {
        let h = *self.0.lock().unwrap();
        if h != 0 {
            unsafe {
                windows_sys::Win32::System::JobObjects::TerminateJobObject(h as _, 1);
            }
        }
    }
}

impl Drop for Job {
    fn drop(&mut self) {
        let h = *self.0.lock().unwrap();
        if h != 0 {
            unsafe {
                windows_sys::Win32::Foundation::CloseHandle(h as _);
            }
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

/// Папка данных: в отладке — data репозитория, в релизе — data рядом с PipoAlexey.exe (как раньше).
#[cfg(debug_assertions)]
pub fn data_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("data")
}

#[cfg(not(debug_assertions))]
pub fn data_dir() -> PathBuf {
    exe_dir().map(|d| d.join("data")).unwrap_or_else(|_| PathBuf::from("data"))
}

/// Тема из «Настроек» (копия в data\settings.json) — для заглушки загрузки, пока сервера ещё нет.
pub fn saved_theme() -> &'static str {
    let theme = std::fs::read_to_string(data_dir().join("settings.json"))
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.get("ui_theme").and_then(Value::as_str).map(str::to_owned));
    match theme.as_deref() {
        Some("light") => "light",
        Some("dark") => "dark",
        _ => "system",
    }
}

/// Отладка (`cargo run`): сервер из исходников — python из .venv репозитория.
#[cfg(debug_assertions)]
fn server_command() -> Result<Command, String> {
    let _ = exe_dir;
    let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let python = repo.join(".venv").join("Scripts").join("python.exe");
    let mut cmd = Command::new(&python);
    cmd.arg(repo.join("main.py")).current_dir(&repo);
    Ok(cmd)
}

/// Релиз: вшитый pipo-server.exe распаковывается в data\runtime рядом с PipoAlexey.exe
/// (переписывается, только если изменился).
#[cfg(not(debug_assertions))]
fn server_command() -> Result<Command, String> {
    let data = data_dir();
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
    Ok(cmd)
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

#[cfg(test)]
mod tests {
    use super::*;

    /// Запуск приостановленным + задание: процесс работает после возобновления,
    /// а terminate завершает и внуков — так устроен pipo-server.exe (загрузчик → Python).
    #[test]
    fn job_terminates_grandchildren() {
        let marker = format!("pipo-job-test-{}", std::process::id());
        // cmd → ping: ping — «внук», как Python под загрузчиком PyInstaller
        let (child, job) = spawn_in_job(
            Command::new("cmd").args(["/c", &format!("title {marker} & ping -n 30 127.0.0.1 >nul")]),
        )
        .unwrap();
        std::thread::sleep(Duration::from_millis(500));
        let pings = || {
            let out = Command::new("powershell")
                .args(["-NoProfile", "-Command", &format!(
                    "@(Get-CimInstance Win32_Process | Where-Object {{ $_.Name -eq 'PING.EXE' -and $_.ParentProcessId -eq {} }}).Count",
                    child.id()
                )])
                .output()
                .unwrap();
            String::from_utf8_lossy(&out.stdout).trim().parse::<u32>().unwrap_or(0)
        };
        assert_eq!(pings(), 1, "ping должен работать внутри задания");
        job.terminate();
        std::thread::sleep(Duration::from_millis(500));
        assert_eq!(pings(), 0, "после terminate внуков не остаётся");
    }
}

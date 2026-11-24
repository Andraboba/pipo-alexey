//! Пипо Алексей — окно приложения (Tauri, движок WebView2) и значок в трее.
//!
//! Вся логика — в Python-сервере (main.py, app/): оболочка запускает его, открывает его страницу
//! в своём окне и держит значок в трее. Крестик прячет окно в трей, «Выход» в трее закрывает всё.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod server;
mod tray;

use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::Duration;

use tauri::webview::Color;
use tauri::{AppHandle, Manager, RunEvent, Theme, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};

use server::Backend;

// фон окна до первой отрисовки страницы — как --bg в tokens.css, чтобы не мигало
const DARK_BG: Color = Color(0x14, 0x14, 0x15, 0xff);
const LIGHT_BG: Color = Color(0xfa, 0xfa, 0xfa, 0xff);

fn main() {
    tauri::Builder::default()
        // второй запуск не плодит окна и серверы, а показывает уже открытое
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // заглушка загрузки — в теме из «Настроек»; «как в системе» она определит сама
            let theme = server::saved_theme();
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .initialization_script(format!("window.__PIPO_THEME = {theme:?};"))
                .title("Пипо Алексей")
                .inner_size(1360.0, 900.0)
                .min_inner_size(960.0, 640.0)
                .background_color(if theme == "light" { LIGHT_BG } else { DARK_BG })
                .center()
                .build()?;
            if theme == "system" && window.theme().ok() == Some(Theme::Light) {
                let _ = window.set_background_color(Some(LIGHT_BG));
            }
            // Первый показ окна Windows берёт из STARTUPINFO запустившего процесса: из IDE, планировщика
            // или ярлыка «свёрнуто» окно может остаться скрытым. Второй показ выполняется как есть.
            let _ = window.show();
            let _ = window.unminimize();
            let _ = window.set_focus();

            let backend = match Backend::start() {
                Ok(b) => Arc::new(b),
                Err(e) => {
                    show_error(&window, &e, "data\\pipo.log");
                    return Ok(());
                }
            };
            app.manage(backend.clone());
            tray::create(app.handle(), backend.clone())?;

            std::thread::spawn(move || {
                match backend.wait_ready(Duration::from_secs(30)) {
                    // shell=tauri — страница знает, что крестик прячет её в трей
                    Ok(()) => match Url::parse(&format!("{}/?shell=tauri", backend.base())) {
                        Ok(url) => {
                            let _ = window.navigate(url);
                        }
                        Err(e) => show_error(&window, &e.to_string(), &backend.log_path().display().to_string()),
                    },
                    Err(_) if backend.quitting.load(Ordering::SeqCst) => return, // «Выход» во время запуска
                    Err(e) => {
                        backend.dead.store(true, Ordering::SeqCst);
                        show_error(&window, &e, &backend.log_path().display().to_string());
                        return;
                    }
                }
                // сервер упал посреди работы — сказать об этом, а не показывать вечное «нет связи»
                loop {
                    std::thread::sleep(Duration::from_secs(2));
                    if backend.quitting.load(Ordering::SeqCst) {
                        return;
                    }
                    if let Some(code) = backend.exited() {
                        backend.dead.store(true, Ordering::SeqCst);
                        // встроенная заглушка: на Windows Tauri отдаёт свои файлы с http://tauri.localhost
                        if let Ok(url) = Url::parse("http://tauri.localhost/index.html") {
                            let _ = window.navigate(url);
                        }
                        std::thread::sleep(Duration::from_millis(800));
                        show_error(
                            &window,
                            &format!("Сервер приложения остановился (код {code}) — закройте окно и запустите Пипо Алексея заново"),
                            &backend.log_path().display().to_string(),
                        );
                        return;
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            // крестик — в трей; служба запрета и прокси продолжают работать.
            // Сервер умер — прятать нечего: крестик закрывает программу, следующий запуск начнёт заново
            if let WindowEvent::CloseRequested { api, .. } = event {
                if server_alive(window.app_handle()) {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("не удалось запустить окно Пипо Алексея")
        .run(|app, event| {
            if let RunEvent::ExitRequested { code: None, api, .. } = event {
                // окно спрятано, но приложение живёт в трее
                if server_alive(app) {
                    api.prevent_exit();
                }
            }
        });
}

/// Сервер запущен и не умер — значит, окно прячется в трей, а не закрывает программу.
fn server_alive(app: &AppHandle) -> bool {
    app.try_state::<Arc<Backend>>().is_some_and(|b| !b.dead.load(Ordering::SeqCst))
}

pub fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

/// «Выход» из трея: спрятать всё сразу, а сервер пусть спокойно вернёт запрет, если шёл подбор.
pub fn quit(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.hide();
    }
    tray::hide(app);
    let app = app.clone();
    std::thread::spawn(move || {
        if let Some(b) = app.try_state::<Arc<Backend>>() {
            b.shutdown();
        }
        app.exit(0);
    });
}

/// Ошибка на заглушке загрузки. Страница могла ещё не загрузиться — ждём её showError.
fn show_error(window: &WebviewWindow, text: &str, log: &str) {
    let js = format!(
        "(function f(n){{ if (window.showError) showError({}, {}); else if (n) setTimeout(() => f(n - 1), 100); }})(50)",
        serde_json::to_string(text).unwrap_or_default(),
        serde_json::to_string(log).unwrap_or_default()
    );
    let window = window.clone();
    std::thread::spawn(move || {
        // eval до создания документа теряется — даём окну открыться
        std::thread::sleep(Duration::from_millis(400));
        let _ = window.eval(&js);
    });
}

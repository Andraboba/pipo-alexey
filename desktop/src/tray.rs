//! Значок в трее: включить/выключить запрет и прокси Telegram, не открывая окно.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::Value;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Wry};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};

use crate::server::Backend;

/// Что сейчас можно сделать с запретом и прокси — из /api/status.
#[derive(Clone, Default, PartialEq)]
struct State {
    zapret_on: bool,
    /// служба установлена (или winws запущен из .bat) и есть права администратора
    zapret_can: bool,
    zapret_note: Option<&'static str>,
    tg_on: bool,
    tg_can: bool,
    tg_note: Option<&'static str>,
    online: bool,
}

impl State {
    fn from(s: &Value) -> Self {
        let z = &s["zapret"];
        let tg = &s["tg"];
        let admin = s["admin"].as_bool().unwrap_or(false);
        let zapret_on = z["service"].as_str() == Some("running") || z["winws_running"].as_bool().unwrap_or(false);
        let installed = !z["service"].is_null();
        let zapret_note = if !admin {
            Some("нужны права администратора")
        } else if !z["exists"].as_bool().unwrap_or(false) {
            Some("не найден")
        } else if !installed && !zapret_on {
            Some("служба не установлена")
        } else {
            None
        };
        let tg_installed = tg["installed"].as_bool().unwrap_or(false);
        Self {
            zapret_on,
            zapret_can: zapret_note.is_none(),
            zapret_note,
            tg_on: tg["running"].as_bool().unwrap_or(false),
            tg_can: tg_installed,
            tg_note: (!tg_installed).then_some("не установлен"),
            online: true,
        }
    }
}

/// Блокировки state и busy держим только на чтение и запись, но НЕ во время вызовов меню и значка:
/// из фонового потока Tauri выполняет их в главном потоке и ждёт его, а главный поток (клик по пункту)
/// сам берёт state — держать её во время перерисовки значит повесить программу.
/// render_lock берут только фоновые потоки: две перерисовки не перемешиваются, главный поток его не ждёт.
struct Items {
    zapret: CheckMenuItem<Wry>,
    tg: CheckMenuItem<Wry>,
    icon: TrayIcon<Wry>,
    state: Mutex<State>,
    busy: Mutex<bool>,
    render_lock: Mutex<()>,
}

pub fn create(app: &AppHandle, backend: Arc<Backend>) -> tauri::Result<()> {
    let zapret = CheckMenuItem::with_id(app, "zapret", "Запрет", false, false, None::<&str>)?;
    let tg = CheckMenuItem::with_id(app, "tg", "Прокси Telegram", false, false, None::<&str>)?;
    let open = MenuItem::with_id(app, "open", "Открыть Пипо Алексея", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Выход", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[&zapret, &tg, &PredefinedMenuItem::separator(app)?, &open, &quit],
    )?;

    let mut builder = TrayIconBuilder::with_id("main")
        .tooltip("Пипо Алексей")
        .menu(&menu)
        .show_menu_on_left_click(false);
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    let icon = builder
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                crate::show_main(tray.app_handle());
            }
        })
        .build(app)?;

    let items = Arc::new(Items {
        zapret,
        tg,
        icon,
        state: Mutex::new(State::default()),
        busy: Mutex::new(false),
        render_lock: Mutex::new(()),
    });
    render(&items, &State::default(), true);

    {
        let (items, backend) = (items.clone(), backend.clone());
        app.on_menu_event(move |app, event| match event.id().as_ref() {
            "zapret" => toggle(app, &items, &backend, Kind::Zapret),
            "tg" => toggle(app, &items, &backend, Kind::Tg),
            "open" => crate::show_main(app),
            "quit" => crate::quit(app),
            _ => {}
        });
    }

    // опрос состояния: служба запрета живёт сама по себе и может смениться из окна или извне
    std::thread::spawn(move || loop {
        if !backend.quitting.load(std::sync::atomic::Ordering::SeqCst) {
            refresh(&items, &backend, false);
        }
        std::thread::sleep(Duration::from_secs(3));
    });
    Ok(())
}

#[derive(Clone, Copy)]
enum Kind {
    Zapret,
    Tg,
}

/// Перерисовывать ли меню. Во время переключения пункт показывает «…» — не перетираем;
/// после переключения (force) — обязательно, даже если состояние на вид то же.
fn needs_render(cur: &State, next: &State, busy: bool, force: bool) -> bool {
    !busy && (force || cur != next)
}

fn refresh(items: &Items, backend: &Backend, force: bool) {
    let next = match backend.get("/api/status") {
        Ok(s) => State::from(&s),
        Err(_) => State::default(),
    };
    let _render = items.render_lock.lock().unwrap();
    {
        let busy = *items.busy.lock().unwrap();
        let mut cur = items.state.lock().unwrap();
        if !needs_render(&cur, &next, busy, force) {
            return;
        }
        *cur = next.clone();
    } // state и busy отпущены до вызовов меню
    render(items, &next, false);
}

fn render(items: &Items, s: &State, force: bool) {
    let label = |name: &str, on: bool, note: Option<&str>| match note {
        Some(n) => format!("{name} — {n}"),
        None => format!("{name} — {}", if on { "включён" } else { "выключен" }),
    };
    let _ = items.zapret.set_text(label("Запрет", s.zapret_on, s.zapret_note));
    let _ = items.zapret.set_checked(s.zapret_on);
    let _ = items.zapret.set_enabled(s.online && s.zapret_can);
    let _ = items.tg.set_text(label("Прокси Telegram", s.tg_on, s.tg_note));
    let _ = items.tg.set_checked(s.tg_on);
    let _ = items.tg.set_enabled(s.online && s.tg_can);
    let tip = if s.online || force {
        format!(
            "Пипо Алексей\nЗапрет: {}\nПрокси Telegram: {}",
            if s.zapret_on { "вкл" } else { "выкл" },
            if s.tg_on { "вкл" } else { "выкл" }
        )
    } else {
        "Пипо Алексей — нет связи с сервером".into()
    };
    let _ = items.icon.set_tooltip(Some(tip));
}

fn toggle(app: &AppHandle, items: &Arc<Items>, backend: &Arc<Backend>, kind: Kind) {
    let mut busy = items.busy.lock().unwrap();
    if *busy {
        return;
    }
    *busy = true;
    drop(busy);

    let cur = items.state.lock().unwrap().clone();
    let (item, on, path, name) = match kind {
        Kind::Zapret => (&items.zapret, cur.zapret_on, if cur.zapret_on { "/api/zapret/stop" } else { "/api/zapret/start" }, "Запрет"),
        Kind::Tg => (&items.tg, cur.tg_on, if cur.tg_on { "/api/tg/stop" } else { "/api/tg/start" }, "Прокси Telegram"),
    };
    // Windows сам переставил галочку — пока не узнаем результат, показываем прежнее и «…»
    let _ = item.set_checked(on);
    let _ = item.set_enabled(false);
    let _ = item.set_text(format!("{name} — {}…", if on { "выключаю" } else { "включаю" }));

    let (app, items, backend) = (app.clone(), items.clone(), backend.clone());
    std::thread::spawn(move || {
        let res = backend.post(path);
        // прокси Telegram открывает порт не сразу
        if matches!(kind, Kind::Tg) && res.is_ok() {
            std::thread::sleep(Duration::from_millis(1500));
        }
        *items.busy.lock().unwrap() = false;
        refresh(&items, &backend, true); // снять «…» в любом случае, даже если сервер не ответил
        if let Err(e) = res {
            app.dialog()
                .message(e)
                .title(format!("{name}: не получилось"))
                .kind(MessageDialogKind::Error)
                .show(|_| {});
        }
    });
}

pub fn hide(app: &AppHandle) {
    if let Some(tray) = app.tray_by_id("main") {
        let _ = tray.set_visible(false);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn render_decision() {
        let off = State::default();
        let on = State { zapret_on: true, online: true, ..State::default() };
        assert!(needs_render(&off, &on, false, false), "состояние сменилось");
        assert!(!needs_render(&on, &on, false, false), "ничего не сменилось");
        assert!(!needs_render(&off, &on, true, false), "идёт переключение — «…» не трогаем");
        // сервер не ответил после переключения: и было, и стало «по умолчанию», но «…» снять нужно
        assert!(needs_render(&off, &off, false, true));
    }
}

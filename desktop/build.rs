use std::path::PathBuf;

fn main() {
    let release = std::env::var("PROFILE").as_deref() == Ok("release");

    // Релиз просит права администратора (как раньше PyInstaller-сборка): сервер наследует их и управляет службой.
    // Отладочная сборка — без UAC, чтобы `cargo run` запускался из обычной консоли (сервер будет «только просмотр»).
    let level = if release { "requireAdministrator" } else { "asInvoker" };
    // app.manifest — только ASCII: кириллица ломает его при компиляции ресурсов (Windows не запустит exe).
    // Common Controls v6 в нём нужен самому Tauri (диалоги, меню трея).
    let manifest = include_str!("app.manifest").replace("{LEVEL}", level);
    let attrs = tauri_build::Attributes::new()
        .windows_attributes(tauri_build::WindowsAttributes::new().app_manifest(manifest));

    // В релиз вшивается собранный сервер (dist\pipo-server.exe) — на выходе один exe, как и раньше.
    if release {
        let dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
        let server = dir.join("..").join("dist").join("pipo-server.exe");
        let server = server
            .canonicalize()
            .unwrap_or_else(|_| panic!("нет {} — сначала соберите сервер (build_exe.bat)", server.display()));
        println!("cargo:rustc-env=PIPO_SERVER_EXE={}", server.display());
        println!("cargo:rerun-if-changed={}", server.display());
    }
    println!("cargo:rerun-if-changed=app.manifest");

    tauri_build::try_build(attrs).expect("tauri-build");
}

// Окно-оболочка на Tauri открывает страницу с ?shell=tauri: у неё есть значок в трее,
// а крестик прячет окно, а не закрывает приложение.
export const IN_TRAY_SHELL = new URLSearchParams(location.search).get("shell") === "tauri";

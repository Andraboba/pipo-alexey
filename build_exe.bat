@echo off
rem cmd читает .bat в кодировке консоли: переключаем на UTF-8, в конце возвращаем прежнюю
for /f "tokens=2 delims=:" %%a in ('chcp') do set "OLD_CP=%%a"
chcp 65001 >nul
rem Собирает dist\PipoAlexey.exe:
rem   1) React-интерфейс  2) сервер pipo-server.exe (PyInstaller)  3) окно с треем на Tauri (Rust),
rem   в которое сервер вшивается — на выходе снова один exe.
rem Нет Rust (cargo) — собирается прежнее окно на pywebview, без значка в трее.
cd /d "%~dp0"

echo [1/3] UI...
pushd frontend
call npm install --no-fund --no-audit || goto :fail
call npm run build || goto :fail
popd

where cargo >nul 2>&1 || goto :legacy

echo [2/3] Сервер...
".venv\Scripts\python.exe" -m PyInstaller pipo-server.spec --noconfirm --clean || goto :fail

echo [3/3] Окно и трей...
pushd desktop
cargo build --release || (popd & goto :fail)
popd
copy /y "desktop\target\release\pipo-alexey.exe" "dist\PipoAlexey.exe" >nul || goto :fail
goto :done

:legacy
echo cargo не найден — собираю окно на pywebview без трея (Rust: https://rustup.rs)
echo [2/2] EXE...
".venv\Scripts\python.exe" -m PyInstaller pipo.spec --noconfirm --clean || goto :fail

:done
echo.
echo Готово: %~dp0dist\PipoAlexey.exe
chcp %OLD_CP% >nul
exit /b 0

:fail
echo Сборка не удалась
pause
chcp %OLD_CP% >nul
exit /b 1

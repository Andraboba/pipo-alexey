@echo off
rem cmd читает .bat в кодировке консоли: переключаем на UTF-8, в конце возвращаем прежнюю
rem только номер: "Active code page: 866" или "Aktive Codepage: 850." (с точкой) — set /a отбросит пробелы
for /f "tokens=2 delims=:." %%a in ('chcp') do set /a "OLD_CP=%%a" >nul
chcp 65001 >nul
rem Запуск из исходников (для разработки). Обычный способ — dist\PipoAlexey.exe
cd /d "%~dp0"

rem React-интерфейс: собрать, если сборки ещё нет (нужен Node.js)
if not exist "web\dist\index.html" (
    where npm >nul 2>&1 && (
        echo Building UI...
        pushd frontend
        call npm install --no-fund --no-audit
        call npm run build
        popd
    )
)

rem pythonw — без чёрного окна консоли: откроется только окно приложения
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" main.py %*
) else (
    start "" pythonw main.py %*
)
chcp %OLD_CP% >nul

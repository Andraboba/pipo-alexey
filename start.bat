@echo off
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

@echo off
rem cmd читает .bat в кодировке консоли: переключаем на UTF-8, в конце возвращаем прежнюю
for /f "tokens=2 delims=:" %%a in ('chcp') do set "OLD_CP=%%a"
chcp 65001 >nul
rem Собирает dist\PipoAlexey.exe: сначала React-интерфейс, потом exe через PyInstaller
cd /d "%~dp0"

echo [1/2] UI...
pushd frontend
call npm install --no-fund --no-audit || goto :fail
call npm run build || goto :fail
popd

echo [2/2] EXE...
".venv\Scripts\python.exe" -m PyInstaller pipo.spec --noconfirm --clean || goto :fail

echo.
echo Готово: %~dp0dist\PipoAlexey.exe
chcp %OLD_CP% >nul
exit /b 0

:fail
echo Сборка не удалась
pause
chcp %OLD_CP% >nul
exit /b 1

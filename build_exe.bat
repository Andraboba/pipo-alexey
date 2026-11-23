@echo off
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
exit /b 0

:fail
echo Сборка не удалась
pause
exit /b 1

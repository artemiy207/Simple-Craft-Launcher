@echo off
chcp 65001 >nul
title Simple Craft Launcher — сборка EXE
:: Сборка одного .exe со всем нужным: ассеты, шрифты и core/launcher_core.py внутри.
:: Игра всё равно ставится рядом с .exe (папки data/ и instances/ создаются автоматически).

if not exist "icon.ico" (
    echo [ОШИБКА] Нет файла icon.ico в папке! Положи его сюда.
    pause
    exit /b
)

echo Компилируем...
pyinstaller ^
  --noconfirm ^
  --clean ^
  --noconsole ^
  --onefile ^
  --icon="icon.ico" ^
  --name="SimpleCraftLauncher" ^
  --collect-all customtkinter ^
  --add-data "assets;assets" ^
  --add-data "core;core" ^
  "Simple-Craft-Launcher.py"

echo.
echo ГОТОВО! Файл: dist\SimpleCraftLauncher.exe
pause

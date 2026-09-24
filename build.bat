@echo off
chcp 65001 >nul
title Simple Craft Launcher
echo Запуск Simple Craft Launcher...

:: Проверяем, установлен ли Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в системе. Установите его с python.org
    pause
    exit /b
)

:: Запуск скрипта
python "Simple-Craft-Launcher.py"

:: Если программа упала, держим окно открытым, чтобы увидеть ошибку
if %errorlevel% neq 0 (
    echo.
    echo [!] Программа завершилась с ошибкой (код %errorlevel%).
    pause
) else (
    exit
)

@echo off
:: Убедись, что файл иконки называется именно icon.ico
:: Если нет — просто переименуй свою картинку в icon.ico
if not exist "icon.ico" (
    echo [ОШИБКА] Нет файла icon.ico в папке! Положи его сюда.
    pause
    exit
)

echo Компилируем...
pyinstaller --noconsole --onefile --icon="icon.ico" --name="SimpleCraftLauncher" Simple-Craft-Launcher.py

echo.
echo ГОТОВО!
echo Ищи файл 'SimpleCraftLauncher.exe' в папке 'dist'.
pause
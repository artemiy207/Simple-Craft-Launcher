"""Проверка сайта: все локальные ссылки ведут на существующие файлы."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
DOCS = "docs"
html = open(os.path.join(DOCS, "index.html"), encoding="utf-8").read()

refs = set()
for attr in ("src", "href"):
    refs |= set(re.findall(rf'{attr}="([^"]+)"', html))

local = [r for r in refs if not r.startswith(("http", "#", "mailto:", "//"))] + \
        re.findall(r"url\(([^)]+)\)", open(os.path.join(DOCS, "css", "style.css"),
                                          encoding="utf-8").read())
missing = []
for ref in sorted(local):
    clean = ref.split("?")[0].split("#")[0].strip("'\"")
    if not clean or clean.startswith("data:"):
        continue
    if not os.path.exists(os.path.join(DOCS, clean)):
        missing.append(clean)

print("локальных ссылок:", len(local))
print("не найдено:", missing if missing else "ничего — всё на месте")

# структура сайта
for root, dirs, files in os.walk(DOCS):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for name in sorted(files):
        path = os.path.join(root, name)
        print(f"  {os.path.relpath(path, DOCS):32} {os.path.getsize(path) / 1024:8.1f} КБ")

# базовые проверки HTML
for tag in ("</html>", "</body>", 'id="download"', 'id="lightbox"', "js/app.js", "css/style.css"):
    print(("есть  " if tag in html else "НЕТ   ") + tag)
print("ВСЁ ЧИСТО" if not missing else "ЕСТЬ БИТЫЕ ССЫЛКИ")

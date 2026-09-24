"""Готовит ассеты сайта: иконки, плейсхолдеры скриншотов, 404/robots/sitemap/.nojekyll."""
import os
import shutil

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")
ASSETS = os.path.join(DOCS, "assets")
FONT = os.path.join(ROOT, "assets", "fonts", "Montserrat-Bold.ttf")
SITE = "https://artemiy207.github.io/Simple-Craft-Launcher/"

os.makedirs(ASSETS, exist_ok=True)

# 1. иконки для сайта
for name in ("app_icon.ico", "logo.png", "box_icon.png"):
    src = os.path.join(ROOT, "assets", "images", name)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(ASSETS, name))
        print("скопировано:", name)

# 2. плейсхолдеры скриншотов (потом замени своими)
CAPTIONS = [
    ("screenshot-1.png", "Главный экран", "карточки сборок, темы, кнопка «Играть»"),
    ("screenshot-2.png", "Менеджер модов", "поиск на Modrinth и «Обновить все моды»"),
    ("screenshot-3.png", "Бэкапы миров", "создание и восстановление в один клик"),
]


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except Exception:
        return ImageFont.load_default()


for filename, title, subtitle in CAPTIONS:
    img = Image.new("RGB", (1280, 720), (15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([60, 60, 1220, 660], radius=24, outline=(37, 49, 74), width=3)
    draw.rounded_rectangle([100, 120, 1180, 620], radius=16, fill=(27, 36, 55))
    draw.text((140, 190), title, font=font(46), fill=(230, 236, 245))
    draw.text((140, 260), subtitle, font=font(26), fill=(143, 163, 191))
    draw.text((140, 330), "Это плейсхолдер — положи свой скриншот",
              font=font(22), fill=(16, 185, 129))
    draw.text((140, 366), f"в docs/assets/{filename}", font=font(22), fill=(16, 185, 129))
    draw.rounded_rectangle([140, 430, 420, 500], radius=12, fill=(16, 185, 129))
    draw.text((176, 450), "Играть", font=font(28), fill=(5, 34, 26))
    img.save(os.path.join(ASSETS, filename))
    print("создан плейсхолдер:", filename)

# 3. страница 404 для GitHub Pages
with open(os.path.join(DOCS, "404.html"), "w", encoding="utf-8") as f:
    f.write(f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Страница не найдена — Simple Craft Launcher</title>
<link rel="icon" href="assets/app_icon.ico">
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
          background:#0f172a; color:#e6ecf5; text-align:center;
          font:16px/1.6 system-ui,"Segoe UI",Roboto,sans-serif }}
  a {{ color:#10b981 }}
</style>
</head>
<body>
  <div>
    <h1 style="font-size:64px;margin:0">404</h1>
    <p>Такой страницы нет 🧭</p>
    <p><a href="{SITE}">← Вернуться на главную</a> ·
       <a href="https://github.com/artemiy207/Simple-Craft-Launcher/releases">Скачать лаунчер</a></p>
  </div>
</body>
</html>
""")
print("создан: 404.html")

# 4. robots.txt и sitemap.xml
with open(os.path.join(DOCS, "robots.txt"), "w", encoding="utf-8") as f:
    f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}sitemap.xml\n")

with open(os.path.join(DOCS, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{SITE}</loc>
    <changefreq>monthly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
""")
print("созданы: robots.txt, sitemap.xml")

# 5. .nojekyll — чтобы GitHub Pages не прогонял файлы через Jekyll
open(os.path.join(DOCS, ".nojekyll"), "w", encoding="utf-8").close()
print("создан: .nojekyll")
print("ГОТОВО")

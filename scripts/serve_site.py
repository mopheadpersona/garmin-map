#!/usr/bin/env python3
"""Локальный сервер конфигуратора цветов: http://127.0.0.1:8765

    python3 scripts/serve_site.py [порт] [папка]

Отдаёт папку site/ или ту, что названа вторым аргументом (например, build/pages — страница,
собранная для выкладки). Путь берётся от расположения скрипта, а не от текущего каталога:
так сервер запускается и оттуда, где текущий каталог недоступен.
"""

import functools
import http.server
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")      # правки видны сразу после обновления страницы
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    folder = os.path.join(ROOT, sys.argv[2] if len(sys.argv) > 2 else "site")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=folder))
    print("http://127.0.0.1:%d  (папка %s)" % (port, folder), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

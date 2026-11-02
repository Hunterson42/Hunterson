"""
Renders each day's card page to the image shown when the day's link is posted:
OUT/card/GRADE/DATE.html -> OUT/og/GRADE/DATE.png, 1200 by 630 pixels.

    python3 scripts/site/render_cards.py OUT_DIR

Needs the playwright package (pip install playwright) and a browser: the Chrome
already on GitHub's Ubuntu runners is used if present, otherwise Playwright's
own Chromium. Chrome's command-line screenshot is not used because it renders
a shorter page than the image it saves. This step only draws pictures of
figures already published; it is not part of the assessment, which uses the
Python standard library only.

A card that already has an image is skipped: images, like day pages, are
written once. The pages are served from a local address so the fonts load.
"""
import functools
import http.server
import os
import sys
import threading

from playwright.sync_api import sync_playwright


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def render(out_dir):
    out_dir = os.path.abspath(out_dir)
    if not os.path.isdir(os.path.join(out_dir, "card")):
        return 0                          # nothing built yet, as before the launch date
    cards = []
    for g in sorted(os.listdir(os.path.join(out_dir, "card"))):
        folder = os.path.join(out_dir, "card", g)
        if os.path.isdir(folder):
            cards += ["%s/%s" % (g, f[:-5]) for f in sorted(os.listdir(folder)) if f.endswith(".html")]
    todo = [c for c in cards if not os.path.exists(os.path.join(out_dir, "og", c + ".png"))]
    if not todo:
        return 0
    handler = functools.partial(Quiet, directory=out_dir)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome")
            except Exception:
                browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 630}, color_scheme="light")
            for c in todo:
                os.makedirs(os.path.dirname(os.path.join(out_dir, "og", c)), exist_ok=True)
                page.goto("http://127.0.0.1:%d/card/%s.html" % (port, c))
                page.evaluate("document.fonts.ready")
                page.wait_for_timeout(150)
                page.screenshot(path=os.path.join(out_dir, "og", c + ".png"))
            browser.close()
    finally:
        server.shutdown()
    return len(todo)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    print("Cards rendered: %d" % render(sys.argv[1]))

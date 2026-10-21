"""Build the local React frontend without a Node toolchain or network access."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def build():
    target = ROOT / 'dist'
    target.mkdir(exist_ok=True)
    for name in ('src', 'vendor'):
        shutil.copytree(ROOT / name, target / name, dirs_exist_ok=True)
    page = '''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Covered Call Optimizer</title>
<link rel="stylesheet" href="/frontend/dist/src/styles.css">
<script type="importmap">{"imports":{"react":"/frontend/dist/vendor/react.js","react-dom/client":"/frontend/dist/vendor/react-dom-client.js"}}</script>
<script src="/profile_settings.js"></script>
<script type="module" src="/frontend/dist/src/main.js"></script>
</head><body><div id="root"></div><noscript>Enable JavaScript to use the covered-call optimizer.</noscript></body></html>
'''
    (target / 'index.html').write_text(page, encoding='utf-8')
    # One browser shell; React selects the page from the URL.
    (ROOT.parent / 'index.html').write_text(page, encoding='utf-8')
    print('Built local React frontend in frontend/dist')


if __name__ == '__main__':
    build()

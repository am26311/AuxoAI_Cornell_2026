"""No-spend setup check. Does not send credentials or make an API request."""
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path


def main():
    python_ok = sys.version_info >= (3, 10)
    result = {'python': sys.version.split()[0], 'python_ok': python_ok, 'platform': platform.system(),
              'api_key_present_in_process': bool(os.getenv('OPENAI_API_KEY')),
              'paid_api_test': 'not_run', 'packages': {}, 'browser': 'not_run'}
    for name in ['openai', 'playwright', 'pydantic', 'pytest']:
        try:
            result['packages'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result['packages'][name] = 'MISSING'
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content('<h1>Cornell preflight</h1>')
            result['browser'] = 'passed' if page.locator('h1').inner_text() == 'Cornell preflight' else 'failed'
            browser.close()
    except Exception as exc:
        result['browser'] = type(exc).__name__ + ': launch failed; check browser installation and OS permissions'
    print(json.dumps(result, indent=2))
    ready = python_ok and result['browser'] == 'passed' and 'MISSING' not in result['packages'].values()
    if not python_ok:
        print('\nPython %s is too old: this project needs Python 3.10 or newer (3.12 is best). Ask Codex to help you install it.' % result['python'])
    print('\nREADY' if ready else '\nNOT READY: ask Codex what went wrong and to fix it, or tell a champion when you arrive')
    return 0 if ready else 1


if __name__ == '__main__':
    raise SystemExit(main())

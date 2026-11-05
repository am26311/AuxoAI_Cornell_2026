import sys
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_agent.browser import BrowserSession, Policy
from research_agent.practice import serve_practice


@pytest.fixture
def session():
    with serve_practice(ROOT / 'practice') as origin, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        session = BrowserSession(browser, Policy([], origin))
        try:
            yield session, origin
        finally:
            session.close()
            browser.close()

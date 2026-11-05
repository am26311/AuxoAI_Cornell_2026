from pathlib import Path
import pytest
from research_agent.browser import Policy, PreventedAction
from research_agent.models import Action
from research_agent.practice import serve_practice
from research_agent.runner import ROOT


def click(e):
    return Action(kind='click', element_id=e['id'], text='', direction='none')


@pytest.mark.parametrize('url', [
    'https://www.dell.com/checkout', 'https://www.dell.com/%2563heckout',
    'https://www.dell.com/cart/add', 'https://www.dell.com/returns.pdf',
    'https://www.dell.com.evil.test/laptops', 'http://www.dell.com/',
    'javascript:alert(1)', 'https://x:secret@www.dell.com/',
])
def test_prohibited_urls(url):
    assert not Policy(['www.dell.com']).url_allowed(url)


def test_observation_and_click(session, tmp_path):
    s, origin = session
    s.goto(origin + '/store-a/index.html')
    obs = s.observe(tmp_path / 'before.png')
    e = next(e for e in obs['elements'] if e['name'] == 'Browse laptops')
    assert s.execute(click(e))[0]
    s.observe(tmp_path / 'after.png')
    assert s.page.url.endswith('/catalog.html')
    assert (tmp_path / 'before.png').stat().st_size > 1000


def test_hidden_and_forbidden_controls(session, tmp_path):
    s, origin = session
    s.goto(origin + '/store-a/safety.html')
    obs = s.observe(tmp_path / 'safety.png')
    assert 'Hidden below viewport' not in [e['name'] for e in obs['elements']]
    for name in ['Continue to checkout', 'External site', 'Download returns', 'Submit']:
        e = next(e for e in obs['elements'] if e['name'] == name)
        with pytest.raises(PreventedAction):
            s.execute(click(e))
    assert s.page.url.endswith('/safety.html')


def test_personal_data_and_search(session, tmp_path):
    s, origin = session
    s.goto(origin + '/store-a/safety.html')
    obs = s.observe(tmp_path / 'fields.png')
    e = next(e for e in obs['elements'] if e['name'] == 'Email address')
    with pytest.raises(PreventedAction):
        s.execute(Action(kind='type', element_id=e['id'], text='a@b.com', direction='none'))
    s.goto(origin + '/store-a/index.html')
    obs = s.observe(tmp_path / 'search.png')
    e = next(e for e in obs['elements'] if e['name'] == 'Product search')
    assert s.execute(Action(kind='type', element_id=e['id'], text='laptop', direction='none'))[0]


def test_post_request_blocked_independently_of_button_label(session, tmp_path):
    s, origin = session
    s.goto(origin + '/store-a/safety.html')
    obs = s.observe(tmp_path / 'post.png')
    e = next(e for e in obs['elements'] if e['name'] == 'View more details')
    s.execute(click(e))
    assert any(r['method'] == 'POST' for r in s.blocked_requests)
    blocked = next(r for r in s.blocked_requests if r['method'] == 'POST')
    assert blocked['why'] == 'non_read_method' and blocked['path'].startswith('/') and 'host' in blocked
    assert not any('?' in r['path'] for r in s.blocked_requests)


def test_stale_target_and_scrolling(session, tmp_path):
    s, origin = session
    s.goto(origin + '/store-a/index.html')
    obs = s.observe(tmp_path / 'stale.png')
    e = next(e for e in obs['elements'] if e['name'] == 'Browse laptops')
    s.page.locator('a').first.evaluate('(e)=>e.textContent="Changed"')
    assert not s.execute(click(e))[0]
    s.goto(origin + '/store-a/safety.html')
    s.execute(Action(kind='scroll', element_id=None, text='', direction='down'))
    assert s.page.evaluate('scrollY') > 0


def test_direct_forbidden_navigation_is_blocked(session):
    s, origin = session
    with pytest.raises(PreventedAction):
        s.goto(origin + '/store-a/checkout.html')


def test_target_identity_survives_other_elements_changing(session, tmp_path):
    s, origin = session
    s.goto(origin + '/store-a/index.html')
    obs = s.observe(tmp_path / 'stable.png')
    e = next(e for e in obs['elements'] if e['name'] == 'Browse laptops')
    # Mimic a rotating promo adding a preceding element and shifting the layout.
    s.page.evaluate("""() => {const b=document.createElement('button');b.textContent='New promo';
      document.body.prepend(b);} """)
    assert s.execute(click(e))[0]
    assert s.page.url.endswith('/catalog.html')


def test_product_option_radio_is_allowed_but_subscription_is_not(session, tmp_path):
    s, origin = session
    s.goto(origin + '/store-a/index.html')
    s.page.set_content('<label>32 GB memory<input type="radio" name="memory"></label>'
                       '<label>Subscribe to newsletter<input type="checkbox"></label>')
    obs = s.observe(tmp_path / 'options.png')
    memory = next(e for e in obs['elements'] if e['name'] == '32 GB memory')
    assert s.execute(click(memory))[0]
    assert s.page.locator('input[type=radio]').is_checked()
    newsletter = next(e for e in obs['elements'] if e['name'] == 'Subscribe to newsletter')
    with pytest.raises(PreventedAction):
        s.execute(click(newsletter))


def _site_policy(site_id):
    from research_agent.runner import ROOT, load_track
    site = next(s for s in load_track(ROOT / 'tracks/dell-laptops.json')['sites'] if s['id'] == site_id)
    return Policy(site['allowed_hosts'], allowed_paths=site['allowed_paths'])


@pytest.mark.parametrize('site_id,url,allowed', [
    ('apple', 'https://www.apple.com/shop/buy-mac/macbook-air', True),
    ('apple', 'https://www.apple.com/shop/buy-mac/macbook-air/13-inch-midnight-m5', True),
    ('apple', 'https://www.apple.com/shop/bag', False),
    ('apple', 'https://www.apple.com/shop/buy-mac/macbook-air?add-to-cart=1', False),
    ('apple', 'https://www.apple.com/shop/buy-mac/checkout', False),
    ('apple', 'https://www.apple.com/shop/buy-mac/macbook-air/../../bag', False),
    ('apple', 'https://www.apple.com/shop/buy-iphone/iphone-17', False),
    ('samsung', 'https://www.samsung.com/us/computing/galaxy-books/galaxy-book5-series/buy/galaxy-book5-pro-360-16-in/', True),
    ('samsung', 'https://www.samsung.com/us/computing/galaxy-books/galaxy-book5-series/buy/cart', False),
    ('samsung', 'https://www.samsung.com/us/smartphones/galaxy-s26/buy/', False),
    ('dell', 'https://www.dell.com/en-us/shop/buy/x', False),
])
def test_product_page_exception_is_narrow(site_id, url, allowed):
    assert _site_policy(site_id).url_allowed(url) is allowed


def test_exempt_buy_link_followable_but_cart_controls_blocked():
    apple, dell = _site_policy('apple'), _site_policy('dell')
    act = Action(kind='click', element_id=1, text='', direction='none')
    apple.check_target(act, {'name': 'Buy', 'href': 'https://www.apple.com/shop/buy-mac/macbook-air', 'tag': 'a'})
    for policy, element in [(apple, {'name': 'Add to Bag', 'href': '', 'tag': 'button'}),
                            (apple, {'name': 'Buy and add to bag', 'href': 'https://www.apple.com/shop/buy-mac/macbook-air', 'tag': 'a'}),
                            (dell, {'name': 'Buy', 'href': 'https://www.dell.com/en-us/shop/x', 'tag': 'a'})]:
        with pytest.raises(PreventedAction):
            policy.check_target(act, element)


def test_exception_patterns_must_be_anchored(tmp_path):
    import json
    from research_agent.runner import ROOT, load_track
    track = json.loads((ROOT / 'tracks/dell-laptops.json').read_text())
    track['sites'][1]['allowed_paths'] = ['.*']
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps(track))
    with pytest.raises(ValueError, match='anchored'):
        load_track(bad)


@pytest.mark.parametrize('resource_type,path,allowed', [
    ('stylesheet', '/public/buy-spa/_next/static/css/ec9635a230e6ac2a.css', True),
    ('script', '/public/buy-spa/_next/static/chunks/pages/%5B...slug%5D-fcf3a7f80fe47d5e.js', True),
    ('script', '/public/buy-spa/_next/static/../../api/cart.js', False),
    ('fetch', '/public/buy-spa/_next/static/css/a.css', False),
    ('xhr', '/public/buy-spa/api/add-to-cart', False),
    ('script', '/public/buy-spa/api/cart.js', False),
])
def test_samsung_static_asset_exception_is_narrow(resource_type, path, allowed):
    from research_agent.runner import ROOT, load_track
    site = next(s for s in load_track(ROOT / 'tracks/dell-laptops.json')['sites'] if s['id'] == 'samsung')
    policy = Policy(site['allowed_hosts'], allowed_paths=site['allowed_paths'], allowed_asset_paths=site['allowed_asset_paths'])
    assert policy.static_asset_allowed(resource_type, path) is allowed


def test_other_sites_get_no_asset_exception():
    from research_agent.runner import ROOT, load_track
    for site in load_track(ROOT / 'tracks/dell-laptops.json')['sites']:
        if site['id'] != 'samsung':
            assert site['allowed_asset_paths'] == []


LOOP_PAGE = b'<a href="/">back</a><script>setTimeout(function(){while(true){}},300)</script>'
HOME_PAGE = b'<a href="/loop">next</a>'


def serve_loop_page():
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = LOOP_PAGE if self.path == '/loop' else HOME_PAGE
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_address[1]}'


def test_stuck_page_raises_page_unresponsive_instead_of_hanging(tmp_path):
    """A page stuck in a script loop used to block frame.evaluate forever."""
    import time
    from playwright.sync_api import sync_playwright
    from research_agent.browser import BrowserSession, PageUnresponsive
    server, origin = serve_loop_page()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            s = BrowserSession(browser, Policy([], origin), deadline_seconds=3)
            s.goto(origin + '/')
            s.page.locator('a').click(no_wait_after=True)
            s.page.wait_for_timeout(700)  # let the loop start
            started = time.monotonic()
            with pytest.raises(PageUnresponsive):
                s.observe(tmp_path / 'stuck.png')
            assert time.monotonic() - started < 15
            assert s.dead
            s.close()  # must not hang on a stopped browser
            try:
                browser.close()
            except Exception:
                pass
            # A fresh browser from the same Playwright works.
            browser = p.chromium.launch(headless=True)
            fresh = BrowserSession(browser, Policy([], origin), deadline_seconds=3)
            fresh.goto(origin + '/')
            assert fresh.observe(tmp_path / 'ok.png')['elements']
            fresh.close()
            browser.close()
    finally:
        server.shutdown()


def test_normal_pages_are_not_cut_off_by_the_deadline(session, tmp_path):
    s, origin = session
    s.goto(origin + '/store-a/index.html')
    assert s.observe(tmp_path / 'fine.png')['elements']
    assert not s.dead


NAVIGATE_ONCE = """() => {
  if (!sessionStorage.getItem('went')) {
    sessionStorage.setItem('went', '1');
    location.href = '/loop-free';
    return new Promise(() => {});
  }
  return 'read the new page';
}"""


def test_evaluate_rides_out_a_navigation(tmp_path):
    """The live Dell stall: a click's navigation landed mid-read and raised 'Execution context was destroyed'."""
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    from research_agent.browser import BrowserSession
    server, origin = serve_loop_page()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            s = BrowserSession(browser, Policy([], origin), deadline_seconds=20)
            s.goto(origin + '/')
            # Without the retry this raises exactly the error seen on dell.com.
            with pytest.raises(PlaywrightError, match='Execution context was destroyed'):
                s.page.evaluate(NAVIGATE_ONCE)
            s.page.evaluate("sessionStorage.removeItem('went')")
            assert s._evaluate(s.page, NAVIGATE_ONCE) == 'read the new page'
            s.close()
            browser.close()
    finally:
        server.shutdown()


def test_other_errors_are_not_swallowed_by_the_navigation_retry(session):
    from playwright.sync_api import Error as PlaywrightError
    s, origin = session
    s.goto(origin + '/store-a/index.html')
    with pytest.raises(PlaywrightError):
        s._evaluate(s.page, "() => { throw new Error('a different problem') }")


def test_close_is_safe_to_repeat_and_never_raises(session):
    s, origin = session
    s.goto(origin + '/store-a/index.html')
    s.close()
    s.close()  # context already closed; must not raise or hang


SEARCH_POST = ['sribsrch.ecom.samsung.com /estoresearch-api/v1/scom/us/pf_search']


def read_post_policy():
    return Policy(['www.samsung.com'], allowed_read_posts=SEARCH_POST)


class FakeRequest:
    def __init__(self, method, url, resource_type, navigation=False):
        self.method, self.url, self.resource_type, self._nav = method, url, resource_type, navigation

    def is_navigation_request(self):
        return self._nav


def reason(policy, request):
    from research_agent.browser import BrowserSession
    return BrowserSession.block_reason(type('S', (), {'policy': policy})(), request)


def test_the_one_signed_off_search_post_is_allowed():
    url = 'https://sribsrch.ecom.samsung.com/estoresearch-api/v1/scom/us/pf_search'
    assert reason(read_post_policy(), FakeRequest('POST', url, 'xhr')) is None
    assert reason(read_post_policy(), FakeRequest('POST', url, 'fetch')) is None


@pytest.mark.parametrize('method,url,kind', [
    ('POST', 'https://sribsrch.ecom.samsung.com/estoresearch-api/v1/scom/us/pf_search/extra', 'xhr'),   # other path
    ('POST', 'https://sribsrch.ecom.samsung.com/estoresearch-api/v1/scom/us/order', 'xhr'),
    ('POST', 'https://evil.example.com/estoresearch-api/v1/scom/us/pf_search', 'xhr'),                  # other host
    ('POST', 'https://sribsrch.ecom.samsung.com/estoresearch-api/v1/scom/us/pf_search', 'document'),    # a form submit
    ('PUT', 'https://sribsrch.ecom.samsung.com/estoresearch-api/v1/scom/us/pf_search', 'xhr'),          # other method
    ('DELETE', 'https://sribsrch.ecom.samsung.com/estoresearch-api/v1/scom/us/pf_search', 'xhr'),
    ('POST', 'https://smetrics.samsung.com/ee/v1/interact', 'fetch'),                                   # tracking stays blocked
    ('POST', 'https://www.samsung.com/us/cart/add', 'xhr'),
])
def test_every_other_post_is_still_blocked(method, url, kind):
    assert reason(read_post_policy(), FakeRequest(method, url, kind)) is not None


def test_without_the_exception_the_search_post_is_blocked():
    url = 'https://sribsrch.ecom.samsung.com/estoresearch-api/v1/scom/us/pf_search'
    assert reason(Policy(['www.samsung.com']), FakeRequest('POST', url, 'xhr')) == 'non_read_method'


def test_allowed_read_posts_must_be_a_literal_host_and_anchored_path(tmp_path):
    import json
    from research_agent.runner import load_track, ROOT
    track = json.loads((ROOT / 'tracks/dell-laptops.json').read_text())
    for bad in ('.*.samsung.com /a', 'sribsrch.ecom.samsung.com a', 'sribsrch.ecom.samsung.com /../x'):
        track['sites'][1]['allowed_read_posts'] = [bad]
        path = tmp_path / 'bad.json'
        path.write_text(json.dumps(track))
        with pytest.raises(ValueError, match='allowed_read_posts'):
            load_track(path)


def test_recording_saves_a_playable_webm_only_when_asked(tmp_path):
    from playwright.sync_api import sync_playwright
    from research_agent.browser import BrowserSession
    with serve_practice(ROOT / 'practice') as origin, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        recorded = BrowserSession(browser, Policy([], origin), record_dir=tmp_path / 'videos')
        recorded.goto(origin + '/store-a/index.html')
        recorded.observe(tmp_path / 'a.png')
        recorded.close(video_name='store-a.webm')
        plain = BrowserSession(browser, Policy([], origin))
        plain.goto(origin + '/store-a/index.html')
        plain.close(video_name='never.webm')
        browser.close()
    video = tmp_path / 'videos' / 'store-a.webm'
    assert video.stat().st_size > 1000 and video.read_bytes()[:4] == b'\x1a\x45\xdf\xa3'  # WebM/EBML header
    assert [f.name for f in (tmp_path / 'videos').iterdir()] == ['store-a.webm']

"""Eyes (screenshot + visible elements) and the Referee (independently enforced safety policy)."""
import os
import re
import signal
import subprocess
import sys
import threading
from contextlib import contextmanager
from urllib.parse import unquote, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as BrowserTimeout


class PreventedAction(RuntimeError):
    pass


# A click that navigates can destroy the page's script context while we are reading the page.
NAVIGATION_RACE = re.compile(r"execution context was destroyed|most likely because of a navigation|frame was detached|cannot find context", re.I)


class PageUnresponsive(RuntimeError):
    """The page stopped answering the runner; its browser was stopped so the run can go on."""


def kill_browser_processes():
    """Stop the Chromium processes started by this process, and nothing else.

    A page stuck in a script loop blocks every Playwright call that has no timeout of its own
    (frame.evaluate, close). Killing Chromium makes the blocked call fail at once. The Playwright
    driver, other programs and anyone else's browser are left alone.
    """
    me = os.getpid()
    try:
        if sys.platform == 'win32':
            script = (f"$p=Get-CimInstance Win32_Process;$k=@({me});do{{$n=$p|?{{$k -contains $_.ParentProcessId -and $k -notcontains $_.ProcessId}};"
                      "$k+=@($n.ProcessId)}}while($n);$p|?{$k -contains $_.ProcessId -and $_.Name -match 'chrome|chromium|headless_shell'}|%{Stop-Process -Id $_.ProcessId -Force}")
            subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, timeout=20)
            return
        rows = subprocess.run(['ps', '-axo', 'pid=,ppid=,comm='], capture_output=True, text=True, timeout=10).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return
    procs = {}
    for row in rows:
        parts = row.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            procs[int(parts[0])] = (int(parts[1]), parts[2])
    mine, grew = {me}, True
    while grew:
        grew = False
        for pid, (ppid, _) in procs.items():
            if ppid in mine and pid not in mine:
                mine.add(pid)
                grew = True
    for pid in mine - {me}:
        name = procs[pid][1].lower()
        if 'chrom' in name or 'headless_shell' in name:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def decoded(value):
    for _ in range(3):
        value = unquote(value)
    return value.lower()


DANGEROUS = re.compile(
    r"checkout|check.out|add.{0,15}(cart|bag)|\bcart\b|\bbag\b|\bbuy\b|"
    r"sign.?in|sign.?up|log.?in|register|account|password|payment|pay.?now|"
    r"place.{0,5}order|subscribe|newsletter|download|purchase|\border\b|"
    r"mailto:|tel:|\.pdf(?:$|[?#])|\.(?:zip|exe|dmg|docx?|xlsx?)(?:$|[?#])",
    re.I,
)


BUY_WORD = re.compile(r"\bbuy\b", re.I)
TRAVERSAL = re.compile(r"(?:^|/)\.\.(?:/|$)")


class Policy:
    def __init__(self, allowed_hosts, local_origin=None, allowed_paths=(), allowed_asset_paths=(), allowed_read_posts=()):
        self.allowed_hosts = set(allowed_hosts)
        self.allowed_read_posts = [(h.lower(), re.compile(p)) for h, p in (e.split(None, 1) for e in allowed_read_posts)]
        self.local_origin = local_origin
        self.allowed_asset_paths = [re.compile(p) for p in allowed_asset_paths]
        # Each pattern must match the WHOLE path. On a match, only the word "buy" is ignored;
        # cart, bag, checkout, sign-in and every other dangerous word still block.
        self.allowed_paths = [re.compile(p) for p in allowed_paths]

    def exempt_path(self, path):
        return any(p.fullmatch(path) for p in self.allowed_paths)

    def read_post_allowed(self, resource_type, host, path):
        # A site's own search box may POST its filters. Only XHR/fetch, only the listed host and exact path.
        path = decoded(path)
        return (resource_type in ("xhr", "fetch") and not TRAVERSAL.search(path)
                and any(h == (host or "").lower() and p.fullmatch(path) for h, p in self.allowed_read_posts))

    def static_asset_allowed(self, resource_type, path):
        # Only GET page assets; never XHR/fetch, never path traversal.
        path = decoded(path)
        return (resource_type in ("stylesheet", "script", "image", "font") and not TRAVERSAL.search(path)
                and any(p.fullmatch(path) for p in self.allowed_asset_paths))

    def path_dangerous(self, path):
        path = decoded(path)
        if self.exempt_path(path):
            path = BUY_WORD.sub('', path)
        return bool(DANGEROUS.search(path))

    def url_allowed(self, url):
        u = urlsplit(url)
        if u.username or u.password or self.path_dangerous(u.path) or DANGEROUS.search(decoded('?' + u.query)):
            return False
        if self.local_origin:
            return f"{u.scheme}://{u.netloc}" == self.local_origin
        return u.scheme == "https" and u.hostname in self.allowed_hosts and u.port in (None, 443)

    def check_url(self, url):
        if not self.url_allowed(url):
            raise PreventedAction("Destination is outside the read-only study boundary")

    def check_target(self, action, element):
        name, href = decoded(element["name"]), element.get("href", "")
        if href and element.get("tag") == "a" and self.url_allowed(href) and self.exempt_path(decoded(urlsplit(href).path)):
            # A plain link to an exempt product page (e.g. Apple's "Buy" link) may be followed;
            # its label is still checked for every other dangerous word.
            name, href = BUY_WORD.sub('', name), ''
        if DANGEROUS.search(name + " " + decoded(href)):
            raise PreventedAction("Transaction, identity, or download control")
        if element.get("download") or element.get("submit"):
            raise PreventedAction("Download or form submission control")
        if element.get("href"):
            self.check_url(element["href"])
        if action.kind == "type":
            label = decoded(element["name"] + " " + element.get("input_type", ""))
            if element.get("tag") != "input" or re.search(r"email|phone|name|address|password|card", label):
                raise PreventedAction("Only public product search and study ZIP fields may receive text")
            if re.search(r"zip|postal", label):
                if action.text != "10001":
                    raise PreventedAction("Only the fixed public study ZIP is permitted")
            elif element.get("input_type") not in ("search", "text") or not re.search(r"search", label):
                raise PreventedAction("Input is not a clearly identified product search field")
            if len(action.text) > 120 or re.search(r"[\r\n@]|https?://", action.text):
                raise PreventedAction("Search value contains unsupported content")
        if action.kind == "select" and element.get("tag") != "select":
            raise PreventedAction("Target is not a visible select control")
        if action.kind == "click" and element.get("tag") in ("input", "textarea"):
            option = element.get("input_type") in ("radio", "checkbox") and re.match(
                r"(?:(?:size|price|bestsellers|customer rating|compare|"
                r"memory|storage|processor|color|colour|screen|display|graphics|ram|ssd|brand|rating)\b"
                r"|\d+(?:\.\d+)?\s?(?:gb|tb|-?inch))",
                element["name"], re.I)
            if not option:
                raise PreventedAction("Only visible product-option inputs may be clicked; text fields need a permitted type action")


# Extract only intersecting, non-occluded controls. IDs are observation-local and
# revalidated before execution. No hidden page text goes to the persona.
EXTRACT = r"""() => {
 const all=[];
 function walk(root) { for (const e of root.querySelectorAll('*')) {
   if(e.matches('a[href],button,input,select,textarea,[role=button],[role=link]')) all.push(e);
   if(e.shadowRoot) walk(e.shadowRoot);
 }} walk(document);
 const answer=[]; window.__cornellNextTarget = window.__cornellNextTarget || 0;
 for(const e of all) {
   const r=e.getBoundingClientRect(), st=getComputedStyle(e);
   if(r.width<2||r.height<2||r.bottom<=0||r.right<=0||r.top>=innerHeight||r.left>=innerWidth||
      st.visibility!=='visible'||st.display==='none'||Number(st.opacity)===0||e.disabled) continue;
   const x=Math.max(0,Math.min(innerWidth-1,(Math.max(0,r.left)+Math.min(innerWidth,r.right))/2));
   const y=Math.max(0,Math.min(innerHeight-1,(Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2));
   const at=e.getRootNode().elementFromPoint?.(x,y) || document.elementFromPoint(x,y);
   if(at && at!==e && !e.contains(at)) continue;
   const name=(e.getAttribute('aria-label')||e.labels?.[0]?.innerText||e.innerText||e.placeholder||e.title||'').trim().replace(/\s+/g,' ').slice(0,180);
   if(!name) continue;
   if(!e.hasAttribute('data-cornell-target')) e.setAttribute('data-cornell-target', String(++window.__cornellNextTarget));
   const id=Number(e.getAttribute('data-cornell-target'));
   answer.push({local_id:id,name,tag:e.tagName.toLowerCase(),input_type:e.type||'',href:e.href||'',
     download:e.hasAttribute('download'),submit:!!e.form && (e.type==='submit'||e.type==='image'),
     x:Math.round(x),y:Math.round(y)});
 }
 return answer;
}"""


class BrowserSession:
    # Hard limits (seconds) for one observation, one action and one page load. Playwright's own
    # timeout does not cover evaluate(), so a page stuck in a script loop would block forever.
    OBSERVE_SECONDS, ACT_SECONDS, LOAD_SECONDS, CLOSE_SECONDS = 20, 30, 30, 10
    NAVIGATION_TRIES = 3

    def __init__(self, browser, policy, timeout_ms=8000, deadline_seconds=None, record_dir=None):
        self.policy = policy
        self.dead = False
        if deadline_seconds:
            self.OBSERVE_SECONDS = self.ACT_SECONDS = self.LOAD_SECONDS = self.CLOSE_SECONDS = deadline_seconds
        options = dict(viewport={"width": 1280, "height": 800}, locale="en-US", timezone_id="America/New_York",
                       accept_downloads=False, service_workers="block")
        self.record_dir = record_dir
        if record_dir:
            # Optional screen recording of the page only (a .webm per site). Nothing else changes.
            options.update(record_video_dir=str(record_dir), record_video_size={"width": 1280, "height": 800})
        self.context = browser.new_context(**options)
        self.context.set_default_timeout(timeout_ms)
        self.blocked_requests = []
        self.context.route("**/*", self._route)
        self.page = self.context.new_page()
        self.context.on("page", lambda p: p.close() if p != self.page else None)
        self.page.on("dialog", lambda d: d.dismiss())
        self.targets = {}

    def block_reason(self, r):
        path = urlsplit(r.url).path
        if r.method not in ("GET", "HEAD", "OPTIONS"):
            if not (r.method == "POST" and self.policy.read_post_allowed(r.resource_type, urlsplit(r.url).hostname, path)):
                return "non_read_method"
        if r.is_navigation_request():
            return None if self.policy.url_allowed(r.url) else "navigation_outside_policy"
        if self.policy.path_dangerous(path) and not (r.method == "GET" and self.policy.static_asset_allowed(r.resource_type, path)):
            return "dangerous_path_pattern"
        return None

    def _route(self, route):
        r = route.request
        why = self.block_reason(r)
        if why:
            # Host and path only, never the query string, so a blocked page can be diagnosed.
            u = urlsplit(r.url)
            self.blocked_requests.append({"method": r.method, "reason": "blocked_by_read_only_policy", "why": why,
                                          "type": r.resource_type, "host": u.hostname or "", "path": u.path[:120]})
            route.abort()
        else:
            route.continue_()

    @contextmanager
    def guard(self, seconds):
        """Stop the browser and raise PageUnresponsive if the block runs past `seconds`."""
        done, fired = threading.Event(), threading.Event()

        def watch():
            if not done.wait(seconds):
                fired.set()
                kill_browser_processes()

        threading.Thread(target=watch, daemon=True).start()
        try:
            yield
        except Exception as exc:
            if fired.is_set():
                self.dead = True
                raise PageUnresponsive(f"The page did not respond for {seconds} seconds") from exc
            raise
        else:
            if fired.is_set():
                self.dead = True
                raise PageUnresponsive(f"The page did not respond for {seconds} seconds")
        finally:
            done.set()

    def _evaluate(self, target, script):
        """evaluate() that rides out a navigation: wait for the new page, then read it again."""
        for attempt in range(1, self.NAVIGATION_TRIES + 1):
            try:
                return target.evaluate(script)
            except PlaywrightError as exc:
                if attempt == self.NAVIGATION_TRIES or not NAVIGATION_RACE.search(str(exc)):
                    raise
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                except PlaywrightError:
                    pass
                self.page.wait_for_timeout(300)

    def goto(self, url):
        with self.guard(self.LOAD_SECONDS):
            return self._goto(url)

    def _goto(self, url):
        self.policy.check_url(url)
        response = self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
        self.page.wait_for_timeout(800)
        if response and response.status in (401, 403, 429):
            return "website_block"
        return self._block_state()

    def block_state(self):
        with self.guard(self.OBSERVE_SECONDS):
            return self._block_state()

    def _block_state(self):
        # Inspect visible text for common access gates, not a full-page hidden DOM dump.
        text = self._evaluate(self.page, """() => [...document.querySelectorAll('h1,h2,p,button')]
          .filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&r.top<innerHeight&&r.bottom>0})
          .map(e=>e.innerText).join(' ').slice(0,5000)""")
        if re.search(r"robot or human|press (?:and|&) hold|verify (?:you are|you're) human|access denied|captcha|pardon our interruption", text, re.I):
            return "website_block"
        return None

    def observe(self, screenshot):
        with self.guard(self.OBSERVE_SECONDS):
            return self._observe(screenshot)

    def _observe(self, screenshot):
        self.targets = {}
        elements = []
        for frame in self.page.frames:
            try:
                # Third-party frames are unavailable to the executor, including payment widgets.
                if frame != self.page.main_frame and not self.policy.url_allowed(frame.url):
                    continue
                for e in self._evaluate(frame, EXTRACT):
                    e["id"] = len(elements) + 1
                    self.targets[e["id"]] = (frame, e)
                    elements.append(e)
            except Exception:
                if frame == self.page.main_frame:
                    raise
        self.page.screenshot(path=str(screenshot), full_page=False, timeout=8000)
        return {"url": self.page.url, "elements": elements}

    def execute(self, action):
        with self.guard(self.ACT_SECONDS):
            return self._execute(action)

    def _execute(self, action):
        blocked_before = len(self.blocked_requests)
        if action.kind == "none":
            return False, "No visible target matched the requested intent"
        if action.kind in ("click", "type", "select"):
            if action.element_id not in self.targets:
                return False, "Unknown or stale visible element id"
            frame, old = self.targets[action.element_id]
            # Observe again without replacing the target mapping; refuse DOM changes.
            try:
                fresh = self._evaluate(frame, EXTRACT)
            except PlaywrightError as exc:
                if NAVIGATION_RACE.search(str(exc)):
                    return False, "Page changed; target requires a new observation"
                raise
            current = next((e for e in fresh if e["local_id"] == old["local_id"]), None)
            keys = ("name", "tag", "href", "input_type", "submit", "download")
            if current is None or any(current[k] != old[k] for k in keys):
                return False, "Page changed; target requires a new observation"
            self.policy.check_target(action, current)
            target = frame.locator(f'[data-cornell-target="{old["local_id"]}"]')
            try:
                if action.kind == "click":
                    target.click(no_wait_after=True)
                elif action.kind == "type":
                    target.fill(action.text)
                else:
                    target.select_option(label=action.text)
            except BrowserTimeout:
                return False, "Visible target action timed out"
        elif action.kind == "scroll":
            if action.direction not in ("up", "down"):
                raise PreventedAction("Scroll direction must be up or down")
            self.page.mouse.wheel(0, 500 if action.direction == "down" else -500)
        elif action.kind == "back":
            previous = self.page.evaluate("document.referrer")
            if not previous or not self.policy.url_allowed(previous):
                raise PreventedAction("Cannot establish a permitted previous page")
            self.page.go_back(wait_until="domcontentloaded", timeout=8000)
        elif action.kind == "wait":
            self.page.wait_for_timeout(500)
        self.page.wait_for_timeout(650)
        self.policy.check_url(self.page.url)
        return True, ("Action executed; compare the next screenshot with the intent" +
                      (". Runner restricted a network request; missing content may reflect the runner policy."
                       if len(self.blocked_requests) > blocked_before else ""))

    def close(self, video_name=None):
        if self.dead:
            return  # the browser was stopped; there is nothing left to close politely
        video = self.page.video if self.record_dir else None
        try:
            with self.guard(self.CLOSE_SECONDS):
                # Drop the request handlers first; closing with one still pending can wait forever.
                self.context.unroute_all(behavior="ignoreErrors")
                self.context.close()
        except Exception:
            self.dead = True  # closing is best effort; the run's own status is what matters
        if video and video_name and not self.dead:
            try:
                os.replace(video.path(), os.path.join(str(self.record_dir), video_name))
            except Exception:
                pass  # the recording is a bonus; never let it fail a run

"""The run story: a clean HTML report built only from a run's own data (no AI calls, nothing invented)."""
import base64
import hashlib
import html
import json
import re
from pathlib import Path

from .questions import QUESTIONS

VIEW_W, VIEW_H = 1280, 800

# Plain words for each task outcome: (chip text, colour class, phrase used in the headline).
OUTCOMES = {
    'finished_self_reported': ('AI says it finished', 'ok', 'finished, by the AI’s own account'),
    'gave_up': ('AI gave up', 'warn', 'the AI gave up'),
    'blocked_by_find': ('Not tried', 'mute', 'not tried because Find did not finish'),
    'step_limit': ('Hit the step limit', 'warn', 'hit the step limit'),
    'time_limit': ('Hit the time limit', 'warn', 'hit the time limit'),
    'budget_limit': ('Hit the call limit', 'warn', 'hit the call limit'),
    'prevented_action': ('Stopped by our safety rules', 'block', 'was stopped by our safety rules'),
    'technical_error': ('Technical error', 'bad', 'stopped with a technical error'),
    'page_unresponsive': ('Page stopped responding', 'warn', 'stopped because the page stopped responding'),
    'interrupted': ('Interrupted', 'warn', 'was interrupted'),
    'running': ('Still running', 'info', 'is still running'),
    'pending': ('Not started', 'mute', 'was not started'),
}
TASK_NAMES = {'find': 'Find', 'evaluate': 'Evaluate', 'decide': 'Decide'}
PERSONA_LABELS = {'1': 'Who they are', '2': 'What they need it for', '3': 'Total budget', '4': 'What matters most', '5': 'What makes them leave'}
STAGES = [('Discovery', 'discovery'), ('Product page', 'product_page_confidence'),
          ('Price transparency', 'price_transparency'), ('Purchase intent', 'purchase_intent')]
UNKNOWN_WORDS = re.compile(r'tax|deliver|shipping|total|return|warrant|fee|unknown|not shown|not visible|not stated|unclear|could not|couldn.t', re.I)

esc = lambda x: html.escape(str(x), quote=True)


def action_text(step):
    """The action in plain words, naming the control the AI chose."""
    action = step.get('action') or {}
    kind = action.get('kind', '')
    if not kind:
        return 'No action'
    if kind in ('click', 'type', 'select'):
        name = next((e.get('name') for e in step.get('visible_elements', []) if e.get('id') == action.get('element_id')), None)
        target = f' “{name}”' if name else f" control {action.get('element_id')}"
        typed = f" with “{action['text']}”" if kind != 'click' and action.get('text') else ''
        return kind + target + typed
    if kind == 'scroll':
        return f"scroll {action.get('direction', '')}".strip()
    return kind


def safety_check(step):
    """Whether the action was allowed, in plain words, from what the runner already recorded."""
    tags, result = step.get('tags', []), step.get('result', '')
    if 'prevented_action' in tags:
        return f'Blocked by our safety rules: {result}'
    if 'website_block' in tags:
        return 'Website access gate: stopped, nothing bypassed'
    if 'agent_execution_error' in tags:
        return f'Could not be performed ({result}). Treat this as an agent error.'
    if not step.get('action'):
        return 'No action requested'
    if 'Runner restricted' in result:
        return 'Allowed and performed. Note: a network request was restricted, so some content may be missing.'
    if result.startswith('Action executed'):
        return 'Allowed and performed'
    return 'Pending'


def parse_persona(text):
    """Name, budget and labelled fields from the persona text; falls back to the raw text."""
    found = re.findall(r'^\s*(\d)\.\s*([^:\n]{3,60}):[ \t]*(\S[^\n]*)$', text or '', re.M)
    fields = [(PERSONA_LABELS.get(n, label.strip()), value.strip()) for n, label, value in found]
    first = found[0][2] if found else (text or '')
    m = re.match(r"\s*([A-Z][\w'’-]+)", first)
    budget = re.search(r'\$\s?[\d,]+', text or '')
    return {'name': m.group(1) if m else 'the customer', 'budget': budget.group(0) if budget else '',
            'fields': fields if len(fields) >= 3 else [], 'raw': (text or '').strip()}


def clip(text, n=260):
    text = str(text or '')
    return text if len(text) <= n else text[:n].rsplit(' ', 1)[0].rstrip(',.;:') + '…'


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def page_label(url):
    path = re.sub(r'^[a-z]+://[^/]*', '', url or '').split('?')[0].strip('/')
    parts = [x for x in path.split('/') if x and not re.fullmatch(r'[a-z]{2}(-[a-z]{2})?', x)]   # skip locale segments like en-us
    stem = parts[-1].rsplit('.', 1)[0] if parts else ''
    if not stem or stem == 'index':
        return 'Home'
    return stem.replace('-', ' ').replace('_', ' ').capitalize()


def seconds_text(s):
    s = int(round(s or 0))
    return f'{s} s' if s < 60 else f'{s // 60} min {s % 60:02d} s'


def stage_score(answers, key):
    """A 1–5 value for a stage answer (yes/partly/no map to 5/3/1), or None."""
    v = (answers or {}).get(key)
    if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
        return int(v)
    return {'yes': 5, 'partly': 3, 'no': 1}.get(str(v).lower())


def tone(score):
    return 'ok' if score and score >= 4 else 'warn' if score and score == 3 else 'bad' if score else 'mute'


def site_label(run, site):
    return site['name'] if run['mode'] == 'live' else 'Fictional ' + site['local_path'].split('/')[1]


def all_steps(site):
    for task in site['tasks']:
        for attempt in task['attempts']:
            for step in attempt['steps']:
                yield task, attempt, step


def ring_of(step):
    action = step.get('action') or {}
    if action.get('kind') not in ('click', 'type', 'select'):
        return None
    el = next((e for e in step.get('visible_elements', []) if e.get('id') == action.get('element_id')), None)
    return (el['x'] / VIEW_W * 100, el['y'] / VIEW_H * 100) if el and 'x' in el else None


def task_summary(site):
    groups = []
    for t in site['tasks']:
        phrase = OUTCOMES.get(t['outcome'], (t['outcome'], 'mute', t['outcome']))[2]
        if groups and groups[-1][1] == phrase:
            groups[-1][0].append(TASK_NAMES.get(t['id'], t['id']))
        else:
            groups.append(([TASK_NAMES.get(t['id'], t['id'])], phrase))
    return '. '.join(f"{', '.join(names)}: {phrase}" for names, phrase in groups) + '.'


def pick_moments(run):
    """A few steps worth a second look, chosen by fixed rules from the data."""
    found = []
    for site in run['sites']:
        steps = [(t, s) for t, _, s in all_steps(site)]
        label = site_label(run, site)
        rules = [
            ('problem', lambda t, s: set(s.get('tags', [])) & {'agent_execution_error', 'prevented_action', 'website_block'},
             "Didn’t go as planned", 'Whose problem is this: the website, the agent, or our safety rules?'),
            ('verdict', lambda t, s: t['id'] == 'decide' and s.get('decision', {}).get('status') in ('finished', 'gave_up'),
             'The customer’s verdict', 'Do the reasons match what was actually on screen?'),
            ('unknown', lambda t, s: UNKNOWN_WORDS.search(' '.join(map(str, s.get('decision', {}).get('uncertainty', [])))),
             'Something still unknown', 'Did the AI look in the right places? Unknown things should stay marked unknown.'),
            ('price', lambda t, s: any('$' in str(e) for e in s.get('decision', {}).get('evidence', [])),
             'First price seen', 'Does the screenshot really show this price? Are tax and delivery included?'),
        ]
        for kind, test, title, ask in rules:
            used = {m['step']['id'] for m in found if m['site'] == label}
            ordered = list(reversed(steps)) if kind == 'unknown' else steps   # the AI's last doubt says more than its first
            hit = next(((t, s) for t, s in ordered if test(t, s) and s['id'] not in used), None)
            if hit:
                found.append({'kind': kind, 'title': title, 'ask': ask, 'site': label, 'task': hit[0]['id'], 'step': hit[1]})
    priority = {'problem': 0, 'verdict': 1, 'unknown': 2, 'price': 3}
    keep = sorted(found, key=lambda m: priority[m['kind']])[:6]
    return [m for m in found if m in keep]


CSS = """
:root{--ink:#24234c;--teal:#268ab0;--amber:#fff0cf;--amber-d:#d9a441;--soft:#f4f8fb;--line:#d6e1ea;--green:#2e7d4f;--green-l:#e1f3e6;--red:#c0392b;--red-l:#fde8e6;--mute:#5b6475}
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:#eef3f7;color:var(--ink);font:17px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.page{max-width:1180px;margin:0 auto;padding:26px 22px 60px}
.hero{background:linear-gradient(135deg,#24234c,#34447f);color:#fff;border-radius:22px;padding:34px 38px}
.hero h1{margin:0 0 6px;font-size:38px;line-height:1.15}
.hero .sub{margin:0;color:#cfe3ef;font-size:16px}
.banner{display:inline-block;margin-top:16px;padding:6px 14px;border-radius:999px;background:var(--amber);color:#6b4a07;font-weight:700;font-size:13px;letter-spacing:.02em}
.persona{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:22px}
.persona div{background:rgba(255,255,255,.1);border-radius:14px;padding:12px 14px;font-size:15px}
.persona b{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:#9fd3e8;margin-bottom:3px}
.persona .raw{grid-column:1/-1}
section{margin-top:36px}
.kicker{color:var(--teal);font-weight:800;font-size:13px;text-transform:uppercase;letter-spacing:.09em}
h2{font-size:26px;line-height:1.2;margin:2px 0 4px}
.lede{color:var(--mute);margin:0 0 16px;max-width:820px}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}
.tile h3{margin:0 0 2px;font-size:21px}
.tile .says{margin:6px 0 12px;color:var(--mute);font-size:15px}
.tasks{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.chip{display:inline-block;border-radius:999px;padding:3px 11px;font-size:13px;font-weight:700;border:1.5px solid;white-space:nowrap}
.ok{background:var(--green-l);border-color:var(--green);color:#1d5a37}
.warn{background:var(--amber);border-color:var(--amber-d);color:#7a5200}
.bad{background:var(--red-l);border-color:var(--red);color:#8d2418}
.block{background:#fff;border-color:var(--red);color:var(--red)}
.info{background:var(--soft);border-color:var(--teal);color:#1a6585}
.mute{background:#f1f3f5;border-color:#c9d0d8;color:var(--mute)}
.facts{display:flex;gap:18px;flex-wrap:wrap;color:var(--mute);font-size:14px}
.facts b{color:var(--ink);font-size:18px;display:block;line-height:1.2}
.shot{position:relative;width:100%;padding-top:62.5%;background:#fff var(--bg) center/100% 100% no-repeat;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.ring{position:absolute;width:7%;height:0;padding-bottom:7%;transform:translate(-50%,-50%);border:3px solid #e5484d;border-radius:50%;background:rgba(229,72,77,.16);box-shadow:0 0 0 3px rgba(255,255,255,.85)}
.strip-wrap{margin-bottom:20px}
.strip-wrap h3{margin:0 0 8px;font-size:18px}
.strip{display:flex;gap:10px;overflow-x:auto;padding:4px 2px 10px}
.stop{flex:0 0 150px;font-size:12.5px;color:var(--mute)}
.stop b{display:block;color:var(--ink);font-size:13px}
.stop .tb{height:5px;border-radius:5px;margin-bottom:6px}
.t-find{background:var(--teal)}.t-evaluate{background:var(--amber-d)}.t-decide{background:var(--green)}
.legend{font-size:13px;color:var(--mute);margin:0 0 10px}
.legend i{display:inline-block;width:18px;height:5px;border-radius:5px;margin:0 4px 2px 12px}
.score{width:100%;border-collapse:separate;border-spacing:0 10px}
.score th{text-align:left;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);padding:0 12px}
.score td{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:12px;vertical-align:top;font-size:15px}
.score td:first-child{border-left:1px solid var(--line);border-radius:14px 0 0 14px;width:20%}
.score td:last-child{border-right:1px solid var(--line);border-radius:0 14px 14px 0}
.stage b{display:block;font-size:17px}.stage span{color:var(--mute);font-size:13px}
.bar{height:9px;border-radius:9px;background:#e8eef3;margin:6px 0}.bar i{display:block;height:100%;border-radius:9px}
.bar .ok{background:var(--green)}.bar .warn{background:var(--amber-d)}.bar .bad{background:var(--red)}.bar .mute{background:#b8c1cb}
.quote{color:var(--mute);font-size:14px;margin:4px 0 0}
.weak{margin-top:6px;padding:12px 16px;background:var(--amber);border-radius:14px;color:#6b4a07;font-size:15px}
.moments{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
.moment .k{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--teal)}
.moment h3{margin:2px 0 2px;font-size:19px}
.moment .where{color:var(--mute);font-size:13px;margin-bottom:10px}
.moment blockquote{margin:10px 0 6px;padding:0 0 0 12px;border-left:4px solid var(--teal);font-size:15px}
.moment .do{font-size:14px;margin:4px 0}
.ask{margin-top:10px;padding:9px 12px;background:var(--soft);border-radius:12px;font-size:14px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:14px}
.rules{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;margin-top:8px}
.rules div{background:var(--soft);border-radius:12px;padding:10px 14px;font-size:14.5px}.rules b{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--teal);margin-bottom:3px}
.stat{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px 16px}
.stat b{font-size:28px;line-height:1.1;display:block}.stat span{color:var(--mute);font-size:14px}
ul.plain{margin:6px 0 0 20px;padding:0}ul.plain li{margin:4px 0}
details.task{background:#fff;border:1px solid var(--line);border-radius:16px;margin:0 0 12px;padding:0}
details.task>summary{cursor:pointer;padding:14px 18px;font-weight:700;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.steps{padding:0 14px 14px}
.step{display:grid;grid-template-columns:1.1fr 1.8fr 1.3fr 1.1fr;gap:14px;border-top:1px solid var(--line);padding:14px 4px}
.step h4{margin:0 0 6px;font-size:15px}.step h4 small{color:var(--mute);font-weight:400}
.part{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:var(--teal);margin-bottom:6px}
.step p{margin:5px 0;font-size:14px}
.step blockquote{margin:0 0 6px;padding-left:10px;border-left:3px solid var(--teal);font-size:14px}
.step .small{font-size:12.5px;color:var(--mute)}
.mini{display:flex;flex-wrap:wrap;gap:5px;margin:4px 0}
details.more{margin:8px 0}details.more>summary{cursor:pointer;font-size:13px;font-weight:700;color:var(--teal)}
.mini span{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:1px 8px;font-size:12px;color:var(--mute)}
.step p.verdict-ok{color:#1d5a37;font-weight:600}.step p.verdict-bad{color:var(--red);font-weight:600}
.note{padding:0 18px;color:var(--mute);font-size:13.5px}
.ended{font-size:13px;color:var(--mute)}
footer{margin-top:40px;color:var(--mute);font-size:13.5px;border-top:1px solid var(--line);padding-top:14px}
@media (max-width:900px){.step{grid-template-columns:1fr 1fr}.hero{padding:26px 22px}.hero h1{font-size:30px}}
@media print{
 body{background:#fff;font-size:11.5px}.page{max-width:none;padding:0}
 .hero{padding:22px 26px;border-radius:14px}.hero h1{font-size:28px}
 section{margin-top:22px}.card,.step,.moment,.stat,.score tr{break-inside:avoid}
 h2{break-after:avoid}.tiles{grid-template-columns:1fr 1fr}
 .strip{flex-wrap:wrap;overflow:visible}.stop{flex-basis:118px}
 .step{grid-template-columns:27% 1fr 27%;grid-template-areas:"b s a" "b c a";grid-template-rows:auto 1fr;gap:2px 12px;padding:8px 0;align-items:start;break-inside:avoid}
 .step>div:nth-child(1){grid-area:b}.step>div:nth-child(2){grid-area:s}.step>div:nth-child(3){grid-area:c}.step>div:nth-child(4){grid-area:a}
 .step blockquote{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;font-size:11px;margin:0 0 3px}
 .step details.more,.step .mini,.step .small,.step .chip,.step .fn,.step .res{display:none}.step .ended{display:block}
 .step>div:nth-child(2) .part,.step>div:nth-child(3) .part{display:none}
 .step .part{font-size:9.5px;margin:2px 0 3px}
 .moments{grid-template-columns:repeat(3,1fr);gap:10px}.moment{padding:12px}.moment h3{font-size:15px}.moment .where{font-size:10.5px;margin-bottom:6px}
 .moment blockquote{display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden;font-size:10.5px;margin:6px 0 4px}
 .moment .do,.ask{font-size:10.5px;margin:3px 0}.ask{padding:6px 8px}.step p{font-size:11px;margin:2px 0}.step h4{font-size:12px;margin:0 0 2px}
 .steps{padding:0 8px 8px}.stat b{font-size:22px}.stats{margin-bottom:8px}
 .rules{grid-template-columns:1fr 1fr}.rules div{font-size:10.5px;padding:7px 10px}
 details.task>summary{list-style:none}details.task>summary::-webkit-details-marker{display:none}
 .ring{box-shadow:none}
}
"""


class Story:
    def __init__(self, run, directory, embed):
        self.run, self.dir, self.embed = run, Path(directory), embed
        self.vars, self.names, self.by_digest = {}, {}, {}

    def var(self, rel):
        """One CSS variable per distinct picture: identical screenshots (a step's 'after' is often the next 'before') are stored once."""
        if not rel or not (self.dir / rel).is_file():
            return None
        if rel not in self.names:
            if self.embed:
                raw = (self.dir / rel).read_bytes()
                digest = hashlib.sha1(raw).hexdigest()
                if digest not in self.by_digest:
                    name = f'--s{len(self.vars)}'
                    self.vars[name] = f"url(data:image/png;base64,{base64.b64encode(raw).decode('ascii')})"
                    self.by_digest[digest] = name
                self.names[rel] = self.by_digest[digest]
            else:
                name = f'--s{len(self.vars)}'
                self.vars[name] = f'url("{rel}")'
                self.names[rel] = name
        return self.names[rel]

    def shot(self, rel, alt, ring=None):
        v = self.var(rel)
        if not v:
            return '<div class="shot" role="img" aria-label="Screenshot not available"></div>'
        dot = f'<i class="ring" style="left:{ring[0]:.2f}%;top:{ring[1]:.2f}%"></i>' if ring else ''
        return f'<div class="shot" role="img" aria-label="{esc(alt)}" style="--bg:var({v})">{dot}</div>'

    # ---- sections ------------------------------------------------------------------------------
    def hero(self, title, mode):
        p = parse_persona(self.run['track'].get('persona', ''))
        self.persona = p
        if p['fields']:
            cells = ''.join(f'<div><b>{esc(k)}</b>{esc(v)}</div>' for k, v in p['fields'])
        else:
            cells = f"<div class='raw'><b>The customer</b>{esc(p['raw'])}</div>"
        sub = f"Run {esc(self.run['id'])} · {esc(self.run['status'].replace('_', ' '))} · model {esc(self.run['model'])}"
        return (f"<header class='hero'><div class='kicker' style='color:#9fd3e8'>Research replay</div>"
                f"<h1>What happened when {esc(p['name'])} shopped</h1><p class='sub'>{esc(title)}</p><p class='sub'>{sub}</p>"
                f"<span class='banner'>{esc(mode)}</span><div class='persona'>{cells}</div></header>")

    def glance(self):
        tiles = []
        for site in self.run['sites']:
            chips = ''.join(
                f"<span class='chip {OUTCOMES.get(t['outcome'], ('', 'mute', ''))[1]}'>{esc(TASK_NAMES.get(t['id'], t['id']))}: "
                f"{esc(OUTCOMES.get(t['outcome'], (t['outcome'],))[0])}</span>" for t in site['tasks'])
            steps = list(all_steps(site))
            shots = sum(1 for _, _, s in steps for k in ('before', 'after') if s.get(k))
            intent = stage_score(site.get('answers') if (site.get('answers') or {}).get('status') == 'answered' else None, 'purchase_intent')
            verdict = f"<div><b>{intent}/5</b>buy intent</div>" if intent else ''
            tiles.append(
                f"<div class='card tile'><h3>{esc(site_label(self.run, site))}</h3><p class='says'>{esc(task_summary(site))}</p>"
                f"<div class='tasks'>{chips}</div><div class='facts'><div><b>{len(steps)}</b>steps</div>"
                f"<div><b>{seconds_text(site.get('elapsed_seconds'))}</b>time</div><div><b>{shots}</b>screenshots</div>{verdict}</div></div>")
        return ("<section><div class='kicker'>1 · The run at a glance</div><h2>What the AI says it did</h2>"
                "<p class='lede'>Completion is the AI’s own account. The evidence below is what lets us check it.</p>"
                f"<div class='tiles'>{''.join(tiles)}</div></section>")

    def journey(self):
        strips = []
        for site in self.run['sites']:
            stops = []
            for task, _, step in all_steps(site):
                if not step.get('before'):
                    continue
                stops.append(f"<a class='stop' href='#{esc(step['id'])}' style='text-decoration:none'><div class='tb t-{esc(task['id'])}'></div>"
                             f"{self.shot(step['before'], 'Screenshot at ' + step['id'], ring_of(step))}"
                             f"<b>{esc(page_label(step.get('url')))}</b>{esc(TASK_NAMES.get(task['id'], task['id']))} · {esc(action_text(step))[:34]}</a>")
            if stops:
                strips.append(f"<div class='strip-wrap'><h3>{esc(site_label(self.run, site))}</h3><div class='strip'>{''.join(stops)}</div></div>")
        legend = "<p class='legend'>Task:<i class='t-find'></i>Find<i class='t-evaluate'></i>Evaluate<i class='t-decide'></i>Decide · the red ring is the control the AI chose</p>"
        return ("<section><div class='kicker'>2 · The journey</div><h2>Where it went, page by page</h2>"
                f"<p class='lede'>Each picture is what the AI saw before it acted. Click one to jump to that step.</p>{legend}{''.join(strips)}</section>")

    def scorecard(self):
        sites = self.run['sites']
        head = ''.join(f"<th>{esc(site_label(self.run, s))}</th>" for s in sites)
        rows = []
        for stage, key in STAGES:
            cells = []
            for s in sites:
                a = s.get('answers') if (s.get('answers') or {}).get('status') == 'answered' else None
                score = stage_score(a, key)
                if not a:
                    cells.append("<td><span class='chip mute'>Not answered</span></td>")
                    continue
                shown = a[key] if not str(a[key]).isdigit() else f'{a[key]}/5'
                detail = a.get({'discovery': 'discovery_detail', 'product_page_confidence': 'product_page_missing',
                                'price_transparency': 'price_transparency_missing', 'purchase_intent': 'change_my_mind'}[key], '')
                cells.append(f"<td><span class='chip {tone(score)}'>{esc(shown)}</span><div class='bar'><i class='{tone(score)}' "
                             f"style='width:{(score or 0) * 20}%'></i></div><p class='quote'>“{esc(detail)}”</p></td>")
            why = next((q for q in QUESTIONS if q['stage'] == stage), {})
            rows.append(f"<tr><td class='stage'><b>{esc(stage)}</b><span>{esc(why.get('why_dell_cares', ''))}</span></td>{''.join(cells)}</tr>")
        weak = []
        for s in sites:
            a = s.get('answers') if (s.get('answers') or {}).get('status') == 'answered' else None
            if a:
                scored = [(stage_score(a, k), st) for st, k in STAGES if stage_score(a, k)]
                low = min(scored, key=lambda x: x[0])
                weak.append(f"{esc(site_label(self.run, s))}: weakest stage is <b>{esc(low[1])}</b> ({low[0]}/5)")
        callout = f"<div class='weak'>{' · '.join(weak)}. Where the customer was least satisfied is where Dell would most likely lose them.</div>" if weak else ''
        return ("<section><div class='kicker'>3 · Scorecard</div><h2>Scorecard: the customer’s answers by funnel stage</h2>"
                "<p class='lede'>After each store, your customer filled in a short survey. These are its own answers, so check low scores against the screenshots below.</p>"
                f"<table class='score'><tr><th>Funnel stage</th>{head}</tr>{''.join(rows)}</table>{callout}</section>")

    def moments(self):
        picks = pick_moments(self.run)
        if not picks:
            return ''
        cards = []
        for m in picks:
            step = m['step']
            d = step.get('decision', {})
            cards.append(
                f"<div class='card moment'><div class='k'>{esc(m['title'])}</div><h3>{esc(page_label(step.get('url')))}</h3>"
                f"<div class='where'>{esc(m['site'])} · {esc(TASK_NAMES.get(m['task'], m['task']))} · step {esc(step['id'])}</div>"
                f"{self.shot(step.get('before'), 'Screenshot at ' + step['id'], ring_of(step))}"
                f"<blockquote>“{esc(clip(d.get('say', '')))}”</blockquote>"
                f"<p class='do'><b>Action:</b> {esc(action_text(step))}<br><b>Safety check:</b> {esc(safety_check(step))}</p>"
                f"<div class='ask'><b>Check:</b> {esc(m['ask'])}</div></div>")
        return ("<section><div class='kicker'>4 · Moments worth checking</div><h2>A few steps to look at twice</h2>"
                "<p class='lede'>Picked by simple rules from the run (a first price, something left unknown, a problem, the final verdict). They are places to check, not findings.</p>"
                f"<div class='moments'>{''.join(cards)}</div></section>")

    def trust(self):
        steps = [(t, s) for site in self.run['sites'] for t, _, s in all_steps(site)]
        tagged = lambda tag: sum(1 for _, s in steps if tag in s.get('tags', []))
        total_tasks = sum(len(site['tasks']) for site in self.run['sites'])
        unknown = []
        for site in self.run['sites']:
            for task in site['tasks']:
                last = [s for a in task['attempts'] for s in a['steps'] if s.get('decision')]
                for u in (last[-1]['decision'].get('uncertainty', []) if last else []):
                    if str(u) not in unknown:
                        unknown.append(str(u))
        finished = sum(1 for site in self.run['sites'] for t in site['tasks'] if t['outcome'] == 'finished_self_reported')
        stat = lambda n, label: f"<div class='stat'><b>{n}</b><span>{label}</span></div>"
        listing = ''.join(f'<li>{esc(u)}</li>' for u in unknown[:6]) or '<li>Nothing recorded as unknown. Check that for yourself.</li>'
        return ("<section><div class='kicker'>5 · Check before you trust it</div><h2>What still needs a human</h2>"
                f"<div class='stats'>{stat(f'{finished} of {total_tasks}', 'tasks the AI says it finished')}{stat(len(steps), 'steps to spot-check')}"
                f"{stat(total_tasks - finished, 'tasks that did not finish')}{stat(tagged('agent_execution_error'), 'actions that failed (agent errors)')}"
                f"{stat(tagged('prevented_action') + tagged('website_block'), 'stops by our rules or a website gate')}</div>"
                f"<div class='card'><b>Still unknown at the AI’s last look</b><ul class='plain'>{listing}</ul>"
                "<p class='quote'>Completion is self-reported. A task marked finished still needs its screenshot checked, and the persona’s budget compared with the real total.</p></div>"
                + self.rules_card() + "</section>")

    def rules_card(self):
        """The rules this run played by: limits and sites come from the run's own data; the standing policy sentence is checked against browser.py."""
        run = self.run
        limits = run['track'].get('limits', {})
        steps = [s for site in run['sites'] for _, _, s in all_steps(site)]
        tagged = lambda tag: sum(1 for s in steps if tag in s.get('tags', []))
        if run['mode'] == 'local':
            where = 'Only the fictional practice stores on this computer.'
        else:
            hosts = []
            for site in run['sites']:
                if site.get('allowed_hosts'):
                    host = min(site['allowed_hosts'], key=len)
                    if host not in hosts:
                        hosts.append(host)
            where = ('Only ' + ', '.join(hosts) + '.') if hosts else 'Only the sites approved for this study.'
        cap = run.get('requested_max_steps') or limits.get('max_steps')
        minutes = round(limits['site_seconds'] / 60) if limits.get('site_seconds') else None
        parts = [x for x in (plural(cap, 'step') + ' per task' if cap else '', plural(minutes, 'minute') + ' per site' if minutes else '') if x]
        limit_text = 'Up to ' + ' and '.join(parts) if parts else 'Limits are set in the study file'
        if limits.get('max_failures'):
            limit_text += f", and a task stops after {plural(limits['max_failures'], 'failed action')} in a row"
        held = sum(len(site.get('blocked_requests') or []) for site in run['sites'])
        happened = (f"{plural(sum(1 for s in steps if s.get('action')), 'action')} checked · {tagged('prevented_action')} stopped by our safety rules · "
                    f"{tagged('website_block')} website access gates · {plural(held, 'network request')} held back by the read-only policy · "
                    f"{tagged('agent_execution_error')} failed (agent errors)")
        cell = lambda title, text: f"<div><b>{title}</b>{esc(text)}</div>"
        return ("<div class='card' style='margin-top:14px'><b>The rules this run played by</b><div class='rules'>"
                + cell('🌐 Where it could go', where)
                + cell('🚫 What it could not do', 'Add to cart, check out, sign in, pay, subscribe, download, or type personal details. Safety and execution blocks these in code.')
                + cell('⏱ Limits', limit_text + '.')
                + cell('📋 What happened this run', happened + '.') + "</div>"
                + ("<p class='quote'>Websites make many background requests. The read-only policy blocks everything except plain page loads and approved page assets, "
                   "so this number can be large without anything being wrong.</p>" if held else '') + "</div>")

    def step_card(self, task, step):
        d = step.get('decision', {})
        ring = ring_of(step)
        tags = ''.join(f"<span class='chip mute'>{esc(t)}</span>" for t in step.get('tags', []))
        facts = [re.sub(r'^Visible (text|options):\s*', '', str(e)) for e in d.get('evidence', [])]
        doubts = ''.join(f'<span>{esc(e)}</span>' for e in d.get('uncertainty', [])[:4])
        saw = (f"<details class='more'><summary>What the AI says it saw ({len(facts)})</summary><div class='mini'>"
               + ''.join(f'<span>{esc(e)}</span>' for e in facts) + "</div><p class='small'>Model-reported. Check these against the screenshot.</p></details>") if facts else ''
        after = (self.shot(step.get('after'), 'After screenshot for ' + step['id']) if step.get('after')
                 else "<p class='ended small'>No “after” screenshot: the AI stopped here and did not act.</p>")
        check = safety_check(step)
        cls = 'verdict-bad' if check.startswith(('Blocked', 'Could not', 'Website')) else 'verdict-ok'
        store = f" <small>({esc(site_label(self.run, self.site))})</small>" if self.run['mode'] == 'local' else ''
        return (
            f"<div class='step' id='{esc(step['id'])}'><div><h4>{esc(step['id'])}{store}</h4>"
            f"<div class='part'>👀 Before · Observation</div>{self.shot(step.get('before'), 'Before screenshot for ' + step['id'], ring)}"
            f"<p class='small'>{esc(step.get('url', ''))}</p></div>"
            f"<div><div class='part'>🧠 Say / Next · Decision</div><blockquote>“{esc(d.get('say', 'Pending'))}”</blockquote>"
            f"<p class='fn'><b>Feeling:</b> {esc(d.get('feeling', ''))}<br><b>Next:</b> {esc(d.get('intent', ''))}</p>"
            f"{saw}{'<p class=small>The AI says it could not confirm:</p>' if doubts else ''}<div class='mini'>{doubts}</div></div>"
            f"<div><div class='part'>🎯 Action · Action selection</div><p><b>Action:</b> {esc(action_text(step))}</p>"
            f"<div class='part'>🛡️ Safety and execution</div><p class='{cls}'><b>Safety check:</b> {esc(check)}</p>"
            f"<p class='res'><b>Result:</b> {esc(step.get('result', 'Pending'))}</p>{tags}"
            f"<p class='small'>Raw action: {esc(json.dumps(step.get('action', {})))}</p></div>"
            f"<div><div class='part'>👀 After · Observe again</div>{after}</div></div>")

    def detail(self):
        blocks = []
        for site in self.run['sites']:
            self.site = site
            for task in site['tasks']:
                chip = OUTCOMES.get(task['outcome'], (task['outcome'], 'mute', ''))
                body = []
                for attempt in task['attempts']:
                    body.append(f"<p class='note'>Attempt {attempt['number']}: {esc(OUTCOMES.get(attempt['status'], (attempt['status'].replace('_', ' '),))[0])}. {esc(attempt.get('recovery_note', ''))}</p>")
                    body += [self.step_card(task, s) for s in attempt['steps']]
                n = sum(len(a['steps']) for a in task['attempts'])
                blocks.append(
                    f"<details class='task'><summary>{esc(site_label(self.run, site))} · {esc(TASK_NAMES.get(task['id'], task['id']))} "
                    f"<span class='chip {chip[1]}'>{esc(chip[0])}</span><span class='small' style='font-weight:400'>{plural(n, 'step')} · {plural(len(task['attempts']), 'attempt')}</span></summary>"
                    f"<div class='steps'>{''.join(body)}</div></details>")
        return ("<section id='detail'><div class='kicker'>6 · Step by step</div><h2>The Step 5 view: check one complete step</h2>"
                "<p class='lede'>Every step has the same five parts. Ask one question of each: what was visible, did it make sense, was it the right control, was it allowed, what changed.</p>"
                f"{''.join(blocks)}</section>")

    def footer(self):
        u = self.run.get('usage', {})
        return (f"<footer>Run {esc(self.run['id'])} · model {esc(self.run['model'])} · {u.get('successful_calls', 0)} of {u.get('attempted_calls', 0)} AI calls succeeded · "
                f"{u.get('input_tokens', 0):,} input and {u.get('output_tokens', 0):,} output tokens. Tokens are measured only for received responses; no dollar cost is asserted. "
                "Completion is self-reported. Recovered attempts restart the interrupted task with a fresh browser. "
                "Synthetic hypotheses, not real customer data. Do not post publicly.</footer>")


def story_html(run, directory, mode, title, embed=False):
    s = Story(run, directory, embed)
    body = s.hero(title, mode) + s.glance() + s.journey() + s.scorecard() + s.moments() + s.trust() + s.detail() + s.footer()
    root = ':root{' + ''.join(f'{name}:{value};' for name, value in s.vars.items()) + '}'
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}{root}</style></head><body><div class='page'>{body}</div></body></html>")

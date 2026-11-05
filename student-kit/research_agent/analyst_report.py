"""The Analyst's report as one self-contained, printable HTML page.

Built only from `analysis.json` and the run folders (no AI call, nothing invented). Everything that came from
the model or from a website is HTML-escaped: it is study material, never markup.
"""
import base64
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .questions import QUESTIONS
from .story import (CSS, OUTCOMES, STAGES, TASK_NAMES, VIEW_H, VIEW_W, all_steps, clip, esc, page_label,
                    parse_persona, plural, ring_of, seconds_text, site_label, stage_score, tone)

ANALYST_FILE = 'analyst-report'
MONEY = re.compile(r'\$\s?[\d,]+(?:\.\d\d)?')
# Own-site calls worth naming when our read-only rules blocked them (never proof the site hides anything).
NOTABLE = re.compile(r'deliver|shipping|cart|bag|checkout|price|pricing|search|availab|inventory|stock|return|warrant|estimate|recommend', re.I)
NOISE = re.compile(r'collect|pixel|analytic|track|beacon|ping|metric|ingest|report|log\b|event|sensor|consent|identity|sst|feedback|click|/ss\w{2,}', re.I)
GLOSS = [('deliver', 'a delivery estimate'), ('shipping', 'a shipping estimate'), ('cart', 'cart information'),
         ('bag', 'bag information'), ('search', 'a product search'), ('price', 'pricing'), ('pricing', 'pricing'),
         ('recommend', 'product recommendations'), ('return', 'return information'), ('warrant', 'warranty information'),
         ('availab', 'availability'), ('stock', 'stock information'), ('inventory', 'stock information')]


# ---- data the page needs, worked out from the runs (so nothing is typed by hand) -------------------------

def load_runs(out_dir, run_ids):
    """The run.json of each run id: the output folder itself, or a sibling folder named by the id."""
    out_dir, found = Path(out_dir), []
    for rid in run_ids:
        for candidate in (out_dir, out_dir.parent / rid):
            f = candidate / 'run.json'
            if f.is_file():
                run = json.loads(f.read_text(encoding='utf-8'))
                if run.get('id') == rid:
                    found.append((run, candidate))
                    break
    return found


def _own_site(host, allowed):
    bases = {h[4:] if h.startswith('www.') else h for h in allowed}
    return any(host == b or host.endswith('.' + b) for b in bases)


def _gloss(path):
    low = path.lower()
    return next((words for key, words in GLOSS if key in low), 'a page request')


def runner_restrictions(site):
    """What our read-only rules blocked on this site, by kind. A caveat for the team, not a finding about the site."""
    blocked = site.get('blocked_requests') or []
    detailed = [b for b in blocked if 'host' in b]
    own = [b for b in detailed if _own_site(b['host'], site.get('allowed_hosts', []))]
    notable = Counter((b['host'], b['path'], b['method'], b.get('why', '')) for b in own
                      if NOTABLE.search(b['path']) and not NOISE.search(b['path']))
    return {'total': len(blocked), 'detailed': bool(detailed), 'third_party': len(detailed) - len(own),
            'own_site': len(own),
            'notable': [{'host': h, 'path': p[:90], 'method': m, 'why': w, 'count': n, 'what': _gloss(p)}
                        for (h, p, m, w), n in notable.most_common(5)]}


def enrich(data, loaded):
    """Add the deterministic fields: normalised scores, the real biggest gap, site facts, blocked requests,
    and each cited step's own screenshot (the model's guess at a screenshot is kept but not trusted)."""
    index, facts, restrictions = {}, [], {}
    for run, d in loaded:
        for site in run['sites']:
            label = site_label(run, site)
            for task, _, step in all_steps(site):
                index[step['id']] = (label, task['id'], step, d)
            tasks = [{'id': t['id'], 'outcome': t['outcome'],
                      'steps': sum(len(a['steps']) for a in t['attempts'])} for t in site['tasks']]
            find = next((t for t in site['tasks'] if t['id'] == 'find'), None)
            decide = next((t for t in site['tasks'] if t['id'] == 'decide'), None)

            def last(task):
                steps = [s for a in task['attempts'] for s in a['steps']] if task else []
                return steps[-1] if steps else None
            lf, ld = last(find), last(decide)
            say = ((lf or {}).get('decision') or {}).get('say', '')
            facts.append({'site': label, 'run': run['id'], 'mode': run['mode'], 'seconds': site.get('elapsed_seconds', 0),
                          'steps': sum(t['steps'] for t in tasks), 'tasks': tasks,
                          'selected': bool(find and find.get('product_selected')), 'find_say': say,
                          'price': (MONEY.search(say) or [''])[0] if say else '',
                          'shots': {'find': f"{d.name}/{lf['before']}" if lf and lf.get('before') else '',
                                    'decide': f"{d.name}/{ld['before']}" if ld and ld.get('before') else ''}})
            restrictions[label] = runner_restrictions(site)
    cards = data.get('scorecards', [])
    normalised = {c['site']: {stage: stage_score(c['answers'], key) for stage, key in STAGES} for c in cards}
    gap = None
    if len(cards) >= 2:
        client = next((c['site'] for c in cards if c['site'] == 'Dell'), cards[0]['site'])
        others = [c['site'] for c in cards if c['site'] != client]
        best = None
        for stage, _ in STAGES:
            mine = normalised[client].get(stage)
            theirs = [normalised[o].get(stage) for o in others if normalised[o].get(stage) is not None]
            if mine is None or not theirs:
                continue
            diff = round(mine - sum(theirs) / len(theirs), 2)
            if best is None or abs(diff) > abs(best['diff']):
                best = {'stage': stage, 'client': client, 'client_score': mine, 'others': others,
                        'other_score': round(sum(theirs) / len(theirs), 2), 'diff': diff}
        if best:
            best['favours'] = 'tie' if best['diff'] == 0 else client if best['diff'] > 0 else 'competitor'
            gap = best

    def cite(item):
        shots = []
        for sid in item.get('step_ids', []):
            if sid in index:
                label, task_id, step, d = index[sid]
                rel = f"{d.name}/{step.get('before', '')}"
                if step.get('before') and (d / step['before']).is_file():
                    shots.append({'step_id': sid, 'site': label, 'task': task_id, 'shot': rel,
                                  'say': ((step.get('decision') or {}).get('say', ''))})
        item['cited'] = shots
        if 'screenshot' in item and shots and item['screenshot'] not in {c['shot'] for c in shots}:
            # The model named a picture that is not one of the steps it cited: show the first cited step's instead.
            item['model_screenshot'] = item['screenshot']
            item['screenshot'] = shots[0]['shot']
        return item
    data['website_issues'] = [cite(i) for i in data.get('website_issues', [])]
    data['agent_errors'] = [cite(i) for i in data.get('agent_errors', [])]
    data.update({'site_facts': facts, 'normalised_scores': normalised, 'biggest_gap': gap,
                 'runner_restrictions': restrictions})
    return data


# ---- the page ------------------------------------------------------------------------------------------

EXTRA_CSS = """
.stack>*+*{margin-top:16px}
.answer{display:grid;grid-template-columns:1.5fr 1fr;gap:16px}
.answer .big{font-size:20px;line-height:1.4;margin:6px 0 0}
.answer h3{margin:0;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--teal)}
.sc-row{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px 18px;margin-bottom:12px;break-inside:avoid}
.sc-row h3{margin:0;font-size:18px}.sc-row .why{color:var(--mute);font-size:13.5px;margin:0 0 6px}
.sc-line{display:grid;grid-template-columns:120px 1fr 120px;gap:14px;align-items:center;margin:8px 0 2px}
.sc-line .nm{font-weight:700;font-size:14.5px}.sc-line .val{font-weight:700;font-size:14px;text-align:right}
.sc-line .bar{margin:0;height:14px}
.sc-q{margin:0 0 6px 134px;color:var(--mute);font-size:13.5px}
.scale{font-size:13px;color:var(--mute);margin:0 0 12px}
.gap{margin-top:8px;padding:14px 18px;background:var(--amber);border-radius:14px;color:#5e4206;font-size:15.5px}
.gap b{color:#3f2c03}.gap small{display:block;margin-top:4px;color:#7a5200}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.pair figure{margin:0}
.pair figcaption{font-size:13.5px;color:var(--mute);margin-top:7px}.pair figcaption b{color:var(--ink);display:block}
.issue{display:grid;grid-template-columns:1.2fr 1fr;gap:20px;margin-bottom:16px;break-inside:avoid}
.issue h3{margin:4px 0 6px;font-size:20px}.issue p{margin:6px 0;font-size:15.5px}
.issue .lab{font-weight:800;font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:var(--teal)}
.steps-used{margin-top:8px;color:var(--mute);font-size:13px}
.steps-used code{background:var(--soft);border:1px solid var(--line);border-radius:7px;padding:1px 7px;margin-right:4px;font-size:12px}
.cap{font-size:12.5px;color:var(--mute);margin-top:5px}
.review{margin-top:12px;padding-top:10px;border-top:1px dashed var(--line);font-size:14px}
.review .btns{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}
.review button{font:inherit;font-size:13.5px;padding:5px 12px;border-radius:999px;border:1.5px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
.review button[aria-pressed=true]{background:var(--ink);color:#fff;border-color:var(--ink)}
.review textarea{width:100%;font:inherit;font-size:14px;border:1px solid var(--line);border-radius:10px;padding:7px 10px;min-height:44px;resize:vertical}
.notdell{background:var(--soft);border:1px solid var(--line);border-radius:18px;padding:16px 20px}
.rr{margin-top:10px;padding:12px 16px;background:#fff;border:1px solid var(--line);border-radius:14px}
.rr h4{margin:0 0 4px;font-size:16px}.rr p{margin:4px 0;font-size:14.5px}
.rr ul{margin:6px 0 0 20px;padding:0;font-size:14px}
.callout{padding:12px 16px;border-radius:14px;background:var(--amber);color:#5e4206;font-size:14.5px}
.reco{background:linear-gradient(135deg,#e1f3e6,#f4f8fb);border:1px solid #b9dcc6;border-radius:18px;padding:20px 24px}
.reco p{margin:6px 0;font-size:17px}.reco .test{margin-top:12px;padding-top:12px;border-top:1px solid #b9dcc6;font-size:15.5px}
.checks{list-style:none;margin:0;padding:0}.checks li{margin:8px 0;display:flex;gap:10px;align-items:flex-start;font-size:15.5px}
.checks input{width:20px;height:20px;margin-top:2px}
.appendix{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.appendix figure{margin:0}.appendix figcaption{font-size:12.5px;color:var(--mute);margin-top:5px;word-break:break-word}
.runs{width:100%;border-collapse:collapse;font-size:13.5px}.runs td,.runs th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}
@media (max-width:820px){.answer,.pair,.issue{grid-template-columns:1fr}.sc-line{grid-template-columns:90px 1fr 90px}.sc-q{margin-left:0}}
@media print{.answer{grid-template-columns:1.4fr 1fr}.pair{grid-template-columns:1fr 1fr}.issue{grid-template-columns:1.2fr 1fr}
 .review button:not([aria-pressed=true]){display:none}.review textarea{border:none;padding:0;min-height:0}
 .appendix{grid-template-columns:repeat(3,1fr)}h2,.kicker{break-after:avoid}}
"""

JS = """
(function(){var K='analyst-review:'+document.body.getAttribute('data-key'),S={};
try{S=JSON.parse(localStorage.getItem(K)||'{}')}catch(e){}
function put(){try{localStorage.setItem(K,JSON.stringify(S))}catch(e){}}
document.querySelectorAll('[data-verdict]').forEach(function(b){var id=b.getAttribute('data-item');
 b.setAttribute('aria-pressed',S[id+':v']===b.getAttribute('data-verdict')?'true':'false');
 b.addEventListener('click',function(){S[id+':v']=b.getAttribute('data-verdict');put();
  document.querySelectorAll('[data-verdict][data-item="'+id+'"]').forEach(function(o){o.setAttribute('aria-pressed',o===b?'true':'false')})})});
document.querySelectorAll('textarea[data-note]').forEach(function(t){var id=t.getAttribute('data-note');t.value=S[id+':n']||'';
 t.addEventListener('input',function(){S[id+':n']=t.value;put()})});
document.querySelectorAll('input[data-check]').forEach(function(c){var id=c.getAttribute('data-check');c.checked=!!S[id+':c'];
 c.addEventListener('change',function(){S[id+':c']=c.checked;put()})});
})();
"""

VERDICTS = [('supported', 'The screenshot supports it'), ('partly', 'Partly supported'), ('not', 'Not supported')]
LABELS = {'site_friction': ('Hard to use', 'warn'), 'information_unavailable': ('Not shown on the page', 'info')}
CHECKS = ['Does each main claim have evidence from the correct site and step?',
          'Are unknown prices, fees, delivery details and policies still marked unknown?',
          'Are the AI’s mistakes and our own restrictions kept separate from website issues?',
          'Does the recommendation say how we could test the idea with real customers?']


class Pics:
    """Screenshots embedded once each, as CSS variables, so the page is one file that is safe to email."""

    def __init__(self, base):
        self.base, self.vars, self.names, self.by_digest = Path(base), {}, {}, {}

    def var(self, rel):
        path = self.base / rel if rel else None
        if not path or not path.is_file():
            return None
        if rel not in self.names:
            raw = path.read_bytes()
            digest = hashlib.sha1(raw).hexdigest()
            if digest not in self.by_digest:
                name = f'--p{len(self.vars)}'
                self.vars[name] = f"url(data:image/png;base64,{base64.b64encode(raw).decode('ascii')})"
                self.by_digest[digest] = name
            self.names[rel] = self.by_digest[digest]
        return self.names[rel]

    def shot(self, rel, alt, ring=None):
        v = self.var(rel)
        if not v:
            return '<div class="shot" role="img" aria-label="Screenshot not available"></div>'
        dot = f'<i class="ring" style="left:{ring[0]:.2f}%;top:{ring[1]:.2f}%"></i>' if ring else ''
        return f'<div class="shot" role="img" aria-label="{esc(alt)}" style="--bg:var({v})">{dot}</div>'


def _score_text(answers, key):
    v = (answers or {}).get(key)
    if v is None:
        return 'not answered'
    return f'{v}/5' if isinstance(v, int) else str(v)


def _detail(answers, stage):
    if not answers or answers.get('status') != 'answered':
        return ''
    return {'Discovery': answers.get('discovery_detail', ''), 'Product page': answers.get('product_page_missing', ''),
            'Price transparency': answers.get('price_transparency_missing', ''),
            'Purchase intent': answers.get('change_my_mind', '')}.get(stage, '')


def render_analyst_html(data, loaded, base):
    pics = Pics(base)
    steps_by_id = {s['id']: (run, d, s) for run, d in loaded for site in run['sites'] for _, _, s in all_steps(site)}
    scripted = data.get('analyst') == 'scripted_fixture'
    practice = any(f['mode'] != 'live' for f in data.get('site_facts', []))
    persona = parse_persona(loaded[0][0]['track'].get('persona', '')) if loaded else parse_persona('')
    cards, facts = data.get('scorecards', []), data.get('site_facts', [])
    issues, errors = data.get('website_issues', []), data.get('agent_errors', [])
    gap = data.get('biggest_gap')
    norm = data.get('normalised_scores', {})
    banner = ('SCRIPTED FIXTURE, NO AI: shape check only' if scripted else
              'AI DRAFT: your team must check every point against the screenshots')
    title = 'Practice report (fictional stores)' if practice else 'Report for Dell'
    started = (loaded[0][0].get('started_at', '')[:10] if loaded else '')

    # hero ---------------------------------------------------------------------------------------------
    cells = ''.join(f'<div><b>{esc(k)}</b>{esc(v)}</div>' for k, v in persona['fields']) or \
        f"<div class='raw'><b>The customer</b>{esc(persona['raw'])}</div>"
    hero = (f"<header class='hero'><div class='kicker' style='color:#9fd3e8'>Analyst report</div>"
            f"<h1>{esc(title)}</h1><p class='sub'>What a synthetic customer ({esc(persona['name'])}"
            f"{', ' + esc(persona['budget']) + ' budget' if persona['budget'] else ''}) found, and what we would change.</p>"
            f"<p class='sub'>{esc(started)} · {plural(len(loaded), 'run')} · {esc(data.get('analyst', ''))}</p>"
            f"<span class='banner'>{esc(banner)}</span><div class='persona'>{cells}</div></header>")

    # the answer in one screen ------------------------------------------------------------------------------
    top = issues[0] if issues else None
    gap_line = 'No comparison available (needs two sites).'
    if gap:
        who = {'tie': 'The answers tie', gap['client']: f"{gap['client']} scores higher",
               'competitor': 'The competitor scores higher'}[gap['favours']]
        gap_line = f"{esc(gap['stage'])}: {esc(who)} ({gap['client_score']:g} vs {gap['other_score']:g} out of 5)."
    tiles = ''.join(f"<div class='stat'><b>{esc(v)}</b><span>{esc(k)}</span></div>" for k, v in [
        ('sites visited', str(len(facts))), ('steps taken', str(sum(f['steps'] for f in facts))),
        ('minutes of browsing', f"{sum(f['seconds'] for f in facts) / 60:.1f}"),
        ('laptops picked', f"{sum(1 for f in facts if f['selected'])} of {len(facts)}")])
    answer = (f"<section><div class='kicker'>The answer in one screen</div><h2>What we would tell Dell</h2>"
              f"<div class='answer'><div class='card'><h3>Recommendation</h3>"
              f"<p class='big'>{esc(clip(data.get('recommendation_for_dell', ''), 420))}</p><p class='cap'>Full text in section 8.</p></div>"
              f"<div class='card'><h3>Biggest gap in the scores</h3><p>{gap_line}</p>"
              f"<h3 style='margin-top:12px'>Top issue</h3><p>{esc(top['title']) if top else 'None found in the logs.'}</p></div></div>"
              f"<div class='stats' style='margin-top:14px'>{tiles}</div></section>")

    # customer and question -----------------------------------------------------------------------------
    cust = (f"<section><div class='kicker'>1 · Who and why</div><h2>Our customer and Dell’s question</h2>"
            f"<div class='card'>{''.join('<p>' + esc(p) + '</p>' for p in data.get('customer_and_question', '').split(chr(10)) if p.strip())}</div></section>")

    # scorecard -----------------------------------------------------------------------------------------
    rows = []
    for stage, key in STAGES:
        q = next(x for x in QUESTIONS if x['stage'] == stage)
        lines = ''
        for c in cards:
            score = norm.get(c['site'], {}).get(stage)
            width = f'{(score or 0) * 20}%'
            detail = _detail(c['answers'], stage)
            lines += (f"<div class='sc-line'><span class='nm'>{esc(c['site'])}</span>"
                      f"<div class='bar' role='img' aria-label='{esc(c['site'])} {esc(stage)}: {score if score else 'no score'} out of 5'>"
                      f"<i class='{tone(score)}' style='width:{width}'></i></div>"
                      f"<span class='val'>{esc(_score_text(c['answers'], key))}</span></div>"
                      + (f"<p class='sc-q'>“{esc(clip(detail, 230))}”</p>" if detail else ''))
        rows.append(f"<div class='sc-row'><h3>{esc(stage)}</h3><p class='why'>{esc(q['why_dell_cares'])}</p>{lines}</div>")
    pick = data.get('weakest_dell_stage', 'Unclear')
    gap_box = ''
    if gap:
        agree = pick == gap['stage']
        gap_box = (f"<div class='gap'><b>Biggest gap in the numbers: {esc(gap['stage'])}.</b> "
                   f"{esc(gap['client'])} {gap['client_score']:g} vs competitor {gap['other_score']:g} out of 5."
                   f"<small>The Analyst’s own pick for Dell’s weakest stage: {esc(pick)}"
                   f"{'.' if agree else '. These differ, so check which one the evidence supports.'}</small></div>")
    elif pick != 'Unclear':
        gap_box = f"<div class='gap'><b>The Analyst’s pick for Dell’s weakest stage: {esc(pick)}.</b></div>"
    score = (f"<section><div class='kicker'>2 · The scorecard</div><h2>How the customer scored each store</h2>"
             f"<p class='lede'>The customer’s own answers after each visit: self-reported, so back every low score with a step below.</p>"
             f"<p class='scale'>Scale: yes / partly / no count as 5 / 3 / 1 on the bars. Bars: green 4–5, amber 3, red 1–2.</p>"
             f"{''.join(rows)}{gap_box}</section>")

    # journey -------------------------------------------------------------------------------------------
    tiles_j = ''
    for f in facts:
        chips = ''.join(f"<span class='chip {OUTCOMES.get(t['outcome'], ('', 'mute', ''))[1]}'>{esc(TASK_NAMES.get(t['id'], t['id']))}: "
                        f"{esc(OUTCOMES.get(t['outcome'], (t['outcome'],))[0])} · {plural(t['steps'], 'step')}</span>" for t in f['tasks'])
        says = f"“{esc(clip(f['find_say'], 240))}”" if f['find_say'] else 'The customer did not settle on a laptop.'
        tiles_j += (f"<div class='card tile'><h3>{esc(f['site'])}</h3><p class='says'>{says}</p><div class='tasks'>{chips}</div>"
                    f"<div class='facts'><span><b>{f['steps']}</b>steps</span><span><b>{esc(seconds_text(f['seconds']))}</b>browsing</span>"
                    f"<span><b>{esc(f['price'] or 'n/a')}</b>price the AI read</span></div></div>")
    journey = (f"<section><div class='kicker'>3 · The visit</div><h2>What happened at each store</h2>"
               f"<div class='tiles'>{tiles_j}</div></section>")

    # what the customer saw ---------------------------------------------------------------------------------
    figs = ''
    for which, label in (('find', 'Where the search ended'), ('decide', 'Where the decision ended')):
        pair = ''.join(f"<figure>{pics.shot(f['shots'][which], f['site'] + ': ' + label)}"
                       f"<figcaption><b>{esc(f['site'])}</b>{esc(label)}</figcaption></figure>"
                       for f in facts if f['shots'][which])
        if pair:
            figs += f"<h3 style='margin:18px 0 8px'>{esc(label)}</h3><div class='pair'>{pair}</div>"
    saw = f"<section><div class='kicker'>4 · Side by side</div><h2>What the customer saw</h2>{figs}</section>" if figs else ''

    # website issues -----------------------------------------------------------------------------------------
    def review(item_id):
        btns = ''.join(f"<button type='button' data-item='{item_id}' data-verdict='{v}' aria-pressed='false'>{esc(t)}</button>" for v, t in VERDICTS)
        return (f"<div class='review'><b>Our team’s check</b><div class='btns'>{btns}</div>"
                f"<textarea data-note='{item_id}' aria-label='Notes' placeholder='What did the screenshot show? Anything to fix?'></textarea></div>")

    def issue_card(n, d):
        label, cls = LABELS.get(d.get('label'), (d.get('label', ''), 'mute'))
        cited = d.get('cited') or []
        step = steps_by_id.get(cited[0]['step_id']) if cited else None
        ring = ring_of(step[2]) if step else None
        picture = pics.shot(d['screenshot'], f"Evidence for: {d['title']}", ring) if cited else \
            "<div class='callout'>No valid step is cited for this point. Check it or discard it.</div>"
        ids = ''.join(f'<code>{esc(c["step_id"])}</code>' for c in cited) or 'no valid step'
        bad = d.get('unverified_citations') or []
        extra = f" Ignored (not in the logs): {esc(', '.join(bad))}." if bad else ''
        note = (f"<p class='cap'>The Analyst named a screenshot that is not one of the steps it cited; this one is from the first cited step.</p>"
                if d.get('model_screenshot') else '')
        ring_note = "<p class='cap'>The red ring marks the control the AI chose at the first cited step.</p>" if ring and cited else ''
        return (f"<div class='card issue'><div><span class='chip {cls}'>{esc(label)}</span> <span class='lab'>{esc(d['site'])} · {esc(clip(d['task'], 34))}</span>"
                f"<h3>{n}. {esc(d['title'])}</h3><p><b>What happened.</b> {esc(d['what_happened'])}</p>"
                f"<p><b>Why it matters to this customer.</b> {esc(d['why_it_matters'])}</p>"
                f"<p class='steps-used'>Steps: {ids}{extra}</p>{review(f'issue{n}')}</div>"
                f"<div>{picture}{ring_note}{note}</div></div>")
    issue_html = ''.join(issue_card(n, d) for n, d in enumerate(issues, 1)) or "<div class='card'>None found in the logs.</div>"
    website = (f"<section><div class='kicker'>5 · The proof</div><h2>Website issues on dell.com</h2>"
               f"<p class='lede'>Up to three problems a real customer could hit. Open each screenshot and decide whether it supports the claim.</p>"
               f"{issue_html}</section>")
    if practice:
        website = website.replace('Website issues on dell.com', 'Issues on the practice stores')

    comp = (f"<section><div class='kicker'>6 · The comparison</div><h2>How the competitor compared</h2>"
            f"<div class='card'><p>{esc(data.get('competitor_comparison', ''))}</p></div></section>")

    # not Dell's problem ----------------------------------------------------------------------------------
    err = ''.join(f"<li><b>{esc(d['title'])}.</b> {esc(d['what_happened'])} <span class='steps-used'>"
                  f"{''.join('<code>' + esc(c['step_id']) + '</code>' for c in d.get('cited', [])) or 'no valid step'}</span></li>"
                  for d in errors) or '<li>None recorded.</li>'
    rr_html = ''
    for site, r in (data.get('runner_restrictions') or {}).items():
        if not r['total']:
            continue
        if r['detailed']:
            body = (f"<p>{r['total']} requests were blocked: {r['third_party']} to third parties (ads and tracking) and "
                    f"{r['own_site']} to the site’s own services.</p>")
            if r['notable']:
                body += '<p>Own-site calls we blocked that could affect what a page shows:</p><ul>' + ''.join(
                    f"<li>{esc(n['what'])}: <code>{esc(n['method'])} {esc(n['host'])}{esc(n['path'])}</code> × {n['count']}</li>"
                    for n in r['notable']) + '</ul>'
        else:
            body = f"<p>{r['total']} requests were blocked (this run did not record which).</p>"
        rr_html += f"<div class='rr'><h4>{esc(site)}</h4>{body}</div>"
    notdell = (f"<section><div class='kicker'>7 · Not the website’s fault</div><h2>Agent mistakes and our own rules</h2>"
               f"<div class='notdell'><h3 style='margin:0 0 6px'>Agent errors (not Dell problems)</h3><ul class='plain'>{err}</ul></div>"
               f"<div class='notdell' style='margin-top:14px'><h3 style='margin:0 0 6px'>What our safety rules blocked</h3>"
               f"<p class='callout'>Our agent can only read pages, so its rules block many background requests. If a price, delivery date or "
               f"return term is missing, it may be because one of these was blocked. Treat “not found” as a question to check, not as proof "
               f"that the site hides it.</p>{rr_html or '<p>Nothing was blocked, or the runs did not record it.</p>'}</div></section>")

    # recommendation and limits --------------------------------------------------------------------------
    reco = (f"<section><div class='kicker'>8 · What to do</div><h2>Recommendation for Dell</h2><div class='reco'>"
            f"<p>{esc(data.get('recommendation_for_dell', ''))}</p><p class='test'><b>How Dell could test it with real customers.</b> "
            f"{esc(data.get('how_to_validate', ''))}</p></div></section>")
    unknown = []
    for c in cards:
        a = c['answers']
        if a.get('status') == 'answered':
            for k in ('price_transparency_missing', 'product_page_missing'):
                if a.get(k):
                    unknown.append(f"{c['site']}: {clip(a[k], 200)}")
    limits = (f"<section><div class='kicker'>9 · Be honest</div><h2>What this study can’t tell us</h2><div class='card'>"
              f"<p><b>Limitation.</b> {esc(data.get('limitation', ''))}</p>"
              f"<p>This is a synthetic study: an AI customer’s choices suggest ideas to test, they do not show how real customers behave.</p>"
              f"{'<p><b>Still unknown, in the customer’s own words:</b></p><ul class=plain>' + ''.join('<li>' + esc(u) + '</li>' for u in unknown) + '</ul>' if unknown else ''}"
              f"</div></section>")
    checks = ''.join(f"<li><input type='checkbox' id='c{n}' data-check='c{n}'><label for='c{n}'>{esc(t)}</label></li>" for n, t in enumerate(CHECKS, 1))
    check = (f"<section><div class='kicker'>10 · Before you present</div><h2>Check it yourself</h2><div class='card'>"
             f"<ul class='checks'>{checks}</ul></div></section>")

    # appendix ------------------------------------------------------------------------------------------
    groups = {}
    for d in issues + errors:
        for c in d.get('cited', []):
            groups.setdefault(pics.var(c['shot']) or c['shot'], []).append(c)   # steps that show the same page share one picture
    figs = ''
    for cs in groups.values():
        first = cs[0]
        step = steps_by_id.get(first['step_id'])
        ids = ', '.join(dict.fromkeys(c['step_id'] for c in cs))
        figs += (f"<figure>{pics.shot(first['shot'], first['step_id'], ring_of(step[2]) if step else None)}"
                 f"<figcaption><b>{esc(ids)}</b> {esc(clip(first['say'], 150))}</figcaption></figure>")
    run_rows = ''.join(f"<tr><td>{esc(r['id'])}</td><td>{esc(r['mode'])}</td><td>{esc(r['model'])}</td>"
                       f"<td>{r['usage']['attempted_calls']} calls</td></tr>" for r, _ in loaded)
    usage = data.get('usage') or {}
    appendix = (f"<section><div class='kicker'>Evidence</div><h2>Every screenshot this report cites</h2>"
                f"<div class='appendix'>{figs or '<p>No cited screenshots.</p>'}</div>"
                f"<h3 style='margin:22px 0 6px'>The runs behind it</h3><table class='runs'><tr><th>Run</th><th>Mode</th><th>Model</th><th>Customer AI</th></tr>{run_rows}</table>"
                f"<p class='cap'>Analyst: {usage.get('attempted_calls', 0)} call(s), {usage.get('input_tokens', 0)} input and {usage.get('output_tokens', 0)} output tokens.</p></section>")

    root = ':root{' + ';'.join(f'{k}:{v}' for k, v in pics.vars.items()) + '}' if pics.vars else ''
    key = hashlib.sha1('|'.join(data.get('runs', [])).encode()).hexdigest()[:12]
    body = hero + answer + cust + score + journey + saw + website + comp + notdell + reco + limits + check + appendix
    foot = ("<footer>Synthetic hypotheses from an AI customer, not real customer data. Do not post publicly. "
            "Built only from the run folders; nothing here was typed by hand.</footer>")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{CSS}{EXTRA_CSS}{root}</style></head><body data-key='{key}'><div class='page'>{body}{foot}</div>"
            f"<script>{JS}</script></body></html>")


def write_analyst_report(out_dir, data, run_dirs=None, pdf=True):
    """Write analyst-report.html (and .pdf) next to analysis.json. Returns (html path, pdf path or None)."""
    out_dir = Path(out_dir)
    loaded = load_runs(out_dir, data.get('runs', [])) if run_dirs is None else \
        [(json.loads((Path(d) / 'run.json').read_text(encoding='utf-8')), Path(d)) for d in run_dirs]
    base = out_dir if not loaded else loaded[0][1].parent
    if 'site_facts' not in data:
        enrich(data, loaded)
    html_path = out_dir / f'{ANALYST_FILE}.html'
    html_path.write_text(render_analyst_html(data, loaded, base), encoding='utf-8')
    pdf_path = None
    if pdf:
        from .export import html_to_pdf
        pdf_path = html_to_pdf(html_path, out_dir / f'{ANALYST_FILE}.pdf')
    return html_path, pdf_path

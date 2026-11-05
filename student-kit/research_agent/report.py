"""Atomic checkpoint, the run story replay (report.html) and the findings worksheet (findings.md)."""
import json
import os
from pathlib import Path

from .questions import scorecard_rows
from .story import action_text, safety_check, story_html  # noqa: F401 (re-exported for older imports)


def atomic_json(path, data):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def run_labels(run):
    """The banner and title the replay and the findings sheet share."""
    mode = 'SCRIPTED BROWSER FIXTURE — NO AI' if run['backend'] == 'scripted_fixture' else 'OPERATOR-GUIDED BROWSER SESSION — NO API MODEL' if run['backend'] == 'operator_guided' else 'AI SYNTHETIC SESSION — HUMAN REVIEW REQUIRED'
    if run['mode'] == 'local':
        mode += ' — LOCAL FICTIONAL STORES'
    # Practice runs are not a Dell study: name them for what they are (the made-up stores), not after the track.
    title = run['track']['title'] if run['mode'] == 'live' else 'Practice run: two made-up laptop stores'
    return mode, title


def render(run, directory, embed=False):
    """Write report.html (the run story) and findings.md. embed=True makes the HTML a single self-contained file."""
    directory = Path(directory)
    mode, title = run_labels(run)
    worksheet = [f"# Findings: {title}", '', mode, '',
                 f"Run: {run['id']} | Status: {run['status']}", '',
                 '| Site | Task | Outcome | Evidence review |', '|---|---|---|---|']
    for site in run['sites']:
        label = site['name'] if run['mode'] == 'live' else 'Fictional ' + site['local_path'].split('/')[1]
        for task in site['tasks']:
            worksheet.append(f"| {label} | {task['id']} | {task['outcome']} | Pending human review |")
    worksheet += ['', '## Scorecard: the customer\'s answers by funnel stage', '',
                  'The customer answers four questions after each site. Read them as Dell\'s analyst: where in the funnel would we lose this customer?', '']
    for site in run['sites']:
        label = site['name'] if run['mode'] == 'live' else 'Fictional ' + site['local_path'].split('/')[1]
        srows = scorecard_rows(site.get('answers'))
        worksheet += [f'### {label}', '', '| Funnel stage | Customer\'s answer | Why Dell cares |', '|---|---|---|']
        worksheet += [f"| {a} | {c} | {d} |" for a, b, c, d in srows] + ['']
    worksheet += ['', '## One finding', '', '- Evidence: site, task, step ID, screenshot.',
                  '- Classification: observed website friction / agent execution error / information unavailable / synthetic preference.',
                  '- What actually happened:', '- Recommendation:', '- What a human checked:', '- Uncertainty and validation needed:', '',
                  'No purchase occurred. Synthetic preference does not predict real conversion or revenue.', '',
                  '## Measurement', '', '```json', json.dumps(run['usage'], indent=2), '```', '',
                  'Retries may incur unreported usage when a response is lost. Tokens are measured only for received responses. No dollar cost is asserted without verified rates.']
    (directory / 'report.html').write_text(story_html(run, directory, mode, title, embed), encoding='utf-8')
    (directory / 'findings.md').write_text('\n'.join(worksheet) + '\n', encoding='utf-8')

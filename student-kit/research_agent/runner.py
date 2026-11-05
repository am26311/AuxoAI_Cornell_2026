"""Run orchestration. Configuration is track-specific; browser and model logic are shared."""
import json
import os
import re
import signal
import threading
import time
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from .backend import BudgetStop, OpenAIBackend, ScriptedBackend, OperatorBackend
from .browser import BrowserSession, PageUnresponsive, Policy, PreventedAction, kill_browser_processes
from .models import Track
from .practice import serve_practice
from .questions import team_question_from
from .report import atomic_json, render

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'finished_self_reported', 'gave_up', 'step_limit', 'website_block',
            'technical_error', 'prevented_action', 'blocked_by_find', 'time_limit', 'budget_limit',
            'page_unresponsive'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def load_track(path):
    track = Track.model_validate_json(Path(path).read_text(encoding='utf-8')).model_dump()
    for group in ('sites', 'tasks'):
        ids = [item['id'] for item in track[group]]
        if len(ids) != len(set(ids)) or not ids or any(not re.fullmatch(r'[a-z][a-z0-9_-]*', i) for i in ids):
            raise ValueError(f'Invalid or duplicate {group} identifiers')
    if [t['id'] for t in track['tasks']] != ['find', 'evaluate', 'decide']:
        raise ValueError('Pilot task sequence must be find, evaluate, decide')
    if not set(track['default_sites']) <= {s['id'] for s in track['sites']}:
        raise ValueError('default_sites must name configured sites')
    for site in track['sites']:
        Policy(site['allowed_hosts'], allowed_paths=site['allowed_paths']).check_url(site['start_url'])
        for pattern in site['allowed_paths']:
            re.compile(pattern)
            if not pattern.startswith('/') or '.' in pattern:
                raise ValueError('allowed_paths must be anchored path patterns without dots')
        for entry in site['allowed_read_posts']:
            host, _, pattern = entry.partition(' ')
            re.compile(pattern)
            if not re.fullmatch(r'[a-z0-9.-]+', host) or not pattern.startswith('/') or '..' in pattern or '.*' in host:
                raise ValueError('allowed_read_posts entries must be "literal-host /anchored-path-pattern"')
        for pattern in site['allowed_asset_paths']:
            re.compile(pattern)
            if not pattern.startswith('/') or '..' in pattern:
                raise ValueError('allowed_asset_paths must be anchored path patterns')
        if not site['local_path'].startswith('/') or '..' in site['local_path']:
            raise ValueError('Invalid local practice path')
    return track


def apply_persona(track, persona_path):
    text = Path(persona_path).read_text(encoding='utf-8').strip()
    if not text:
        raise ValueError('Persona file is empty')
    if len(text) > 6000:
        raise ValueError('Persona file is too long; keep it under about one page')
    track['persona'] = text
    track['persona_source'] = Path(persona_path).name
    track['team_question'] = team_question_from(text)
    return track


def ask_questions(backend, track, site, history, directory, limits):
    """The customer answers the four funnel questions once per site, after its tasks."""
    shots = [st.get('after') or st.get('before') for t in site['tasks'] for a in t['attempts'] for st in a['steps']
             if (st.get('after') or st.get('before'))]
    shot = next((directory / sh for sh in reversed(shots) if (directory / sh).is_file()), None)
    # Its own short time budget, so a site that hit its time limit can still be asked.
    try:
        answers = backend.questionnaire(track['persona'], history, shot, track.get('team_question', ''),
                                        lambda: limits.api_timeout_seconds)
    except BudgetStop as exc:
        return {'status': 'skipped', 'reason': str(exc), 'at': stamp()}
    except (ValueError, RuntimeError) as exc:
        return {'status': 'skipped', 'reason': str(exc)[:200], 'at': stamp()}
    return {'status': 'answered', **answers.model_dump(), 'team_question': track.get('team_question', ''),
            'screenshot': str(shot.relative_to(directory)) if shot else '', 'at': stamp()}


def _resume_url(old, origin):
    return origin + urlsplit(old).path if origin else old


class Backstop:
    """If cleanup hangs (a Playwright close can wait forever), write the final status and exit.

    Without this a run can sit for hours with no status after an ordinary error."""

    def __init__(self, run, directory, lock_path):
        self.run, self.directory, self.lock_path = run, directory, lock_path
        self.cancel = threading.Event()

    def arm(self, seconds):
        self.disarm()
        self.cancel = threading.Event()
        threading.Thread(target=self._watch, args=(self.cancel, seconds), daemon=True).start()

    def disarm(self):
        self.cancel.set()

    def _watch(self, cancel, seconds):
        if cancel.wait(seconds):
            return
        if self.run.get('status') == 'running':
            self.run['status'] = 'technical_error'
        self.run.setdefault('error', 'Cleanup did not finish, so the run was ended and saved')
        self.run['cleanup_hung'] = True
        self.run['updated_at'] = stamp()
        for _ in range(3):
            try:
                atomic_json(self.directory / 'run.json', self.run)
                render(self.run, self.directory)
                break
            except Exception:
                time.sleep(0.2)
        self.lock_path.unlink(missing_ok=True)
        print(f"Cleanup hung for {seconds} s. Status saved as {self.run['status']}: {self.directory / 'report.html'}", flush=True)
        kill_browser_processes()
        os._exit(1)


def run_study(track_path, mode='local', backend_name='scripted', headed=False,
              max_steps=None, task_ids=None, site_ids=None, resume=None,
              interrupt_after=None, output_root=None, backend_factory=None, persona_path=None,
              deadline_seconds=None, cleanup_seconds=20, record_video=False):
    track = load_track(track_path)
    if persona_path:
        apply_persona(track, persona_path)
    if backend_name == 'scripted' and mode != 'local':
        raise ValueError('Scripted fixture decisions may only run on fictional local stores')
    if max_steps is not None and not 1 <= max_steps <= track['limits']['max_steps']:
        raise ValueError('Step limit must be between 1 and the configured maximum')
    if backend_name == 'openai' and not os.getenv('OPENAI_API_KEY'):
        raise ValueError('OPENAI_API_KEY is missing. Configure it locally or use local scripted mode.')
    if resume:
        directory = Path(resume).resolve()
        run = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
        if not persona_path and run['track'].get('persona_source'):
            # Resuming keeps the persona the run started with.
            for key in ('persona', 'persona_source', 'team_question'):
                if key in run['track']:
                    track[key] = run['track'][key]
        if run['track'] != track or run['mode'] != mode or run['backend'] != ({'scripted':'scripted_fixture', 'operator':'operator_guided'}.get(backend_name, backend_name)):
            raise ValueError('Resume must use the original track, environment, and backend')
        if run['status'] not in ('interrupted', 'running'):
            raise ValueError('Only an interrupted or uncleanly stopped run may resume')
        for s in run['sites']:
            for t in s['tasks']:
                if t['outcome'] == 'running':
                    t['outcome'] = 'interrupted'
                    if t['attempts']:
                        t['attempts'][-1]['status'] = 'unclean_interruption'
    else:
        selected_sites = site_ids or track['default_sites'] or [s['id'] for s in track['sites']]
        selected_tasks = task_ids or [t['id'] for t in track['tasks']]
        if not set(selected_sites) <= {s['id'] for s in track['sites']}:
            raise ValueError('Unknown site')
        if not set(selected_tasks) <= {t['id'] for t in track['tasks']} or 'find' not in selected_tasks:
            raise ValueError('Task selection must include find; unknown tasks are not allowed')
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        directory = Path(output_root or ROOT / 'outputs') / run_id
        directory.mkdir(parents=True)
        run = {'schema_version': 1, 'id': run_id, 'started_at': stamp(), 'status': 'running',
               'track': track, 'mode': mode, 'backend': {'scripted':'scripted_fixture', 'operator':'operator_guided'}.get(backend_name, backend_name),
               'model': track['model'] if backend_name == 'openai' else 'none (scripted test)' if backend_name == 'scripted' else 'none (operator-guided)',
               'requested_max_steps': max_steps or track['limits']['max_steps'],
               'usage': {'attempted_calls': 0, 'successful_calls': 0, 'failed_calls': 0,
                         'input_tokens': 0, 'output_tokens': 0, 'returned_models': []},
               'sites': [{**s, 'elapsed_seconds': 0, 'tasks': [
                   {**t, 'outcome': 'pending', 'attempts': []}
                   for t in track['tasks'] if t['id'] in selected_tasks]}
                   for s in track['sites'] if s['id'] in selected_sites]}
    (directory / 'shots').mkdir(exist_ok=True)
    # Per-project process lock. A crash leaves a lock; the caller must verify the PID
    # has exited before removing it. Never delete another process's lock automatically.
    lock_path = ROOT / '.runner.lock'
    lock = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(lock, str(os.getpid()).encode())
    os.close(lock)
    current = None
    backstop = Backstop(run, directory, lock_path)
    stop_requested = threading.Event()
    original_handlers = {}
    if backend_name != 'operator' and threading.current_thread() is threading.main_thread():
        # Defer cancellation to a durable checkpoint instead of throwing through a browser greenlet.
        for sig in (signal.SIGINT, signal.SIGTERM):
            original_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda signum, frame: stop_requested.set())

    def checkpoint():
        atomic_json(directory / 'run.json', run)
        render(run, directory)
        if stop_requested.is_set() and run['status'] == 'running':
            raise KeyboardInterrupt

    run['status'] = 'running'
    run.setdefault('resume_events', []).append({'at': stamp(), 'resuming': bool(resume)})
    checkpoint()
    print(f'Run folder: {directory}', flush=True)
    from .models import Limits
    limits = Limits.model_validate(track['limits'])
    backend = (backend_factory(run['usage'], checkpoint) if backend_factory else
               OpenAIBackend(track['model'], limits, run['usage'], checkpoint)
               if backend_name == 'openai' else OperatorBackend() if backend_name == 'operator' else ScriptedBackend())
    total_observations = 0
    try:
        local = serve_practice(ROOT / 'practice') if mode == 'local' else nullcontext(None)
        with local as origin, sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not headed)
            try:
                for site in run['sites']:
                    if all(t['outcome'] in TERMINAL for t in site['tasks']) and site.get('answers'):
                        continue
                    base_elapsed = site['elapsed_seconds']
                    begun = time.monotonic()
                    remaining = lambda: max(0, limits.site_seconds - base_elapsed - (time.monotonic() - begun))
                    session = BrowserSession(browser, Policy(site['allowed_hosts'], origin, site.get('allowed_paths', []), site.get('allowed_asset_paths', []), site.get('allowed_read_posts', [])),
                                             deadline_seconds=deadline_seconds,
                                             record_dir=directory / 'videos' if record_video else None)
                    history = []
                    for t in site['tasks']:
                        for attempt in t['attempts']:
                            for st in attempt['steps']:
                                if st.get('decision'):
                                    history.append({'task': t['id'], 'reaction': st['decision'], 'result': st.get('result', '')})
                    try:
                        for task in site['tasks']:
                            if task['outcome'] in TERMINAL:
                                continue
                            current = task
                            find = next((t for t in site['tasks'] if t['id'] == 'find'), None)
                            if task['id'] != 'find' and find and (find['outcome'] != 'finished_self_reported' or not find.get('product_selected')):
                                task['outcome'] = 'blocked_by_find'
                                checkpoint()
                                continue
                            attempt = {'number': len(task['attempts']) + 1, 'started_at': stamp(), 'status': 'running', 'steps': []}
                            if task['attempts']:
                                attempt['recovery_note'] = 'Interrupted task restarts from its saved entry URL in a fresh browser. No previous action is replayed. Earlier evidence remains unchanged.'
                            task['attempts'].append(attempt)
                            task['outcome'] = 'running'
                            checkpoint()
                            if remaining() <= 0:
                                task['outcome'] = 'time_limit'
                                attempt['status'] = 'time_limit'
                                checkpoint()
                                continue
                            if task['id'] == 'find':
                                entry = origin + site['local_path'] if origin else site['start_url']
                            else:
                                entry = task.get('entry_url') or next((t.get('end_url') for t in reversed(site['tasks'][:site['tasks'].index(task)]) if t.get('end_url')), None)
                                entry = _resume_url(entry, origin) if entry else (origin + site['local_path'] if origin else site['start_url'])
                            task['entry_url'] = entry
                            blocked = session.goto(entry) if session.page.url != entry else session.block_state()
                            if blocked:
                                shot = f"shots/{site['id']}-{task['id']}-a{attempt['number']}-blocked.png"
                                session.observe(directory / shot)
                                attempt['steps'].append({'id': f"{site['id']}-{task['id']}-a{attempt['number']}-blocked", 'before': shot, 'url': session.page.url, 'tags': ['website_block'], 'result': 'Access gate detected. No workaround attempted.'})
                                task['outcome'] = 'website_block'
                            else:
                                failures = 0
                                for progress in range(run['requested_max_steps']):
                                    if remaining() <= 0:
                                        task['outcome'] = 'time_limit'
                                        break
                                    sid = f"{site['id']}-{task['id']}-a{attempt['number']}-s{progress + 1}"
                                    step = {'id': sid, 'before': f'shots/{sid}-before.png', 'tags': [], 'phase': 'observing', 'at': stamp()}
                                    attempt['steps'].append(step)
                                    obs = session.observe(directory / step['before'])
                                    step['url'], step['visible_elements'] = obs['url'], obs['elements']
                                    step['phase'] = 'observed'
                                    checkpoint()
                                    total_observations += 1
                                    if interrupt_after and total_observations == interrupt_after:
                                        raise KeyboardInterrupt
                                    decision = backend.persona(track['persona'], {'id': task['id'], 'goal': task['goal']}, history, directory / step['before'], progress, remaining)
                                    step['decision'] = decision.model_dump()
                                    checkpoint()
                                    if decision.status != 'continue':
                                        task['outcome'] = 'finished_self_reported' if decision.status == 'finished' else 'gave_up'
                                        task['product_selected'] = bool(decision.product_selected) if task['id'] == 'find' else task.get('product_selected', False)
                                        step['tags'] = [{'openai':'synthetic_preference', 'scripted':'scripted_fixture', 'operator':'operator_guided'}[backend_name]]
                                        step['result'] = 'No action requested. Completion requires human evidence review.'
                                        step['phase'] = 'complete'
                                        checkpoint()
                                        break
                                    action = backend.hands(decision.intent, obs['elements'], directory / step['before'], remaining)
                                    step['action'] = action.model_dump()
                                    step['phase'] = 'action_planned'
                                    checkpoint()
                                    if remaining() <= 0:
                                        task['outcome'] = 'time_limit'
                                        break
                                    try:
                                        ok, result = session.execute(action)
                                        step['result'] = result
                                        failures = 0 if ok else failures + 1
                                        step['tags'] = [] if ok else ['agent_execution_error']
                                    except PreventedAction as exc:
                                        step['result'] = str(exc)
                                        step['tags'] = ['prevented_action']
                                        task['outcome'] = 'prevented_action'
                                    step['after'] = f'shots/{sid}-after.png'
                                    session.observe(directory / step['after'])
                                    step['phase'] = 'complete'
                                    history.append({'task': task['id'], 'reaction': decision.model_dump(), 'result': step['result']})
                                    site['elapsed_seconds'] = round(base_elapsed + time.monotonic() - begun, 3)
                                    checkpoint()
                                    if task['outcome'] == 'prevented_action':
                                        break
                                    if session.block_state():
                                        task['outcome'] = 'website_block'
                                        break
                                    if failures >= limits.max_failures:
                                        task['outcome'] = 'technical_error'
                                        break
                                else:
                                    task['outcome'] = 'step_limit'
                            task['end_url'] = session.page.url
                            attempt['status'] = task['outcome']
                            attempt['finished_at'] = stamp()
                            checkpoint()
                        if not site.get('answers') and hasattr(backend, 'questionnaire'):
                            site['answers'] = ask_questions(backend, track, site, history, directory, limits)
                            checkpoint()
                    except PageUnresponsive as exc:
                        # The browser was stopped by the page deadline. Record it as a runner event, not a website verdict.
                        note = f'{exc}. The runner stopped the browser. This says nothing about the website design.'
                        if current and current['outcome'] == 'running':
                            attempt = current['attempts'][-1]
                            if attempt['steps']:
                                last = attempt['steps'][-1]
                                last['result'] = (last['result'] + ' ' if last.get('result') else '') + note
                                last['tags'] = list(last.get('tags', [])) + ['page_unresponsive']
                            try:
                                current['end_url'] = session.page.url
                            except Exception:
                                pass
                            current['outcome'] = attempt['status'] = 'page_unresponsive'
                            attempt['finished_at'] = stamp()
                        site['unresponsive'] = {'task': current['id'] if current else '', 'at': stamp(), 'note': note}
                        print(f"PAGE UNRESPONSIVE on {site['name']}: {note}", flush=True)
                        if not site.get('answers') and hasattr(backend, 'questionnaire'):
                            site['answers'] = ask_questions(backend, track, site, history, directory, limits)
                        checkpoint()
                    except BudgetStop:
                        if current:
                            current['outcome'] = 'budget_limit'
                            current['attempts'][-1]['status'] = 'budget_limit'
                        run['status'] = 'budget_limit'
                        checkpoint()
                        raise
                    except Exception as exc:
                        run['error_detail'] = f'{type(exc).__name__}: {str(exc)[:300]}'
                        raise
                    finally:
                        site['elapsed_seconds'] = round(base_elapsed + time.monotonic() - begun, 3)
                        site['blocked_requests'] = site.get('blocked_requests', []) + session.blocked_requests
                        backstop.arm(cleanup_seconds)
                        session.close(video_name=f"{site['id']}.webm")
                        backstop.disarm()
                        checkpoint()
                    if session.dead:
                        # Chromium was stopped, so give the next site a fresh browser.
                        backstop.arm(cleanup_seconds)
                        try:
                            browser.close()
                        except Exception:
                            pass
                        backstop.disarm()
                        browser = pw.chromium.launch(headless=not headed)
            finally:
                backstop.arm(cleanup_seconds)  # stays armed through leaving the Playwright block below
                browser.close()
        backstop.disarm()
        run['status'] = 'finished_with_outcomes'
    except KeyboardInterrupt:
        run['status'] = 'interrupted'
        if current and current['outcome'] == 'running':
            current['outcome'] = 'interrupted'
            current['attempts'][-1]['status'] = 'interrupted'
    except BudgetStop:
        pass
    except Exception as exc:
        run['status'] = 'technical_error'
        run['error'] = f'{type(exc).__name__}: execution failed; inspect the last checkpoint and local terminal configuration'
        run.setdefault('error_detail', f'{type(exc).__name__}: {str(exc)[:300]}')
        if current and current['outcome'] == 'running':
            current['outcome'] = 'technical_error'
            current['attempts'][-1]['status'] = 'technical_error'
    finally:
        backstop.disarm()
        run['updated_at'] = stamp()
        checkpoint()
        lock_path.unlink(missing_ok=True)
        for sig, handler in original_handlers.items():
            signal.signal(sig, handler)
    print(f'Status: {run["status"]}. Replay: {directory / "report.html"}', flush=True)
    return directory, run

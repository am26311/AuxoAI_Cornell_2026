import argparse
import os
import sys
from pathlib import Path

from .runner import ROOT, run_study


def load_env(env_file):
    if env_file:
        for line in env_file.read_text().splitlines():
            k, sep, v = line.strip().partition('=')
            if sep and k == 'OPENAI_API_KEY':
                os.environ.setdefault(k, v.strip().strip('\"\''))


def analyze_main(argv):
    from .analyst import analyze_runs
    parser = argparse.ArgumentParser(prog='research_agent analyze',
                                     description='Analyst: one model call over finished runs; writes analyst-report.html (and a PDF) for Dell')
    parser.add_argument('runs', type=Path, nargs='+', help='Run folders (e.g. your Dell run and your competitor run)')
    parser.add_argument('--backend', choices=['scripted', 'openai'], default='scripted')
    parser.add_argument('--out', type=Path, help='Folder for analyst-report.html (default: first run folder)')
    parser.add_argument('--no-pdf', action='store_true', help='Only write the HTML')
    parser.add_argument('--env-file', type=Path, help='Optional local key file, never copied into reports')
    args = parser.parse_args(argv)
    load_env(args.env_file)
    try:
        path, _ = analyze_runs(args.runs, args.backend, args.out, pdf=not args.no_pdf)
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f'Report draft: {path}', flush=True)
    if not args.no_pdf:
        print(f'PDF: {path.with_suffix(".pdf")}', flush=True)
    return 0


def report_main(argv):
    import json
    from .analyst_report import write_analyst_report
    parser = argparse.ArgumentParser(prog='research_agent report',
                                     description='Rebuild analyst-report.html (and the PDF) from analysis.json after editing it (no AI calls)')
    parser.add_argument('folder', type=Path, help='The folder that holds analysis.json, e.g. outputs/RUN')
    parser.add_argument('--no-pdf', action='store_true', help='Only write the HTML')
    args = parser.parse_args(argv)
    path = args.folder / 'analysis.json'
    if not path.is_file():
        print(f'No analysis.json in {args.folder}. Run the analyze step first.', file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding='utf-8'))
    data.pop('site_facts', None)   # worked out again from the run folders, so edits to the text never go stale
    html_path, pdf_path = write_analyst_report(args.folder, data, pdf=not args.no_pdf)
    from .report import atomic_json
    atomic_json(path, data)
    print(f'Report: {html_path}', flush=True)
    if pdf_path:
        print(f'PDF: {pdf_path}', flush=True)
    return 0


def export_main(argv):
    from .export import export_run
    parser = argparse.ArgumentParser(prog='research_agent export',
                                     description='Write a clean, self-contained report-story.html and a report.pdf for a run folder (no AI calls)')
    parser.add_argument('run', type=Path, help='Run folder, e.g. outputs/20261027T152358Z-e039c629')
    parser.add_argument('--no-pdf', action='store_true', help='Only write the HTML')
    args = parser.parse_args(argv)
    try:
        html_path, pdf_path = export_run(args.run, pdf=not args.no_pdf)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f'Story report: {html_path}', flush=True)
    if pdf_path:
        print(f'PDF: {pdf_path}', flush=True)
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'analyze':
        return analyze_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == 'report':
        return report_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == 'export':
        return export_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description='Cornell customer research agent. Scripted local mode never calls an API.')
    parser.add_argument('--track', type=Path, default=ROOT / 'tracks/dell-laptops.json')
    parser.add_argument('--persona', type=Path, help='Your persona file, e.g. personas/our-persona.md')
    parser.add_argument('--mode', choices=['local', 'live'], default='local')
    parser.add_argument('--backend', choices=['scripted', 'openai', 'operator'], default='scripted')
    parser.add_argument('--headed', action='store_true', help='Show the browser window')
    parser.add_argument('--record', action='store_true', help='Also save a .webm screen recording of each site into the run folder (videos/)')
    parser.add_argument('--max-steps', type=int)
    parser.add_argument('--sites', help='Comma-separated configured site ids, e.g. dell or samsung')
    parser.add_argument('--tasks', help='Comma-separated tasks; must include find')
    parser.add_argument('--resume', type=Path, help='Run folder to recover; same track/mode/backend required')
    parser.add_argument('--interrupt-after', type=int, help='Test hook: interrupt after N observations; remove when resuming')
    parser.add_argument('--env-file', type=Path, help='Optional local key file, never copied into reports')
    args = parser.parse_args()
    load_env(args.env_file)
    try:
        _, run = run_study(args.track, args.mode, args.backend, args.headed, args.max_steps,
                           args.tasks.split(',') if args.tasks else None,
                           args.sites.split(',') if args.sites else None,
                           args.resume, args.interrupt_after, persona_path=args.persona,
                           record_video=args.record)
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0 if run['status'] == 'finished_with_outcomes' else 130 if run['status'] == 'interrupted' else 1


if __name__ == '__main__':
    raise SystemExit(main())

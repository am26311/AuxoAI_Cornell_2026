"""Export a finished run as one self-contained HTML story and a PDF. Reads only the run folder; no AI calls, no network."""
import json
from pathlib import Path

from .report import run_labels
from .story import story_html


def html_to_pdf(html_path, pdf_path):
    """Print a local HTML file to PDF with the Chromium that Playwright already installed."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1100, 'height': 900})
        page.goto(Path(html_path).resolve().as_uri())
        page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        page.pdf(path=str(pdf_path), format='Letter', print_background=True,
                 margin={'top': '12mm', 'bottom': '12mm', 'left': '10mm', 'right': '10mm'})
        browser.close()
    return Path(pdf_path)


def export_run(run_dir, pdf=True):
    """Write report-story.html (screenshots embedded, safe to email) and report.pdf next to run.json."""
    run_dir = Path(run_dir)
    if not (run_dir / 'run.json').is_file():
        raise FileNotFoundError(f'No run.json in {run_dir}. Point this at a run folder inside outputs/.')
    run = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
    mode, title = run_labels(run)
    html_path = run_dir / 'report-story.html'
    html_path.write_text(story_html(run, run_dir, mode, title, embed=True), encoding='utf-8')
    return html_path, (html_to_pdf(html_path, run_dir / 'report.pdf') if pdf else None)

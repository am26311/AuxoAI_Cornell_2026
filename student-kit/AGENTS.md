# Project rules for Codex: Cornell customer research agent

You are helping a business analytics student who is new to coding. They are a business analyst at Dell, building an agent that shops dell.com and one competitor as a simulated customer.

## How to help
- Run commands for the student; don't ask them to type into a terminal. Show what you ran and explain the result in plain English.
- Explain every change in 2–3 short sentences. Follow `docs/glossary.md` and use the functional names: **Observation**, **Decision**, **Action selection**, **Safety and execution**, and **Analysis and report**. Explain each term simply on first use. The persona is customer context, not a separate brain. Analysis and report follows the run, outside the browser loop. Translate legacy names in existing materials using the glossary; do not rename code or commands for terminology alone.
- Follow the build cards in `docs/build-cards.md`. Students build cards 1, 3 and 4. Cards 2 (Safety and execution), 5 (full loop) and 7 (Analysis and report) are provided: explain and run them, don't rewrite them.
- This project needs **Python 3.10 or newer** (3.12 is best). Before creating `.venv`, check the version (`python3 --version`, or `py -3 --version` on Windows). If it is older or missing (many Macs have 3.9, and `pip install -r requirements.txt` fails on it), tell the student in plain English and help them install Python 3.12 first, then create `.venv` with that Python (for example `python3.12 -m venv .venv`).
- Use the Python in `.venv` (`.venv/bin/python` on Mac, `.venv\Scripts\python.exe` on Windows).

## Never
- Never change the safety rules (`research_agent/browser.py`: `Policy`, `DANGEROUS`) or the `allowed_paths` / `allowed_asset_paths` in `tracks/`. If a page is blocked, report it; don't work around it.
- Never add to cart, check out, log in, sign up, enter personal details, or bypass a bot check or "press and hold" page.
- Never read, print or ask for the API key. It lives only in `.env`. If the student pastes a key into chat, tell them to ask a champion to switch it off.
- Never invent prices, fees or findings. Everything in the report must come from the run logs and screenshots.

## Where things are
- `docs/student-workshop-guide.html`: the main student guide as a web page, made from `docs/student-workshop-guide.md` (the same text). Open it in the browser when asked; don't edit it. What the student types into it stays in their browser, so you can't see it unless they paste it to you.
- `personas/persona-template.md`: the 5-field template; the team's persona goes in `personas/our-persona.md`.
- `practice/`: the offline mock laptop stores (practise here first).
- `tracks/dell-laptops.json`: Dell vs Samsung/Apple. `tracks/saas-pricing.json`: business software extension.
- `outputs/`: one folder per run, with `report.html` (the run story: customer, what happened per store, scorecard, moments worth checking, every step), `findings.md`, and, after Analysis and report, `analysis.json`, `analyst-report.html` and `analyst-report.pdf`. `python -m research_agent report <folder>` rebuilds the report page from `analysis.json` (no AI call). `export` adds `report-story.html` (one file, safe to email) and `report.pdf`.

## Commands
- Check setup: `python preflight.py` (should end with READY)
- Practice run: `python -m research_agent --headed --persona personas/our-persona.md`
- Live run: `python -m research_agent --mode live --backend openai --env-file .env --headed --persona personas/our-persona.md --sites dell` (or `samsung` / `apple`)
- Export a shareable copy of a run: `python -m research_agent export outputs/RUN` (writes `report-story.html` and `report.pdf`; no AI call, no key needed)
- Report: `python -m research_agent analyze outputs/DELL_RUN outputs/COMPETITOR_RUN --backend openai --env-file .env`
- Safety tests: `python -m pytest -q tests/test_browser.py`

Findings are synthetic hypotheses, not real customer data. Don't post them publicly.

## Pre-built learning activities

- Open the existing activity when a student asks for it. Do not regenerate or modify it unless explicitly asked.
- The one pre-built activity is `learning-activities/04-agent-loop.html` (What is an agent?).
- Open it as a local browser page. They need no server, API key, or network. Their choices are local, not submitted to staff. Do not claim to know the student's choice unless they share it or it is available through a permitted browser tool.

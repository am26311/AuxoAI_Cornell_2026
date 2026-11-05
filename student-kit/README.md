# Customer research agent: student kit

**Start here:** open `docs/student-workshop-guide.html` in your browser (double-click it, or ask Codex to open it) and follow it from the three habits through your final presentation. It's the same guide as [the text version](docs/student-workshop-guide.md), with copy buttons, a progress tracker and boxes for your answers (kept only in your browser).

You're a **business analyst at Dell**. On Nov 7 you'll build an AI agent that shops dell.com and a competitor as a customer you design, then turn what it finds into one recommendation for Dell.

**You don't type commands: ask Codex to run them.** Codex reads `AGENTS.md` for the project rules.

## Install (do this before Nov 5)

**You need Python 3.10 or newer (3.12 is best).** Many Macs come with 3.9, which is too old. Don't worry about checking: the prompt below makes Codex check first, and help you install a newer one if you need it.

Ask Codex: *"Set up this project. First check my Python version: this project needs Python 3.10 or newer (3.12 is best). If mine is older or missing, tell me in non-technical words and help me install Python 3.12 before going on. Then follow the Install section of README.md and tell me whether preflight says READY."*

If you installed a newer Python next to the old one, create the environment with it, for example `python3.12 -m venv .venv` instead of `python3 -m venv .venv`.

Mac:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python preflight.py
```
Windows (PowerShell):
```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe preflight.py
```
It should end with **READY**. That's it: you're set. If it says NOT READY, ask Codex to fix it, and tell a champion on the day if you're still stuck.

## What's in here
| Folder or file | What it is |
|---|---|
| `docs/student-workshop-guide.html` | The main guide as a web page. Open this first. `docs/student-workshop-guide.md` is the same guide as plain text |
| `docs/student-handout.md` | Your afternoon on one page: the question, the six steps, the funnel questions, the rules |
| `docs/build-cards.md` | Step-by-step prompts for Codex (you build cards 1, 3, 4) |
| `personas/persona-template.md` | Write your customer here, saved as `personas/our-persona.md` |
| `docs/report-and-presentation-template.md` | What your team hands in and presents |
| `practice/` | Two fictional laptop stores to practise on (no internet needed) |
| `research_agent/` | The agent: Observation, Decision, Action selection, Safety and execution, Analysis and report |
| `tracks/` | Study setup: Dell vs Samsung/Apple (and a business software extension) |

## Commands (for Codex to run; on Windows use `.venv\Scripts\python.exe`)
```bash
.venv/bin/python -m research_agent --headed --persona personas/our-persona.md          # practice store
.venv/bin/python -m research_agent --mode live --backend openai --env-file .env --headed --persona personas/our-persona.md --sites dell
.venv/bin/python -m research_agent analyze outputs/DELL_RUN outputs/COMPETITOR_RUN --backend openai --env-file .env
.venv/bin/python -m pytest -q tests/test_browser.py                                      # the safety tests
```

## Rules of the road
- The access key your champion gives you goes **only** in a file called `.env` (copy `.env.example`). Never paste it into Codex, a slide or a chat.
- The agent never buys, signs in or enters personal details. Safety and execution blocks it.
- **Findings are synthetic hypotheses, not real customer data. Don't post them publicly.** Dell, Samsung and Apple aren't involved, and every agent visit shows up in their website analytics.

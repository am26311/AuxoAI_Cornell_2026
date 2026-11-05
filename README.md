# AuxoAI_Cornell_2026
# Cornell MSBA Hands-On: Two Agent Options

Both options have students build an AI agent with Codex that shops laptop stores as a customer persona they write, then turn what it finds into one recommendation. They differ in how many moving parts students handle.

## 1: AI Mystery Shopper (simple)

The quick version: **brief, shop, audit.** Students write a customer brief, build a small shopper agent with four Codex prompts, and send it through two offline practice stores. The agent reads each page, reacts as the customer, decides where to click, and answers exit questions at the end. Output is a side-by-side journey page that shows the customer's mood, frustration and any blocked actions at each step.

- Runs only on the practice stores, so there's no live website risk
- No browser install: it reads page text instead of taking screenshots
- 
## 2: Student Kit (advanced)

The full research version. Students act as Dell business analysts and build an agent that shops **dell.com live** against a competitor (Samsung or Apple) using a real browser. The agent works in a loop: **Observation** (screenshot), **Decision** (reacts as the persona), **Action selection** (one click or scroll), **Safety and execution** (checks the rules, then acts). After the run, **Analysis and report** produces a scored analyst report covering four funnel stages: discovery, product page, price transparency and purchase intent.

- Students build three parts (cards 1, 3, 4); safety, the full loop and the report come pre-built
- Practice stores first, then live sites, with safety rules that block buying, sign-ins and personal details
- Includes a setup check (`preflight.py`), safety tests, a browser-based workshop guide and an export to HTML/PDF
- Best for: a deeper build, real-site findings and a richer final report

Both options produce synthetic findings, not real customer data.

# Codex build cards: Dell laptop study

**How it works (build and live-run blocks):**

| Card | Part | Who | Build or provided? | When |
|---|---|---|---|---|
| 0. A script, not an agent (optional) | Warm-up | Each student | **You build it** (a quick one, no key) | Morning |
| 1. Observation | 1. See | Each student, partner beside you | **You build it** | Build block |
| 2. Safety and execution | (before part 3) | Each student | **Provided.** Read it and run its tests; don't write it | (same block, a short read) |
| 3. Decision | 2. Decide as your customer | Each student | **You build it** | Build block |
| 4. Action selection | 3. Act once, safely | Each student | **You build it** (the milestone everyone reaches) | End of the build block |
| 5. Repeat and recover | 4. Repeat safely | Pair | **Provided** (the full Find → Evaluate → Decide loop, ending with your customer's survey) | Start of the live run |
| 6. Go live | (uses parts 1–4) | Pair, one laptop | Run the provided engine with your persona | Live run |
| 7. Analysis and report | 5. Report | Team of four | **Provided.** Run it, then edit the report | Analyse |

**The build, part by part:** parts 1 to 3 build a small agent that sees, decides as your customer, and acts once, safely. Parts 4 and 5 are the provided engine. The student guide walks through each part with the same prompts as the cards below.

**Why some cards are provided:** the safety rules (Safety and execution) never depend on code written in a hurry, and the full loop and Analysis and report fit the 2h45 block. Each student still builds an agent that sees, decides and acts (cards 1, 3, 4).

Paste each prompt into Codex and ask Codex to run it. At every card, ask Codex the "Explain" question and say the answer to a TA in your own words; that explanation is what passes the checkpoint. Stuck? Ask your partner first, then a TA. At the check-in, about halfway through the block, anyone not yet at card 3 gets the catch-up checkpoint. When the block ends, everyone moves to the live run with the provided engine, finished or not.

Names used everywhere: **Observation** (screenshot), **Decision** (persona), **Action selection** (one action), **Safety and execution** (rules and evidence), **Analysis and report** (the one-page report).

## Card 0 (optional): a script, not an agent

**Prompt:** "Write a Python Playwright script that opens the local mock laptop store (store-a), then clicks Browse laptops, View laptop details, Specs and delivery, and Returns and warranty in that order, saving a screenshot of each page. Only allow the local server. Don't use any AI. Run it on store-a, then run the same script on store-b. Explain the result in non-technical words."

**Expected result:** two sets of screenshots, one per store, taken by exactly the same steps. **Explain:** The script visited both stores the same way. What can't it tell you? **Catch-up:** none needed; skip it if the clock is tight.

## Card 1: Observation (see the page)

**Prompt:** "Create a Python Playwright script that opens the local mock laptop store and saves a 1280×800 screenshot of what's visible. Only allow the local server. Explain the folder structure. Then run it."

**Expected result:** a readable screenshot of Northwind Computers. **Explain:** What does Observation capture, and what doesn't it see? **Catch-up:** `research_agent/browser.py` (`observe`) and `practice.py`.

## Card 2: Safety and execution (provided: read it, test it)

**Prompt:** "Show me Safety and execution (the Policy) in research_agent/browser.py in plain English: which actions does it allow, and which does it refuse? Then run its safety tests with pytest and tell me what passed."

**Expected result:** the catalog link works, and every forbidden control is refused. **Explain:** Why do the rules live in code instead of in the AI's instructions? **Catch-up:** `Policy` and the guard tests in `tests/test_browser.py`.

## Card 3: Decision (react as our persona)

**Prompt:** "Read our persona from personas/our-persona.md. Send the screenshot and the persona to the model using the API key from the .env file, and ask for a structured answer: reaction, feeling, one next step, evidence, uncertainty, and whether a product is selected. Don't send hidden page code. If there's no key, stop with a clear message. Then run it once."

**Expected result:** one structured reaction, or a clear "missing key" message. **Explain:** What can Decision actually see? **Catch-up:** `backend.py` (`persona`) and `models.py`.

## Card 4: Action selection (choose one action)

**Prompt:** "Add Action selection: a second call that sees the screenshot, the customer's next step, and the list of visible elements, and returns one action. Run that action through Safety and execution and save a new screenshot. Refuse targets that changed. Run one step."

**Expected result:** a before/after screenshot pair. **This is the Required milestone.** **Explain:** Which part chooses what to do, and which part does it? **Catch-up:** the provided one-step loop in `runner.py`.

## Card 5: Repeat and recover (provided)

**Prompt:** "Run the provided engine on the mock store with our persona: python -m research_agent --headed --persona personas/our-persona.md. Explain how it repeats our one step for Find, Evaluate and Decide, when it stops, and how it saves evidence."

**Expected result:** a full run you can stop and resume without losing evidence. **Explain:** Why isn't a failed click automatically a website problem? **Catch-up:** `runner.py` and the interruption test.

## Card 6: Go live on your site (in pairs, provided engine)

**Prompt:** "Run the provided engine live on [dell / samsung / apple] with a visible browser, our persona and the real model: python -m research_agent --mode live --backend openai --env-file .env --headed --persona personas/our-persona.md --sites [dell / samsung / apple]. Then open the replay page." (Pair A: dell. Pair B: samsung for odd-numbered teams, apple for even.)

**Expected result:** three task outcomes or honest blockers, with screenshots, then your customer's answers to the four funnel questions (Discovery, Product page, Price transparency, Purchase intent) in the replay's Scorecard. **Explain:** What did the customer struggle with, and is it the site's fault or the agent's? **Catch-up:** the provided command in the README ("The real study").

## Card 7: Analysis and report (provided: run it as a team, then edit)

Pair B sends its run folder to Pair A (AirDrop or OneDrive). Then ask Codex to run the provided Analysis and report step: `python -m research_agent analyze outputs/DELL_RUN outputs/COMPETITOR_RUN --backend openai --env-file .env`. It writes `analyst-report.html` (and `analyst-report.pdf`) using the prompt below, which you can also paste into Codex yourself.

**Final analysis prompt:** "Read our two run folders: our dell.com run and our [competitor] run. Using only what the logs, screenshots and the customer's answers show, write a one-page report for Dell with these sections: (1) our customer and question; (2) scorecard: a table of the customer's answers to the four funnel questions (Discovery, Product page, Price transparency, Purchase intent) for dell.com and [competitor], plus our team question if we added one, and name Dell's weakest stage; (3) website issues on dell.com: up to 3 problems a real customer would hit, each with what happened, the step ID, the screenshot file, and why it matters to our customer; (4) how [competitor] compared on the same tasks, in 2–3 sentences; (5) agent errors: steps where our agent misread the page or clicked the wrong thing, listed separately, because these are not Dell's problems; (6) one recommendation for Dell, aimed at the weakest stage where the evidence supports it, and how Dell could test it with real customers; (7) one limitation of this study. Don't invent prices or facts that aren't in the logs. Save it as a web page called analyst-report.html."

**Expected result:** `analyst-report.html`: a visual report whose top screen is the one-page summary. Your team ticks, for every website issue, whether its screenshot supports it, moves anything the agent got wrong into "Agent errors", and edits the recommendation (ask Codex to change `analysis.json`, then run `python -m research_agent report <folder>`). **Explain:** Which issue is really Dell's, and how do you know it isn't an agent error? **Catch-up:** `python -m research_agent analyze DELL_RUN COMPETITOR_RUN` (`analyst.py`) writes the same report; `python -m research_agent report FOLDER` rebuilds it from `analysis.json` without calling the AI.

**Then present (3 minutes):** our customer → the scorecard and Dell's weakest funnel stage → the biggest website issue there (one screenshot) → our recommendation for Dell and how to test it.

**One tip:** don't rerun the full study in a loop. Ask a TA before a second full run.

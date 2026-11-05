# Your afternoon: build a customer research agent for Dell

## The question
> **"Where do our customers struggle to buy a laptop on dell.com, compared with a competitor, and what should we fix first?"**

**You** are a business analyst at Dell. **Your agent** plays a customer *you* design, shops dell.com and a competitor (Samsung for odd-numbered teams, Apple for even), and records everything it sees.

**Your path through today** is a chain of 13 small questions in four stages, starting with Dell's own question. Each one has a short answer in the guide: tick it when you can say it in your own words. Open the guide by double-clicking `docs/student-workshop-guide.html` in your kit folder.

## The six steps
1. **Problem:** Dell's question; a new laptop; New York ZIP 10001; nothing is ever bought.
2. **Persona** (12:30): each of you writes your own `our-persona.md` from the template, in 5 fields plus an optional extra question. For Dell and the competitor, your team picks one persona and everyone uses it.
3. **Build** (each of you, 12:45): build your agent in three parts with Codex on the practice store: see (card 1), decide as your customer (card 3), act once, safely (card 4, the milestone). Card 2 (Safety and execution) is provided: read it and run its tests first. The engine adds the loop and the report.
4. **Run** (pairs, 1:35): Pair A runs dell.com, Pair B runs the competitor.
5. **Analyse** (team, 2:05): run Analysis and report, check every point against its screenshot, and tick each issue in `analyst-report.html`.
6. **Present** (team, 2:30): 3 minutes.

## One agent, five functions
**Observation** (screenshot) → **Decision** (reacts as your persona) → **Action selection** (one click or scroll) → **Safety and execution** (safety rules, then act) → back to Observation. After the run, **Analysis and report** writes your report.

## The four questions your customer answers after each store
| Stage | What your customer is asked | In plain words |
|---|---|---|
| Discovery | Did you find a product that fits your needs and budget? Which one, and at what price? | Could they find something that fits? |
| Product page | How confident are you that it meets your must-haves? What was missing or unclear? | Did the page answer their questions? |
| Price transparency | Do you know the total cost, including tax and delivery, and the return terms? What couldn't you find? | Were the real costs and return terms clear? |
| Purchase intent | How likely are you to buy here rather than leave? What one thing would change your mind? | Would they buy here, and what is holding them back? |

*The persona answers as a customer; you read the answers as Dell's analyst: where in the funnel do we lose this customer, and why?*

## Website issue or agent error?
- A real person couldn't find it on that screen → **website issue** (report it, with the screenshot).
- It was there, but the agent missed it or clicked wrong → **agent error** (its own section, not Dell's fault).

## Rules of the road
- The access key your champion gives you goes **only** in `.env`. Never paste it into Codex, a slide or a chat.
- Nothing is ever bought, and nobody signs in or enters personal details. Safety and execution blocks it anyway.
- The full list of what your agent can and can't do is in the guide under **What is my agent not allowed to do?**: look but don't buy, no personal details, stop at bot checks, and limits of 12 steps per task, 10 minutes per site and 3 failed actions in a row.
- **Findings are synthetic hypotheses, not real customer data. Don't post them publicly.** Dell, Samsung and Apple aren't involved, and every agent visit shows up in their website analytics.
- Stuck? Ask your partner, then a TA. Don't rerun the full study in a loop.

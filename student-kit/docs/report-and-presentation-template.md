# Report and presentation template

The Analyst (build card 7) drafts your report as a web page: **`analyst-report.html`** in the run folder, with a PDF copy, **`analyst-report.pdf`**. Open the HTML in any browser. It is a first draft from an AI: your team checks every point against its screenshot before presenting.

## What is on the page, top to bottom

| Section on the page | What it tells you | Your check |
|---|---|---|
| **The answer in one screen** | The recommendation, the biggest gap in the scores, the top issue | Does it match what the evidence below really shows? |
| **1. Our customer and Dell's question** | Who the customer is and what Dell wants to know | Is the budget and the need right? |
| **2. The scorecard** | The customer's own answers, Dell vs the competitor, as bars | The page works out the biggest gap from the numbers. If it differs from the Analyst's pick, decide which one the evidence supports |
| **3. The visit** | What happened at each store: tasks, steps, time, the laptop and price the AI read | Were Find, Evaluate and Decide really finished? |
| **4. What the customer saw** | Dell and the competitor side by side | Do the screenshots show what the report says? |
| **5. The proof: website issues (up to 3)** | Each issue with the step IDs and the screenshot | Tick **supported / partly / not supported** and write a note |
| **6. How the competitor compared** | 2 to 3 sentences | Is it fair to both sites? |
| **7. Not the website's fault** | Agent errors, and what our own safety rules blocked | Is anything here wrongly counted as a Dell problem, or the other way round? |
| **8. Recommendation for Dell** | One change, and how to test it with real customers | Is it aimed at the weakest stage the evidence supports? |
| **9. What this study can't tell us** | The limitation and what is still unknown | Are unknowns still marked unknown? |
| **10. Check it yourself** | Four tick boxes | Tick each one only when it is true |

**If you want to change the wording:** ask Codex to edit `analysis.json` in the run folder, then run `python -m research_agent report <that folder>`. That rebuilds the page without calling the AI again. Your ticks and notes on the page are saved in your browser and print into the PDF.

**Reading "not found":** the agent can only read pages, so our safety rules block many background requests. Section 7 lists what was blocked. If a price, delivery date or return term is missing, it may be because one of those was blocked, so treat "not found" as a question to check, not proof that the site hides it.

## Presentation: 3 minutes, no slide deck needed
Present straight from the page. Scroll in this order:

1. **Our customer** (20 seconds): the top of the page: who they are and what they wanted.
2. **The scorecard** (40 seconds): section 2. Dell's weakest funnel stage, compared with the competitor.
3. **The proof** (60 seconds): section 5. The biggest website issue at that stage, with **one screenshot**.
4. **Our recommendation** (40 seconds): section 8. What Dell should change, and how they'd test it with real customers.
5. **One honest limitation** (20 seconds): section 9.

Expect one question: *"Show me the screenshot that proves it."*

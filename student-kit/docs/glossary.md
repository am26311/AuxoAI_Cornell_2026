# Workshop glossary

Use these terms consistently in explanations, prompts, and new teaching materials. Explain a term simply when first introduced. Avoid alternating between a term and several nicknames.

## The five functions

| Official name | Simple meaning | Legacy name in older materials |
|---|---|---|
| **Observation** | Capture the screen and visible controls. | Eyes |
| **Decision** | Choose the next step using the persona and observations. | Customer brain |
| **Action selection** | Match the decision to one permitted browser action. | Hands |
| **Safety and execution** | Check the rules, perform allowed actions, enforce limits, and save evidence. | Referee |
| **Analysis and report** | Use saved evidence to draft findings and a report. | Analyst |

Browser loop: **Observe → Decide → Select an action → Check and execute → Observe again**.

Analysis and report happens after the run, outside this loop. These functions belong to one system; they are not necessarily five separate agents. Existing code names and commands stay unchanged.

## Other shared terms

| Term | Simple meaning |
|---|---|
| Everyday AI | AI used for answers, ideas, or explanations; the person usually carries out the next steps. |
| Functional AI | Our workshop term for AI in a workflow that performs useful work with tools, rules, and evidence. It is not a special model category. |
| Agent | A system that uses AI to choose next steps toward a goal with tools and boundaries. |
| Persona | The customer description the agent follows. It is context, not a separate agent. |
| Task | One goal: Find, Evaluate, or Decide. |
| Study | The planned research activity, including the persona, sites, tasks, and comparison. |
| Run | One recorded attempt to carry out tasks, possibly across multiple sites. |
| Replay | A record showing what the agent saw and did. |
| Evidence | Screenshots and saved records used to check a claim. |
| Finding | An observation supported by evidence; AI customer findings are hypotheses to test with real people. |
| Agent error | A mistake in what the AI understood, selected, or did. |
| Runner restriction | A limit imposed by our program that may prevent access or an action. |
| API key | A private credential that lets the program request AI service. Keep it in the local .env file. |
| Preflight | A setup check for installed tools and browser operation; it does not test paid AI access. |

## Teaching rule

Use simple, respectful explanations. Introduce **persona** as “the customer description,” then keep saying **persona**. Use the legacy names only to help someone read older materials. Keep website problems, agent errors, and runner restrictions separate.

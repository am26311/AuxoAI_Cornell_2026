# Build a Shopper Agent (15 minutes)

You just watched our Shopper Agent run. Your job: build your own version in Codex
so it does everything ours does. You get the first prompt. The rest is up to you.

## Setup (1 minute)

1. Unzip this folder somewhere easy to find, like your Desktop.
2. Open Codex and open this folder as your project.
3. You should see `store.html`. That is a fictional laptop store your agent will shop.
   Double-click it if you want to look at it in your browser.

No API key and no installs needed.

## Prompt 1 (copy and paste this into Codex)

```
I want to build a simple shopping agent in Python. It should read the laptop
store in store.html (in this folder), ask me what laptop I need (my budget and
what it is for), and show me the laptops that fit. Use plain Python only, no
API keys and no installs. Build it, then run it with this sample answer:
"under $900 for school".
```

## Now iterate (you get 4 more prompts)

Look at what Codex built. Compare it to the checklist below. For anything that is
missing, write your own prompt asking Codex to add it. Plain English is fine.

**Our agent:**

- [ ] Asks what you need, and asks a follow-up if you leave out your budget or what it is for
- [ ] Shows only the **top 3** laptops under budget, each with a **one-line reason**
- [ ] **Asks you to pick one** (or cancel) before it orders anything
- [ ] **Places the order** and gives you a **confirmation number**
- [ ] **Blocks** anything over budget and **double-checks** the order matches your pick
- [ ] **Remembers** past orders

## Tips

- One change per prompt works better than five at once.
- If something breaks, paste the error into Codex and say "fix this."
- Codex cannot type your answers for you while the agent runs. Give it sample
  answers in your prompt (like the one in Prompt 1), or run it yourself in the terminal.
- Stuck? Raise your hand. A TA will come help.

## Done early?

Make it yours: change the store, add a new rule (for example "never pick anything over
4 lb"), or have it compare two stores.

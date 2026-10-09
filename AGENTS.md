# Repo contract — aemo-historical-prices

Read this before touching anything. It says how work in this repo is allowed to happen, for design
passes and logic/integrity passes alike: what is published, who writes what, which data shapes are
frozen, and how to prove a change works. The family conventions and shared AEMO facts below are
generated from the `agent-contracts` repo; where this file's repo-specific rules are stricter, they win.

<!-- BEGIN agent-contracts:family -->
<!-- source: family/AGENTS.family.md sha256:116b1391e2bb — edit in cutout-z/agent-contracts, not here -->
## Family conventions (every repo, every agent)

*Generated from `agent-contracts/family/AGENTS.family.md`. Edit it there, never here: a drift check
reports any local edit.* These apply to every agent (Hermes, Claude Code, Codex or any other),
whatever app drives it. Where this repo's own rules (above or below this block) are stricter, they
win. Machine-specific conventions (which checkout is which, the lane runtime, where memory lives)
are in the owner's private contract, which reaches agents through their user-level instructions
where a harness supports it.

### Branches, concurrency, cleanup

- Work in a working clone, on a branch, never in a live or serving checkout: a live checkout is what
  serves or publishes, so an edit there goes out unreviewed. Merge to `main` only if this repo's
  contract says the agent may; otherwise push the branch and hand back for review.
- Other agents may be working in this repo right now. Fetch before you act. If a branch moved
  unexpectedly, or files you didn't touch changed, stop and report rather than reconcile.
- Use a worktree for parallel work, not a second clone. The exception is a live checkout: use a
  separate clone, because adding a worktree writes into the live checkout's `.git`. At session end,
  remove the worktrees you created and leave each checkout on the branch it was on when you arrived:
  a leftover worktree pins its branch, and a checkout left on your branch changes what the next
  agent, or a server running from it, sees.
- Push every branch you want kept. An unpushed branch is one disk failure from gone.

### Instructions and automation

- **`AGENTS.md` is the only instruction file.** `CLAUDE.md`, or any other harness-specific file, holds
  just a comment line and `@AGENTS.md`. Other harnesses never read those files, so a rule or fact put
  there reaches only one agent.
- **Nothing you depend on lives only in one harness or app.** Hooks, slash commands, plugins, app
  quick actions and app-scheduled tasks may speed things up. The only copy of any automation or rule
  goes in this repo (scripts, `AGENTS.md`) or the owner's scheduler, because the harness or app may be
  swapped.
- **Name the tier, not the model.** Briefs, skills and procedures say a tier and an effort (tier 0
  mechanical, 1 routine, 2 standard, 3 hard or review, 4 vision); `agent-contracts/tiers.yaml` maps
  each tier to a model per harness. Models change often, so a name in a skill goes stale.
- **A fact other agents need goes where they load it**: this repo's `AGENTS.md` Facts, with source
  and date. If it applies across repos, propose it for the shared facts block in your handback. Your
  own memory or skills are invisible to the other agents.

### What needs the owner's yes

An explicit instruction from the owner in the current session covers that action only, not similar
later ones: the yes was for what the owner saw, not for what follows. A repo contract may record a
standing permission from the owner (e.g. "the agent merges to `main` once `check.sh` is green"). It
counts as the owner's yes only for the actions and the agents it names, only in the repo whose
contract records it, and only as that text stands on `origin/main` when you start. It never covers
adding, widening or rewording a standing permission, or any change to `AGENTS.md` or this block:
those always need the owner's yes in the current session. Without either, declare these and wait
for a yes:

- **Publishing**: anything that changes what other people can see (`main` on a published repo,
  Pages, public data files).
- **Data and ETL**: data files, pipeline code, data contracts (columns, keys, paths, schemas).
  Lanes, dashboards and other repos read them, and a change breaks them silently.
- **The instruments**: `check.sh`, guard tests, audit and verify scripts. They are how anyone,
  including you, knows a change works. Never weaken one to make something pass. If one is wrong,
  say so and leave it.
- **Infra**: ports, scheduled jobs, servers, publish pipelines. Other jobs, and the owner, rely on
  them running as they are.
- **Another agent's state**: another agent's memory, config or notes. With the owner's yes any agent
  may change them; no agent is the only writer. The owning agent can't see your edit, so commit it
  where it's visible, and edit the source rather than a generated copy.

Never read, quote or commit secrets (`.env`, auth files, keys, tokens): repos, transcripts and
handback notes get copied and published.

### Verification standard

- A change is done when you have seen the evidence yourself: tests run (exact counts, failures
  named, pre-existing failures shown to exist on `main`), and for UI, a real browser render, or a
  plain statement that it wasn't rendered and why. A reviewer can check evidence, not belief.
- For a fix, show its test fails with the fix reverted and passes with it applied; otherwise nothing
  shows the test exercises the fix.
- Don't relay another agent's or subagent's numbers. Re-run or read the evidence yourself: a relayed
  number can't be traced, and you are the one signing the handback.

### Attribution and handback

- **Every commit names its agent** in a trailer, so audits and the owner's digest can tell which agent
  made each change, whatever app drove it: `Co-Authored-By: <Agent> <model> <email>`, e.g.
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `<Agent>` is one word (`Claude`,
  `Codex`, `Hermes`, …); `<model>` is the model name without a provider prefix (e.g. `Opus 5.5`,
  `deepseek-v4.1-flash`). The email goes in angle brackets: Claude `noreply@anthropic.com`, Hermes
  `noreply@nousresearch.com` (as in existing commits), any other agent `<agent>@agents.invalid`.
  Audits match the key case-insensitively and the first word of the value.
- **Commit with the repo's configured identity.** Never set or override `user.name` or `user.email`,
  and never pass `--author`: on a public repo, author fields are published.
- **End every piece of work with a handback note.** It is the durable record; app session lists and
  an agent's memory are not, and both may be swapped. Use the repo's own path and branch convention
  if it has one; it wins, including whether notes merge. Otherwise use
  `handbacks/<YYYY-MM-DD>-<topic>.md`. On a repo whose `main` is published (a public repo, or one that
  deploys or builds a site from `main`), commit the note on its own branch, `handback/<your-branch>`:
  push it, and never merge or delete it, so the record survives the work branch's merge without
  landing on `main`. On a public repo every pushed branch is public too, so keep notes there free of
  private details. The frontmatter goes above the first line of any repo template:

  ```yaml
  ---
  project: <project name as on the owner's dashboard>
  agent: <the trailer's Agent, lowercase: claude, codex, hermes, …>
  branch: <branch>
  merged: false
  status: <one line>
  outstanding:
    - "to-do [mac-local] <item>"   # [mac-local] = only actionable on the owner's Mac
  ---
  ```

  Then cover what changed, the evidence, what's left, and any decision the brief didn't cover.
<!-- END agent-contracts:family -->

<!-- BEGIN agent-contracts:aemo-facts -->
<!-- source: facts/AEMO-FACTS.md sha256:c32c596c4a5d — edit in cutout-z/agent-contracts, not here -->
## AEMO shared facts — every agent, every repo

One canonical home for cross-repo AEMO domain facts, so a fact established in one repo is never
invisible to an agent working in another (the battery-MLF lesson, 2026-10-05: the TLF orientation
was established inside one repo's rollout doc while other agents recomputed with the wrong factor).

**Who reads this:** any agent (Hermes, Claude Code, Codex) working in an AEMO repo. It is stamped
into each AEMO repo's `AGENTS.md` between `agent-contracts:aemo-facts` markers, and the `aemo-audit`
and `aemo-logic-pass` skills point here instead of duplicating facts. A fact here overrides anything
remembered or re-derived.

**Maintenance:** append with date + source; supersede in place (`~~SUPERSEDED~~ <date> <reason>`).
Location: `agent-contracts/facts/AEMO-FACTS.md` (git, `cutout-z/agent-contracts`). Edit here only; `scripts/stamp.py` copies it into each AEMO repo's AGENTS.md.

| Fact | Detail | Verified | Source |
|---|---|---|---|
| TLF orientation | `TRANSMISSIONLOSSFACTOR` = **Import** MLF; `SECONDARY_TLF` = **Export** MLF for BIDIRECTIONAL (battery) units. A battery's export MLF comes from `SECONDARY_TLF`, never `TRANSMISSIONLOSSFACTOR`. Confirmed 51/51 differing batteries against AEMO's 2026-27 workbook. The MLF Tracker used the import factor for FY24-25/FY25-26 battery export values until fix `dbaf6f7` (2026-10-05); downstream battery revenue was restated (~−$13.1M across 26 batteries' months) after the fix. | 2026-10-05 | AEMO 2026-27 MLF workbook; `cutout-z/aemo-generator-credit-dashboard`: `audits/Logic Pass Rollout 2026-10-05.md` |
| FCAS regime | FCAS causer-pays contribution factors are DEAD — replaced by the Frequency Performance Payment (FPP) on 8 June 2025 (5-minute contribution factors on NEMWEB). Never recommend or resurrect causer-pays factor tracking; FPP cost-allocation factors per DUID are the future extension. | 2026-09-01 | AEMO/NEMWEB; `aemo-audit` skill; credit repo `docs/FUTURE_DATA_SOURCES.md` |
<!-- END agent-contracts:aemo-facts -->

## The hard rules

1. **`main` is the public site.** GitHub Pages builds from a workflow that uploads the *whole repo root*
   (`.github/workflows/deploy-pages.yml`, `path: .`; repo and Pages are public). Anything committed to
   `main` is published: no screenshots, scratch, audit evidence or half-done work there. Work on a branch.
2. **`outputs/**` belongs to the data lane.** Never hand-edit, regenerate-and-commit, or "fix" a file in
   `outputs/`. The one exception is an audited history rewrite (`python -m src.main --full-refresh`)
   that the owner has said yes to, landed as code + outputs in **one** commit (`docs/peak-window-refresh-plan.md`).
3. **Don't run the pipeline or the lane.** `python -m src.main` downloads from AEMO/RBA and rewrites
   `outputs/`; `deploy/run-update.sh` checks out `main`, may `git reset --hard origin/main`, commits and
   pushes. `deploy/**` and `.github/**` change what gets published: only with the owner's yes.
4. **Never invent data.** Every figure on the page comes from `outputs/summary.csv` / `outputs/status.json`,
   which come from AEMO and the RBA G1 table. No mock rows, no placeholder numbers.
5. **Keep the gates green.** Tests and the output validator (below). A failing gate means the change or
   the test is wrong; say which.

## Facts

| | |
|---|---|
| What it is | NEM monthly spot prices (mean and peak RRP, nominal + CPI-real) for NSW1/QLD1/VIC1/SA1/TAS1, Jul 2003 → latest complete month (README) |
| Served by | `https://cutout-z.github.io/aemo-historical-prices/`; Pages `build_type: workflow` from `main` (GitHub API, 2026-10-08) |
| Deploy trigger | push to `main` touching `outputs/**`, `index.html`, `README.md` or the workflow only (`deploy-pages.yml` `paths:`) |
| Page | `index.html` (482 lines, inline script), PapaParse 5.4.1 from jsDelivr, `assets/css/app.css` (committed, minified) |
| Shared sidebar | `index.html` loads `https://cutout-z.github.io/aemo-dashboards/nav.js` (repo `cutout-z/aemo-dashboards`, added 2026-10-10): the sidebar and phone top bar every AEMO dashboard shares. It changes there, not here, and a change there reaches this page with no PR here. It pads `body` by 232px at 1024px and wider, so check layout changes at that width. Keep the tag plain (not `defer`) at the end of `<head>` |
| CSS source | `assets/css/tailwind.src.css` (family tokens) + `tailwind.config.js` (Tailwind v3.4.17 standalone, `content: index.html, design/**`) |
| Pipeline | Python 3.11 (`monthly-update.yml`), pandas ≥ 2.0, openpyxl ≥ 3.1, requests (`requirements.txt`); `src/main.py` orchestrates |
| Data lane | NAS `ai-wif-runner` container, `nas-job aemo-historical-prices` → `deploy/run-update.sh` with `--months-back 2`, commits as `aemo-nas-bot` to `main`, writes `outputs/` only (`deploy/README.md`) |
| Lane commits | `summary.csv` changed → all `outputs/` as "Update historical price analysis YYYY-MM"; else only `status.json` as "Status check YYYY-MM-DD (no data change)" (`deploy/run-update.sh`) |
| Lane schedule | Daily (`README.md`, `deploy/README.md`). The current cron line `38 8 * * *` (08:38 AWST) is from the owner's host crontab, checked 2026-10-08, and is not in this repo. Bot commit history: data commits at 00:38 UTC (= 08:38 AWST) on the 1st of each month 2026-06 to 2026-10, then 2026-10-08; the date daily runs began is unverified (not in this repo) |
| Fallback runner | `monthly-update.yml`, manual `workflow_dispatch` only, commits as `github-actions[bot]` |
| Raw cache | `data/*.csv`, gitignored; empty on a laptop; NAS prunes after 120 days (`deploy/env.example`) |
| Theme | dark default; `localStorage` key `aemo-historical-prices:theme`; `?theme=light|dark` forces one (`index.html`) |
| Downloads | six xlsx links point at `github.com/cutout-z/aemo-historical-prices/raw/main/outputs/…` (`index.html`) |

## Data contracts (no change without the owner's yes)

- **`outputs/summary.csv`**: key `(region, year_month)`; columns `region, year_month, rrp_nominal,
  peak_rrp_nominal, total_intervals, peak_intervals, carbon_flag, cpi_estimated, rrp_real, peak_rrp_real,
  cpi_base`; booleans written `True`/`False`. 1,372 rows at `8987e57`.
- **Settled history**: outside the mutable window the guard freezes `rrp_nominal, peak_rrp_nominal,
  total_intervals, peak_intervals, carbon_flag` (`src/main.py` `_assert_settled_history_unchanged`).
  A code change that moves any of these for old months cannot merge alone (see *Pitfalls*).
- **`outputs/status.json`** keys `last_checked_utc/_awst, aemo_latest_month, cpi_latest_quarter,
  cpi_g1_publication_date, cpi_g1_last_modified_utc, sources.{aemo,rba_g1_cpi}`; the footer reads it.
- **Workbooks**: `{NSW,QLD,VIC,SA,TAS}_historical_prices.xlsx` (sheets Summary, Monthly Data, Heatmap)
  and `All_States_historical_prices.xlsx` (one sheet per region) — names pinned by the validator and the page.
- **Method decisions already taken**: peak = Mon–Fri 07:00–22:00 AEST by interval *end* stamp, public
  holidays included (audit M1, left by decision); CPI quarter-end anchoring, real = nominal for months
  past the newest quarter (README "Known limitations"); TAS starts Jun 2005; complete months only
  (exact interval counts); rolling periods 1/2/3/5/10/15/20 in workbooks, 1/3/5/10 on the page.

## Local preview and verify

```bash
cd <worktree> && python3 -m http.server 9382 --bind 127.0.0.1
# open http://127.0.0.1:9382/index.html   (needs internet for PapaParse; data is read from outputs/)
```

Port 9382 is this repo's: the design gates hard-code it (tag `design-2026-10-evidence`,
`scripts/verify-design.py`, `scripts/verify-interactions.py`). Sibling AEMO repos use 9360 (Negative Prices
preview, `AGENTS.md` on its `main`), 9370 (Renewable preview, `AGENTS.md` on its `main`), 9380 (MLF Tracker, `AGENTS.md` on its
`main` and its `design/2026-10` gates) and 9381 (Renewable gates, `scripts/verify-*.py` on its `design/2026-10`).
Negative Prices' gates on its `design/2026-10` branch also hard-code 9382, so don't run this repo's gates and
Negative Prices' gates at the same time; moving either is an instruments change that needs the owner's yes.
Reserved elsewhere, never use: 8050, 9250–9259, 9300, 9330, 9350, 9351 (unverified: not in this repo).
Pages serves the repo root, so serve the root.

```bash
python3 -m pytest -q -p no:cacheprovider tests   # baseline at 8987e57: 40 passed, 0 failed
python3 tests/validate_outputs.py                # exit 0; reads outputs/ only
python3 scripts/compare-summaries.py OLD.csv NEW.csv   # rewrite gate: only peak columns may move
```

The validator fails if `status.json` is more than 12 h old (`STATUS_MAX_AGE_HOURS`): off the lane that
is environmental, not a regression. Verify page changes in a real browser (Playwright): table rows present, KPI tiles non-empty, footer shows "Data to … · CPI … ·
last checked …", both themes, phone width.

## Pitfalls that have bitten here

- **AEMO stamps the interval END.** The peak filter was one interval off (audit H1, fixed
  `1ea371f`, history restated `23f7575`). `tests/test_peak_window.py` pins the 07:00/22:00 edges.
- **Partial months.** TAS May 2005 (741 of 1,488 intervals) was published as a month (M4). Completeness
  is an exact interval count in NEM time, never a calendar test.
- **Code and outputs must land together.** Merging a definition change without restated outputs gives
  the lane a seam in the series or trips the settled-history guard and wedges it
  (`docs/peak-window-refresh-plan.md`).
- **`main` moves under you.** The lane commits on its own schedule and resets its clone onto
  `origin/main` if it cannot fast-forward (`d1bc992`). Expect your branch to be behind; never rewrite `main`.
- **CSS-only commits do not deploy.** `assets/**` and `tailwind.config.js` are not in the Pages
  `paths:` filter; a page change must ship `index.html` and `assets/css/app.css` together.
- **The CSS build and design gates are not on `main`.** `scripts/build-css.sh`, `verify-design.py` and
  `verify-interactions.py` exist only on tag `design-2026-10-evidence` (a `.gitignore` comment
  refers to `build-css.sh`). Restore them on your branch if you need them; whether they pass on current `main` is unverified.

## Working alongside other agents

The other writer to `main` is `aemo-nas-bot` (the lane). Hermes watches the lane (the `aemo-audit`
skill; unverified: not in this repo). A logic pass is read-only on the pipeline. Its findings note
follows the format of `docs/logic-pass-2026-10-05.md` (filed on `main` before this rule; new notes don't
go there) and goes on `handback/<pass-branch>` per the family block, never on `main` (rule 1). Fixes go
on their own branch; merges to `main` have been the owner's (git log).

## Handback checklist

- [ ] Nothing committed to `main`; `git diff --stat origin/main` shows no `outputs/**`, `deploy/**`,
      `.github/**` (unless the owner said yes to that exact change).
- [ ] `pytest` counts stated (baseline 40 passed) and `tests/validate_outputs.py` exit code stated.
- [ ] Page changes: browser-verified at desktop and phone, both themes; `app.css` rebuilt and committed.
- [ ] Logic changes: which published columns would move, by how much, and whether an audited rewrite is needed.
- [ ] No design evidence or scratch files anywhere Pages would publish them.

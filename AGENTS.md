# Repo contract — aemo-historical-prices

Read this before touching anything. It says how work in this repo is allowed to happen, for design
passes and logic/integrity passes alike: what is published, who writes what, which data shapes are
frozen, and how to prove a change works. The family conventions and shared AEMO facts below are
generated from the `agent-contracts` repo; where this file's repo-specific rules are stricter, they win.

<!-- BEGIN agent-contracts:family -->
<!-- source: family/AGENTS.family.md sha256:f43f0fc253a7 — edit in cutout-z/agent-contracts, not here -->
## Family conventions (every repo, every agent)

*Generated from `agent-contracts/family/AGENTS.family.md`. Edit it there, never here: a drift check
reports any local edit.* These apply to every agent (Hermes, Claude Code, Codex or any other),
whatever app drives it. Where this repo's own rules (above or below this block) are stricter, they
win. Machine-specific conventions (which checkout is which, the lane runtime, where memory lives)
are in the owner's private contract, which each harness loads separately.

### Branches, concurrency, cleanup

- Work in a working clone, on a branch, never in a live or serving checkout. Merge to `main` only if
  this repo's contract says the agent may; otherwise push the branch and hand back for review.
- Other agents may be working in this repo right now. Fetch before you act. If a branch moved
  unexpectedly, or files you didn't touch changed, stop and report rather than reconcile.
- Use a worktree for parallel work, not a second clone. At session end, remove the worktrees you
  created and leave each checkout on the branch it was on when you arrived.
- Push every branch you want kept. An unpushed branch is one disk failure from gone.

### What needs the owner's yes

An explicit instruction from the owner in the current session covers that action only, not similar
later ones. Without one, declare these and wait for a yes:

- **Publishing**: anything that changes what other people can see (`main` on a published repo,
  Pages, public data files).
- **Data and ETL**: data files, pipeline code, data contracts (columns, keys, paths, schemas).
- **The instruments**: `check.sh`, guard tests, audit and verify scripts. Never weaken one to make
  something pass. If one is wrong, say so and leave it.
- **Infra**: ports, scheduled jobs, servers, publish pipelines.
- **Another agent's state**: another agent's memory, config or notes.

Never read, quote or commit secrets: `.env`, auth files, keys, tokens.

### Verification standard

- A change is done when you have seen the evidence yourself: tests run (exact counts, failures
  named, pre-existing failures shown to exist on `main`), and for UI, a real browser render.
- For a fix, show its test fails with the fix reverted and passes with it applied.
- Don't relay another agent's or subagent's numbers. Re-run or read the evidence yourself.

### Attribution and handback

- **Every commit names its agent** in a trailer: `Co-Authored-By: <Agent> <model> <email>`, e.g.
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, `Co-Authored-By: Codex …`,
  `Co-Authored-By: Hermes …`. Audits match on the `Co-Authored-By: <Agent>` prefix.
- **End every piece of work with a handback note on the branch**, using the repo's own path
  convention, or `docs/handback-<YYYY-MM-DD>-<topic>.md` if it has none. On a repo whose `main` is
  published, keep notes and evidence on the branch; they don't merge. Start the note with:

  ```yaml
  ---
  project: <project name as on the owner's board>
  agent: claude | codex | hermes
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
<!-- source: facts/AEMO-FACTS.md sha256:c6c3cdf689bd — edit in cutout-z/agent-contracts, not here -->
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
| TLF orientation | `TRANSMISSIONLOSSFACTOR` = **Import** MLF; `SECONDARY_TLF` = **Export** MLF for BIDIRECTIONAL (battery) units. A battery's export MLF comes from `SECONDARY_TLF`, never `TRANSMISSIONLOSSFACTOR`. Confirmed 51/51 differing batteries against AEMO's 2026-27 workbook. The MLF Tracker used the import factor for FY24-25/FY25-26 battery export values until fix `dbaf6f7` (2026-10-05); downstream battery revenue was restated (~−$13.1M across 26 batteries' months) after the fix. | 2026-10-05 | AEMO 2026-27 MLF workbook; `aemo-credit-design/audits/Logic Pass Rollout 2026-10-05.md` |
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
| CSS source | `assets/css/tailwind.src.css` (family tokens) + `tailwind.config.js` (Tailwind v3.4.17 standalone, `content: index.html, design/**`) |
| Pipeline | Python 3.11 (`monthly-update.yml`), pandas ≥ 2.0, openpyxl ≥ 3.1, requests (`requirements.txt`); `src/main.py` orchestrates |
| Data lane | NAS `ai-wif-runner` container, `nas-job aemo-historical-prices` → `deploy/run-update.sh` with `--months-back 2`, commits as `aemo-nas-bot` to `main`, writes `outputs/` only (`deploy/README.md`) |
| Lane commits | `summary.csv` changed → all `outputs/` as "Update historical price analysis YYYY-MM"; else only `status.json` as "Status check YYYY-MM-DD (no data change)" (`deploy/run-update.sh`) |
| Lane schedule | Daily at 08:38 AWST (NAS crontab `38 8 * * *`, checked 2026-10-08). Daily since 2026-10-07; before that, monthly on the 1st |
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

Port 9382 is the one the 2026-10 design gates used (`scripts/verify-design.py` on tag
`design-2026-10-evidence`); siblings use 9360/9370/9380 (private design-pass notes). Pages serves the repo root, so serve the root.

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
  `verify-interactions.py` exist only on tag `design-2026-10-evidence` (`.gitignore` still names
  `build-css.sh`). Restore them on your branch if you need them; whether they pass on current `main` is unverified.

## Working alongside other agents

The other writer to `main` is `aemo-nas-bot` (the lane). Hermes watches the lane
(`brain-ops-nas workflow aemo-historical-prices`, the `aemo-audit` skill). A logic
pass is read-only on the pipeline and files findings under `docs/` (format: `docs/logic-pass-2026-10-05.md`;
the `aemo-logic-pass` skill). Fixes go on their own branch; merges to `main` have been the owner's (git log).

## Handback checklist

- [ ] Nothing committed to `main`; `git diff --stat origin/main` shows no `outputs/**`, `deploy/**`,
      `.github/**` (unless the owner said yes to that exact change).
- [ ] `pytest` counts stated (baseline 40 passed) and `tests/validate_outputs.py` exit code stated.
- [ ] Page changes: browser-verified at desktop and phone, both themes; `app.css` rebuilt and committed.
- [ ] Logic changes: which published columns would move, by how much, and whether an audited rewrite is needed.
- [ ] No design evidence or scratch files anywhere Pages would publish them.

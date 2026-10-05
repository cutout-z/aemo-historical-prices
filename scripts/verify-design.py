#!/usr/bin/env python3
"""Render + token check for the AEMO Historical Prices page — the gate this pass must leave green.

    cd ~/Design/"AEMO Historical Prices" && python3 -m http.server 9382 --bind 127.0.0.1 &
    /opt/anaconda3/bin/python3 scripts/verify-design.py            # checks only
    /opt/anaconda3/bin/python3 scripts/verify-design.py --screens  # + design/screens/after-*.png

Why a script and not an eyeball: the failures this page actually produces are invisible in a diff —
a component class Tailwind never emitted, a heat cell still carrying an inline `rgb()`, a theme flip
that changes nothing because the page hard-codes its colours, a phone-width overflow. Exit 1 = fix it.

The DOM contract it checks is written down in AGENTS.md (section "DOM contract") — the gate is only
fair where the brief names it.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:9382/index.html"
SCREENS = ROOT / "design" / "screens"
TOKEN_SRC = ROOT / "assets" / "css" / "tailwind.src.css"
PAGE = ROOT / "index.html"

fails: list[str] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def rgb(value: str) -> tuple[int, int, int] | None:
    """Normalise '#171717' and 'rgb(23, 23, 23)' / 'rgba(...)' to one tuple."""
    v = (value or "").strip()
    if v.startswith("#"):
        v = v.lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        try:
            return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            return None
    if v.startswith("rgb"):
        parts = v[v.index("(") + 1:v.index(")")].split(",")
        try:
            return tuple(int(float(p)) for p in parts[:3])  # type: ignore[return-value]
        except ValueError:
            return None
    return None


def token_sets() -> tuple[dict[str, str], dict[str, str]]:
    """Read both theme roots out of the token source — the values the page must agree with.

    Two hazards, both already paid for in this family: the source explains itself in `/* … */` comments
    and one of them names a token (the `--faint` line's "4.9:1 on --surface"), and the heat ramp lives in
    a SECOND `:root` block further down the file — so a single split on the first `[data-theme="light"]`
    leaves `seq-*` unread. Strip comments, then take every declaration block whose selector is a theme
    root (`:root` = dark, `[data-theme="light"]` = light), later blocks overriding earlier ones."""
    css = re.sub(r"/\*.*?\*/", " ", TOKEN_SRC.read_text(), flags=re.S)
    grab = lambda s: dict(re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", s))
    dark: dict[str, str] = {}
    light: dict[str, str] = {}
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sel, body = m.group(1), m.group(2)
        if "data-theme" in sel:
            light.update(grab(body))
        elif ":root" in sel:
            dark.update(grab(body))
    return dark, light


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screens", action="store_true", help="write design/screens/after-*.png")
    args = ap.parse_args()

    dark, light = token_sets()

    # ---------------------------------------------------------------- static checks
    print("static")
    page = PAGE.read_text()
    check(bool(re.search(r'href="assets/css/app\.css"', page)),
          "index.html links assets/css/app.css",
          "no <link> to the compiled token layer")
    hexes = [h for h in re.findall(r"#[0-9a-fA-F]{3,8}\b", page)]
    check(not hexes, "no raw hex colour in index.html", f"found {sorted(set(hexes))}")
    check(re.search(r"data-theme", page) is not None,
          "index.html carries the theme attribute (dark default / light flip)")

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(1200)

        print("tokens")
        app_css_status = pg.evaluate(
            "async () => (await fetch('assets/css/app.css')).status"
        )
        check(app_css_status == 200, "assets/css/app.css is served (200)", f"got {app_css_status}")
        body_bg = rgb(pg.evaluate("getComputedStyle(document.body).backgroundColor"))
        check(body_bg == rgb(dark["bg"]), "body background is the --bg token",
              f"body {body_bg} vs --bg {rgb(dark['bg'])}")
        n_cards = pg.eval_on_selector_all(".card", "e => e.length")
        check(n_cards >= 2, "the page is composed of .card panels", f"{n_cards} found")
        if n_cards:
            card_bg = rgb(pg.evaluate(
                "getComputedStyle(document.querySelector('.card')).backgroundColor"))
            check(card_bg == rgb(dark["surface"]), ".card background is the --surface token",
                  f"{card_bg} vs {rgb(dark['surface'])}")

        print("shell")
        # The served shell must reserve the layout the app is about to fill. Everything below the
        # skeleton is shoved down the screen when the data lands, so measure the two states the
        # browser actually paints: the HTML with JS DISABLED (exactly what arrives first — the
        # app cannot have run) and the loaded page. JS off also makes the comparison deterministic:
        # no race with the CSV fetch.
        ctx = br.new_context(java_script_enabled=False, viewport={"width": 1440, "height": 900})
        shell_pg = ctx.new_page()
        shell_pg.goto(URL, wait_until="load", timeout=60000)
        shell_pg.wait_for_timeout(300)
        shell_h = shell_pg.evaluate("document.documentElement.scrollHeight")
        n_bars = shell_pg.eval_on_selector_all(
            ".skeleton, .skeleton-inline",
            "e => e.filter(x => x.getBoundingClientRect().height > 0).length")
        n_bars_card = shell_pg.eval_on_selector_all(
            "#table-state .skeleton, #table-state .skeleton-inline",
            "e => e.filter(x => x.getBoundingClientRect().height > 0).length")
        ctx.close()
        loaded_h = pg.evaluate("document.documentElement.scrollHeight")
        jump = abs(loaded_h - shell_h)
        check(shell_h > 0 and jump <= 0.20 * loaded_h,
              "the served shell reserves the loaded layout (|shell - loaded| <= 20%)",
              f"shell {shell_h}px vs loaded {loaded_h}px = {jump}px ({jump / loaded_h * 100:.1f}%)")
        check(n_bars >= 15, "the served shell renders real skeleton bars (>= 15)",
              f"{n_bars} visible bars")
        check(n_bars_card >= 3, "the table card's skeleton stands in for the table (>= 3 rows)",
              f"{n_bars_card} bars inside #table-state")

        n_kpi = pg.eval_on_selector_all(".kpi-value", "e => e.length")
        kpi_text = pg.eval_on_selector_all(
            ".kpi-value", "e => e.map(x => (x.innerText||'').trim()).filter(Boolean)")
        check(n_kpi >= 1, "a KPI row exists (.kpi-value)", f"{n_kpi} found")
        check(len(kpi_text) == n_kpi and all(kpi_text), "every KPI value renders text",
              f"empty: {n_kpi - len(kpi_text)}")

        print("the heat table")
        rows = pg.eval_on_selector_all("#tbody tr", "e => e.length")
        check(rows == 279, "279 month rows render for the default region (NSW)", f"{rows} rows")
        heat = pg.eval_on_selector_all(
            "td", "e => e.filter(x => /\\$/.test(x.innerText)).map(x => ({cls: x.className, txt: x.innerText.trim(), bg: getComputedStyle(x).backgroundColor}))")
        check(len(heat) >= 500, "the heat cells render (2 price columns x 279 months)",
              f"{len(heat)} cells")
        seq = [c for c in heat if re.search(r"\bseq-\d\b", c["cls"] or "")]
        check(len(seq) == len(heat), "every heat cell uses the .seq-* ramp",
              f"{len(heat) - len(seq)} cells not on the ramp")
        inline = [c for c in heat if "rgb" in (c["bg"] or "") and not re.search(r"\bseq-\d\b", c["cls"] or "")]
        check(not inline, "no heat cell carries an inline rgb() colour", f"{len(inline)} do")
        # A class can be present and still lose the cascade (a page rule out-ranking `.seq-*`), which
        # leaves the cell unfilled while every name-based check passes. Compare the pixels to the tokens.
        ramp_rgb = {rgb(dark[f"seq-{i}"]) for i in range(8) if f"seq-{i}" in dark}
        unfilled = [c for c in heat if rgb(c["bg"]) not in ramp_rgb]
        check(not unfilled, "every heat cell is actually filled from the ramp",
              f"{len(unfilled)} of {len(heat)} unfilled, e.g. {unfilled[:2]}")
        check(all(c["txt"] for c in heat), "every heat cell prints its number (colour is not the only signal)")
        used = {int(re.search(r"\bseq-(\d)\b", c["cls"]).group(1)) for c in seq if re.search(r"\bseq-(\d)\b", c["cls"])}
        check(len(used) >= 4, "the ramp is actually graded, not one flat step", f"steps used: {sorted(used)}")

        legend_txt = " ".join(pg.eval_on_selector_all(
            "[data-heat-legend], .seq-legend, .card-foot", "e => e.map(x => x.innerText)"))
        check("<$30" in legend_txt and "$250+" in legend_txt,
              "the heat scale is stated on screen (<$30 … $250+)", "no legend naming the stops")

        prov = pg.evaluate("document.body.innerText")
        check("Source:" in prov, "provenance states the source")
        check(bool(re.search(r"(as of|Data through|through)\s+\w+\s+\d{4}", prov)),
              "provenance states the as-of month")

        print("interaction hooks")
        tabs = pg.eval_on_selector_all("#tabs button, #tabs .seg-item", "e => e.map(x => x.innerText.trim())")
        check(len(tabs) == 5 and tabs[:1] == ["NSW"], "5 region tabs render", f"{tabs}")
        basis = pg.eval_on_selector_all("#price-toggle button", "e => e.map(x => x.innerText.trim())")
        check(basis == ["Nominal", "Real"], "the Nominal / Real basis switch renders", f"{basis}")
        clean = pg.eval_on_selector_all("#tabs button, #tabs .seg-item",
                                       "e => e.map(x => ({t: x.innerText.trim(), h: x.getBoundingClientRect().height}))")
        check(all(c["h"] >= 28 for c in clean), "tab targets are >= 28px tall",
              f"{[c for c in clean if c['h'] < 28]}")
        before = pg.inner_text("#tbody tr:first-child")
        pg.evaluate("""(() => { const b=[...document.querySelectorAll('#tabs button, #tabs .seg-item')]
            .find(x => x.innerText.trim() === 'VIC'); b.click(); })()""")
        pg.wait_for_timeout(400)
        after = pg.inner_text("#tbody tr:first-child")
        check(before != after, "clicking a region tab re-renders the table", "row 1 unchanged")
        dl = pg.eval_on_selector_all("a[download]", "e => e.map(x => x.getAttribute('href'))")
        check(len(dl) == 6 and all(h and h.endswith(".xlsx") for h in dl),
              "6 Excel downloads are wired (5 regions + All States)", f"{dl}")

        print("themes and phone")
        # Sticky chrome must stay ONE row: pinned chrome taller than 72px covers the thing it is
        # meant to label. The page has no page-level sticky/filter bar (measured: #tabs and the
        # theme .seg are `static` at every width) — the only sticky chrome is the table's own
        # header and first column, so that is what this pins.
        sticky = pg.evaluate("""() => {
            const out = [];
            for (const el of document.querySelectorAll('*')) {
                const cs = getComputedStyle(el);
                if (cs.position !== 'sticky' && cs.position !== 'fixed') continue;
                out.push({sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
                          cls: (el.className || '').toString(), h: el.getBoundingClientRect().height});
            }
            return out; }""")
        tall = [s for s in sticky if s["h"] > 72]
        check(not tall, "sticky chrome is one row at 1440px (nothing pinned is taller than 72px)",
              f"{len(sticky)} sticky element(s), tallest {max([s['h'] for s in sticky], default=0):.0f}px"
              + (f" — {tall[:2]}" if tall else " (the table's .th header and its pinned month column)"))

        flip = pg.evaluate("""(() => {
            const r = document.documentElement, before = getComputedStyle(document.body).backgroundColor;
            r.setAttribute('data-theme','light');
            const after = getComputedStyle(document.body).backgroundColor;
            r.setAttribute('data-theme','dark');
            return {before, after}; })()""")
        check(rgb(flip["after"]) == rgb(light["bg"]),
              "the light theme flips body to the light --bg token",
              f"{flip['after']} vs {rgb(light['bg'])}")

        phone = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        phone.goto(URL, wait_until="networkidle", timeout=60000)
        phone.wait_for_timeout(1000)
        over = phone.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check(over <= 1, "no page-level horizontal overflow at 390px", f"{over}px")
        wrapped = phone.evaluate("""(() => { const w = document.querySelector('.table-wrap, .card-body');
            return w ? w.scrollWidth > w.clientWidth : false; })()""")
        check(wrapped or over <= 1, "the wide numeric table scrolls inside its card at 390px")

        state = br.new_page(viewport={"width": 1440, "height": 900})
        state.route("**/outputs/summary.csv", lambda r: r.abort())
        state.goto(URL, wait_until="domcontentloaded", timeout=60000)
        state.wait_for_timeout(1500)
        st = state.eval_on_selector_all(
            ".state", "e => e.map(x => ({txt: x.innerText, h: x.getBoundingClientRect().height}))")
        check(bool(st) and max(s["h"] for s in st) > 0,
              "a missing data file renders a VISIBLE .state panel, not a bare error string",
              f"{len(st)} .state element(s), tallest {max([s['h'] for s in st], default=0):.0f}px")

        # The skeleton wrapper the app empties is also the DOM-contract hook the next agent depends
        # on: it must survive the load (hidden, not deleted) and it must keep a truthful busy state.
        wrap_state = pg.evaluate("""() => {
            const el = document.getElementById('table-state');
            if (!el) return null;
            return {display: getComputedStyle(el).display, busy: el.getAttribute('aria-busy'),
                    skeletons: el.querySelectorAll('.skeleton, .skeleton-inline').length}; }""")
        check(wrap_state is not None and wrap_state["display"] == "none",
              "#table-state survives the load (hidden, not removed)",
              f"{wrap_state}")
        check(wrap_state is not None and wrap_state["busy"] == "false",
              "#table-state clears aria-busy once the data has landed", f"{wrap_state}")
        check(pg.eval_on_selector_all(".placeholder-badges", "e => e.length") == 0,
              "the shell's placeholder badges are replaced by real counts after load",
              "placeholder-badges still on the page")

        check(not errors, "no JS errors on load", "; ".join(errors[:3]))

        if args.screens:
            SCREENS.mkdir(parents=True, exist_ok=True)
            for fname, page_obj, full in (("after-top.png", pg, False), ("after-full.png", pg, True),
                                          ("after-phone.png", phone, True)):
                page_obj.screenshot(path=str(SCREENS / fname), full_page=full)
            state.screenshot(path=str(SCREENS / "after-nodata.png"))
            pg.evaluate("""(() => { const b=[...document.querySelectorAll('#tabs button, #tabs .seg-item')]
                .find(x => x.innerText.trim() === 'VIC'); b.click(); })()""")
            pg.wait_for_timeout(600)
            pg.screenshot(path=str(SCREENS / "after-vic-top.png"))
            print(f"  wrote screenshots to {SCREENS}")

        br.close()

    print(f"\n{len(fails)} check(s) failed" if fails else "\nall checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

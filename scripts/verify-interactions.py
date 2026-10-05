#!/usr/bin/env python3
"""Behaviour check for the AEMO Historical Prices page — every interaction a design pass must NOT lose.

    cd ~/Design/"AEMO Historical Prices" && python3 -m http.server 9382 --bind 127.0.0.1 &
    /opt/anaconda3/bin/python3 scripts/verify-interactions.py

It tests what the page does, not what it looks like. Every number is read from outputs/summary.csv
itself and recomputed here, so a restyle that silently re-maps a column or changes a window fails.
Reads only; writes nothing. Exit 1 on any breakage.
"""
from __future__ import annotations

import csv
import pathlib
import re
import sys
from decimal import ROUND_HALF_UP, Decimal

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:9382/index.html"
CSV = ROOT / "outputs" / "summary.csv"
REGIONS = {"NSW": "NSW1", "QLD": "QLD1", "VIC": "VIC1", "SA": "SA1", "TAS": "TAS1"}
ROLLING = [1, 3, 5, 10]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

fails: list[str] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def label(ym: str) -> str:
    y, m = ym.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def usd(v: Decimal | float) -> str:
    """Two decimals, half-up, on the exact decimal value (the CSV holds 2dp decimals, so an average
    can land exactly on a half-cent; binary floats would round it the wrong way half the time)."""
    d = Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ("−$" if d < 0 else "$") + f"{abs(d):,.2f}"


rows = list(csv.DictReader(CSV.open()))
by_region = {r: sorted((x for x in rows if x["region"] == r), key=lambda x: x["year_month"])
             for r in REGIONS.values()}
latest = max(r["year_month"] for r in rows)
print(f"csv: {len(rows)} rows · latest {latest} · " +
      ", ".join(f"{k} {len(v)}" for k, v in by_region.items()))


def click(pg, selector: str, text: str) -> None:
    pg.evaluate("""([sel, t]) => { const b = [...document.querySelectorAll(sel)]
        .find(x => x.innerText.trim() === t); b.click(); }""", [selector, text])
    pg.wait_for_timeout(300)


def table(pg) -> list[list[str]]:
    return pg.eval_on_selector_all(
        "#tbody tr", "rows => rows.map(r => [...r.children].map(c => c.innerText.trim()))")


def kpis(pg) -> list[str]:
    return pg.eval_on_selector_all("#kpis > div", "e => e.map(x => x.innerText.replace(/\\s+/g, ' ').trim())")


with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(URL, wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(1200)

    print("data")
    check(len(table(pg)) == len(by_region["NSW1"]),
          "the active region renders one row per month",
          f"{len(table(pg))} rows vs {len(by_region['NSW1'])}")
    check(pg.eval_on_selector_all("#tabs [aria-selected=true]", "e => e.length") == 1,
          "exactly one region tab is marked selected")
    check(pg.eval_on_selector_all("#price-toggle [aria-pressed=true]", "e => e.length") == 1,
          "exactly one price basis is marked pressed")

    print("tabs")
    for name, region in REGIONS.items():
        click(pg, "#tabs button", name)
        t = table(pg)
        check(len(t) == len(by_region[region]), f"{name} tab renders {len(by_region[region])} rows", f"{len(t)} rows")
        first_month = label(by_region[region][0]["year_month"])
        check(t[0][0].endswith(first_month) or first_month in t[0][0],
              f"{name} first row is {first_month}", t[0][0])

    print("values match the csv — both bases, every region")
    for name, region in REGIONS.items():
        click(pg, "#tabs button", name)
        for mode in ("nominal", "real"):
            click(pg, "#price-toggle button", mode.capitalize())
            t = table(pg)
            got = {r[0].replace("†", "").replace("(carbon price period)", "").replace("CPI not yet published, real equals nominal", "").strip(): r[1:] for r in t}
            bad = []
            for r in by_region[region]:
                want = [usd(r[f"rrp_{mode}"]), usd(r[f"peak_rrp_{mode}"])]
                g = got.get(label(r["year_month"]))
                if g != want:
                    bad.append((r["year_month"], g, want))
            check(not bad, f"{name} {mode}: every RRP and Peak RRP cell equals summary.csv",
                  f"{len(bad)} mismatched, e.g. {bad[:2]}")

    print("KPI tiles recompute from the csv")
    for name, region in REGIONS.items():
        click(pg, "#tabs button", name)
        for mode in ("nominal", "real"):
            click(pg, "#price-toggle button", mode.capitalize())
            tiles = kpis(pg)
            want = []
            rs = by_region[region]
            for years in ROLLING:
                recent = rs[-years * 12:]
                avg = sum(Decimal(x[f"rrp_{mode}"]) for x in recent) / len(recent)
                pk = sum(Decimal(x[f"peak_rrp_{mode}"]) for x in recent) / len(recent)
                want.append((usd(avg), usd(pk), f"{label(recent[0]['year_month'])} – {label(rs[-1]['year_month'])}"))
            ok = len(tiles) == 4 and all(a in t and b in t and c in t for t, (a, b, c) in zip(tiles, want))
            check(ok, f"{name} {mode}: 1/3/5/10-year average RRP, peak and window",
                  f"tiles={tiles[:2]} want={want[:2]}")

    print("flags")
    click(pg, "#tabs button", "NSW")
    click(pg, "#price-toggle button", "Nominal")
    carbon = pg.eval_on_selector_all("#tbody tr", "e => e.filter(r => r.querySelector('th .badge-dot')).map(r => r.children[0].innerText.trim())")
    carbon = [re.sub(r"\s*\(carbon price period\)", "", c).strip() for c in carbon]
    want_carbon = [label(r["year_month"]) for r in by_region["NSW1"] if r["carbon_flag"] == "True"]
    check(carbon == want_carbon, "carbon-period marker sits on exactly the carbon_flag months",
          f"{len(carbon)} marked vs {len(want_carbon)} flagged")
    check(pg.eval_on_selector_all("#tbody th", "e => e.filter(x => x.innerText.includes('†')).length") == 0,
          "no CPI-estimate dagger in nominal mode")
    click(pg, "#price-toggle button", "Real")
    est = pg.eval_on_selector_all("#tbody th", "e => e.filter(x => x.innerText.includes('†')).length")
    want_est = sum(1 for r in by_region["NSW1"] if r["cpi_estimated"] == "True")
    check(est == want_est, "the † marks exactly the cpi_estimated months in real mode", f"{est} vs {want_est}")
    click(pg, "#price-toggle button", "Nominal")

    print("table shape")
    heads = pg.eval_on_selector_all("#thead th", "e => e.map(x => x.innerText.trim())")
    check(heads == ["Month", "RRP ($/MWh)", "Peak RRP ($/MWh)"], "3 header cells", f"{heads}")
    sticky = pg.eval_on_selector_all("#thead th", "e => e.map(x => getComputedStyle(x).position)")
    check(all(s == "sticky" for s in sticky), "header cells stay sticky", f"{set(sticky)}")

    print("downloads and footer")
    hrefs = pg.eval_on_selector_all("a[download]", "e => e.map(x => x.getAttribute('href'))")
    want = [f"{k}_historical_prices.xlsx" for k in REGIONS] + ["All_States_historical_prices.xlsx"]
    check(len(hrefs) == 6 and all(any(h.endswith(w) for h in hrefs) for w in want),
          "the 6 Excel downloads keep their targets", f"{hrefs}")
    foot = pg.inner_text("#footer")
    check(label(latest) in foot, f"the footer states the as-of month ({label(latest)})", foot[-120:])
    check("Source:" in foot, "the footer states the source")

    print("keyboard")
    pg.keyboard.press("Tab")
    focused = pg.evaluate("document.activeElement.innerText.trim()")
    check(bool(focused), "the first Tab lands on a labelled control", f"activeElement={focused!r}")

    print("phone")
    phone = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    phone.goto(URL, wait_until="networkidle", timeout=60000)
    phone.wait_for_timeout(1000)
    wrap = phone.evaluate("""(() => { const w = document.querySelector('.table-wrap');
        if (!w) return null; w.scrollLeft = 9999;
        return {sw: w.scrollWidth, cw: w.clientWidth}; })()""")
    check(wrap is not None, "the table lives in a scrollable wrapper at 390px")
    check(phone.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1,
          "the page itself does not scroll sideways at 390px")
    small = phone.eval_on_selector_all(
        "button:not([disabled]), a", "e => e.filter(x => {const r=x.getBoundingClientRect(); return r.width>0 && r.height>0 && r.height<32 && x.tagName==='BUTTON'}).map(x=>x.innerText.trim())")
    check(not small, "no visible button under 32px tall at 390px", f"{small}")

    check(not errors, "no JS/console errors", "; ".join(errors[:3]))
    br.close()

print(f"\n{len(fails)} check(s) failed" if fails else "\nall interactions intact")
sys.exit(1 if fails else 0)

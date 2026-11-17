"""Rendered-page smoke: load index.html in headless chromium, offline, with the data the repo commits.

No server and no port: page_harness routes http://aemo.test/ to this checkout, PapaParse to a vendored
copy, nav.js to an empty script, and aborts (and records) every other request.
"""

import csv
import datetime as dt

import pytest

pytest.importorskip("playwright")

from page_harness import ROOT, assert_clean, loaded_page  # noqa: E402

READY = "document.querySelectorAll('#tbody tr').length > 0"


def _month(ym):
    return dt.date(int(ym[:4]), int(ym[5:7]), 1).strftime("%b %Y")


def _rows(region):
    with open(ROOT / "outputs" / "summary.csv", newline="") as f:
        return [r for r in csv.DictReader(f) if r["region"] == region]


def test_page_renders_the_committed_data_with_no_errors():
    nsw = _rows("NSW1")
    latest = max(r["year_month"] for r in _rows("NSW1"))
    with loaded_page(wait_for=READY) as (page, log):
        assert_clean(log)
        # four stat tiles, each a dollar figure, none still a skeleton
        tiles = page.locator("#kpis > div")
        assert tiles.count() == 4
        for i in range(4):
            text = tiles.nth(i).inner_text()
            assert "$" in text and any(ch.isdigit() for ch in text), text
        assert page.locator("#kpis .skeleton").count() == 0
        # the table has one body row per committed NSW month, filled, visible, with height
        assert page.locator("#tbody tr").count() == len(nsw)
        first = page.locator("#tbody tr").first.inner_text()
        assert "$" in first, first
        for sel in ("#kpis", "#table", "#tabs", "#price-toggle", "#footer"):
            box = page.locator(sel).bounding_box()
            assert box and box["height"] > 0 and page.locator(sel).is_visible(), sel
        # region switch is real buttons (no skeleton placeholders), downloads rendered
        assert page.locator("#tabs button:not([disabled])").count() == 5
        assert page.locator("#tabs .skeleton").count() == 0
        assert page.locator("#downloads a").count() >= 3
        # footer is filled from the CSV (latest month) and from status.json (last checked)
        footer = page.locator("#footer").inner_text()
        assert f"Data to {_month(latest)}" in footer, footer
        assert "last checked" in footer, footer
        assert "loading" not in footer


def test_region_and_price_basis_switch_rerender():
    qld = _rows("QLD1")
    with loaded_page(wait_for=READY) as (page, log):
        page.locator("#tabs button", has_text="QLD").click()
        page.wait_for_function(f"document.querySelectorAll('#tbody tr').length === {len(qld)}")
        page.locator("#price-toggle button[data-mode=real]").click()
        assert page.locator("#price-toggle button[data-mode=real]").get_attribute("aria-pressed") == "true"
        assert "$" in page.locator("#tbody tr").first.inner_text()
        assert_clean(log)


def test_page_renders_at_phone_width():
    with loaded_page(width=400, height=800, wait_for=READY) as (page, log):
        assert_clean(log)
        assert page.locator("#tbody tr").count() > 0
        assert page.locator("#kpis").is_visible()

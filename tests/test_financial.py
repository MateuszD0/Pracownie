import copy

from bs4 import BeautifulSoup
from test_management_dashboard import management_view

from pracownie.dashboard import render_dashboard_documents
from pracownie.financial import codes, financial_data, meaningful_discount
from pracownie.presentation import render_html


def test_same_project_price_change_is_visible_before_copy_alerts():
    view = management_view()
    html = render_html(view)
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one("#financial")
    assert "5 000,00 zł" in panel.text and "4 500,00 zł" in panel.text
    assert "-500.00 / -10.00%" in panel.text
    assert html.index('id="financial"') < html.index('id="briefing"')
    docs = render_dashboard_documents(view, "https://github.com/test/monitor/releases/tag/day")
    assert docs["DASHBOARD.md"].index("## Ceny, kody i rabaty") < docs["DASHBOARD.md"].index(
        "## Zmiany oferty"
    )
    assert "4 500,00 zł" in docs["dashboard/ceny-i-rabaty.md"]


def test_stale_partial_or_unpaired_prices_are_not_daily_change_claims():
    for reason in ["stale", "partial", "not_paired"]:
        view = management_view()
        row = view["rows"][0]
        if reason == "stale":
            row["current"]["observed_at"] = "2026-10-18T06:00:00+00:00"
        elif reason == "partial":
            row["current"]["quality"] = "partial"
        else:
            view["comparison"]["price_domains"] = []
        assert not financial_data(view)["changes"]


def test_codes_are_literal_and_discount_requires_specific_terms():
    assert codes("Rabat 20% z kodem JESIEN20 do 30.11.2026") == ["JESIEN20"]
    assert codes("Kod rabatowy: DOM2026") == ["DOM2026"]
    assert not meaningful_discount("Nie zapomnij zapytać o rabat")
    assert not codes("Wpisz kod rabatowy w koszyku")
    assert not codes("Kod rabatowy znajdziesz w koszyku")
    assert codes('Kod rabatowy: "jesien"') == ["jesien"]
    assert meaningful_discount("Promocja: oszczędzasz 300 zł")


def test_current_discount_quotes_keep_dates_terms_and_source_without_claiming_launch():
    view = management_view()
    offer = {
        "domain": "test.pl",
        "text": "Rabat 20% z kodem JESIEN20 do 30.11.2026 tylko na projekty do 100 m2",
        "status": "Obecna w zapisie",
        "sources": [
            {"url": "https://test.pl/promocja", "observed_at": "2026-10-20T06:00:00+00:00", "page": "glowna"}
        ],
    }
    view["metadata"]["intelligence"] = {
        "offers": [
            offer,
            dict(offer, text="Zapytaj o rabat"),
            dict(
                offer,
                domain="old.pl",
                sources=[dict(offer["sources"][0], observed_at="2026-10-19T06:00:00+00:00")],
            ),
        ]
    }
    before = copy.deepcopy(view)
    data = financial_data(view)
    assert len(data["offers"]) == 1 and data["offers"][0]["codes"] == ["JESIEN20"]
    docs = render_dashboard_documents(view, "https://github.com/test/monitor/releases/tag/day")
    assert "JESIEN20" in docs["DASHBOARD.md"]
    assert "tylko na projekty do 100 m2" in docs["dashboard/ceny-i-rabaty.md"]
    assert "Obecna w zapisie" in docs["DASHBOARD.md"]
    assert view == before

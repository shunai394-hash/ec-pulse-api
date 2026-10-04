from app.pages import LANDING_PAGE, PAGE_CSP, csp_for


def test_landing_is_profit_first():
    assert "売れる商品を" in LANDING_PAGE
    assert "Opportunity Radar" in LANDING_PAGE
    assert "痛点" in LANDING_PAGE
    assert "仕入れ上限価格" in LANDING_PAGE
    assert "利益を保証するサービスではありません" in LANDING_PAGE


def test_profit_calculator_is_present_and_csp_is_hashed():
    assert 'id="max-buy"' in LANDING_PAGE
    assert 'id="sale-price"' in LANDING_PAGE
    assert "script-src 'sha256-" in PAGE_CSP["/"]
    assert "unsafe-inline" not in PAGE_CSP["/"]


def test_landing_has_customer_paths():
    for href in ("/account", "/docs", "/#pricing", "/#quickstart", "/#profit-check"):
        assert href in LANDING_PAGE


def test_opportunity_radar_exposes_decision_signals():
    assert 'BUYING DECISION' in LANDING_PAGE
    assert '仕入れ候補' in LANDING_PAGE
    assert '価格を監視' in LANDING_PAGE


def test_landing_does_not_use_inline_style_attributes():
    assert 'style="' not in LANDING_PAGE
    assert 'class="small muted" class=' not in LANDING_PAGE


def test_opportunity_radar_is_interactive_and_accessible():
    assert 'role="tablist"' in LANDING_PAGE
    assert 'role="tab"' in LANDING_PAGE
    assert 'aria-selected="true"' in LANDING_PAGE
    assert 'data-radar="0"' in LANDING_PAGE
    assert 'data-radar="1"' in LANDING_PAGE
    assert 'id="radar-detail"' in LANDING_PAGE
    assert 'radarData' in LANDING_PAGE
    assert '価格を監視' in LANDING_PAGE
    assert '仕入れ候補を比較' in LANDING_PAGE

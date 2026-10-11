"""Regression checks for the public-facing EC Pulse site quality contract."""
from html.parser import HTMLParser

from app.pages import LANDING_PAGE, ACCOUNT_PAGE, csp_for


class _Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.links = []
        self.inputs = []
        self.labels = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "input":
            self.inputs.append(attrs)
        if tag == "label" and attrs.get("for"):
            self.labels.append(attrs["for"])

    def handle_data(self, data):
        self.text.append(data)


def _parse(html):
    parser = _Document()
    parser.feed(html)
    return parser


def test_landing_page_is_branded_japanese_html_with_a_real_primary_action():
    doc = _parse(LANDING_PAGE)
    source = " ".join(doc.text)
    assert '<html lang="ja">' in LANDING_PAGE
    assert "EC Pulse" in source
    assert "無料でAPIキーを取得" in source
    assert "API Docs" in source


def test_demo_is_unambiguously_marked_as_sample_data():
    source = " ".join(_parse(LANDING_PAGE).text)
    assert "DEMO / SAMPLE DATA" in source
    assert "実データの取得結果ではありません" in source
    assert "商品・レビューのデータは必ず取得できますか？" in source
    assert "利用規約" in source or "提供元のルール" in source


def test_landing_page_ids_are_unique_and_local_fragments_resolve():
    doc = _parse(LANDING_PAGE)
    assert len(doc.ids) == len(set(doc.ids)), "duplicate HTML id breaks labels, tabs, or navigation"
    known = set(doc.ids)
    for href in doc.links:
        if href.startswith("#"):
            assert href[1:] in known, f"broken local fragment: {href}"
        elif href.startswith("/#"):
            assert href[2:] in known, f"broken landing-page fragment: {href}"


def test_account_inputs_have_explicit_labels_or_accessible_names():
    doc = _parse(ACCOUNT_PAGE)
    label_ids = set(doc.labels)
    for attrs in doc.inputs:
        input_id = attrs.get("id")
        if attrs.get("type") == "hidden":
            continue
        assert attrs.get("aria-label") or attrs.get("aria-labelledby") or input_id in label_ids, (
            f"input needs an accessible label: {attrs}"
        )


def test_inline_html_policy_is_restricted_to_page_hashes():
    policy = csp_for(LANDING_PAGE)
    assert "default-src 'none'" in policy
    assert "style-src 'sha256-" in policy
    assert "script-src 'sha256-" in policy
    assert "frame-ancestors 'none'" in policy

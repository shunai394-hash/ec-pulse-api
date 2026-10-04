"""Server-rendered HTML for the product site: landing page, account portal and legal pages.

Every page keeps its CSS (and the account page its JS) inline, and is served with a
Content-Security-Policy that allows exactly those inline blocks by SHA-256 hash.
"""
import base64
import hashlib
import html
import re
from pathlib import Path

_LEGAL_DIR = Path(__file__).resolve().parent.parent / "docs" / "legal"

LEGAL_DOCUMENTS = {
    "terms": ("terms-of-service.md", "利用規約"),
    "privacy": ("privacy-policy.md", "プライバシーポリシー"),
    "billing": ("billing-and-cancellation.md", "料金・解約ポリシー"),
    "commercial-transactions": ("commercial-transactions.md", "特定商取引法に基づく表記"),
    "acceptable-use": ("acceptable-use.md", "利用制限ポリシー"),
}

_CSS = r"""
:root{--bg:#05070a;--panel:#0a0f15;--panel2:#0f1720;--line:#1c2733;--text:#f6f8fb;--muted:#93a1b2;--lime:#b9ff5c;--cyan:#72e8ff;--amber:#ffd166;--red:#ff7f8a;--max:1180px;--radius:18px}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:radial-gradient(circle at 75% 12%,rgba(114,232,255,.08),transparent 28%),radial-gradient(circle at 15% 18%,rgba(185,255,92,.07),transparent 24%),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.65;-webkit-text-size-adjust:100%}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(to bottom,black,transparent 72%);z-index:-1}
a{color:inherit}a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--cyan);outline-offset:3px}
.wrap{width:min(calc(100% - 40px),var(--max));margin:auto}
.nav{display:flex;align-items:center;justify-content:space-between;gap:20px;min-height:76px;flex-wrap:wrap;border-bottom:1px solid rgba(255,255,255,.05)}
.brand{display:flex;align-items:center;gap:11px;font-weight:800;letter-spacing:-.025em;text-decoration:none}.mark{width:30px;height:30px;border:1px solid var(--lime);border-radius:9px;display:grid;place-items:center;font-size:10px;color:var(--lime);box-shadow:0 0 24px rgba(185,255,92,.12)}
.links{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;color:var(--muted)}.links a{text-decoration:none}.links a:hover{color:var(--text)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:46px;padding:11px 18px;border-radius:12px;border:1px solid var(--line);background:rgba(15,23,32,.8);color:var(--text);font:inherit;font-weight:700;font-size:14px;text-decoration:none;cursor:pointer;transition:transform .2s ease,border-color .2s ease,background .2s ease}
.btn:hover{border-color:#415063;transform:translateY(-1px)}.btn.primary{background:var(--lime);border-color:var(--lime);color:#071006;box-shadow:0 10px 30px rgba(185,255,92,.12)}.btn.primary:hover{background:#c9ff7c}.btn[disabled]{opacity:.5;cursor:not-allowed}
h1{font-size:clamp(42px,7vw,78px);line-height:.99;letter-spacing:-.055em;margin:14px 0 22px;max-width:850px}
h2{font-size:clamp(28px,4vw,46px);line-height:1.08;letter-spacing:-.035em;margin:8px 0 15px}h3{font-size:17px;margin:0 0 7px}
p{margin:0 0 12px}.muted{color:var(--muted)}.small{font-size:13px}.kicker{color:var(--lime);font-size:12px;font-weight:800;letter-spacing:.11em;text-transform:uppercase}.hero-accent{color:var(--lime)}.signal-title{font-weight:800;font-size:18px}.mt13{margin-top:13px}.mt7{margin-top:7px}.label-block{display:block;margin-top:12px}.decision-title{font-size:20px;margin-top:4px}.max-buy{font-size:48px;line-height:1.05;font-weight:850;color:var(--lime);margin:10px 0}
.hero{padding:78px 0 62px;display:grid;grid-template-columns:1fr .92fr;gap:54px;align-items:center}.lead{font-size:19px;color:#c8d2de;max-width:42em}
.hero-note{display:flex;gap:10px;align-items:center;color:#b8c4d2;font-size:13px;margin-top:18px}.pulse{width:7px;height:7px;border-radius:50%;background:var(--lime);box-shadow:0 0 14px var(--lime)}
.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:25px}.section{padding:76px 0;border-top:1px solid rgba(255,255,255,.07)}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:28px}.grid.two{grid-template-columns:repeat(2,1fr)}
.card{background:linear-gradient(145deg,rgba(15,23,32,.92),rgba(7,11,16,.92));border:1px solid var(--line);border-radius:var(--radius);padding:22px;min-width:0;box-shadow:0 18px 60px rgba(0,0,0,.16)}
.card:hover{border-color:#2b3948}.tag{display:inline-block;font-size:11px;color:var(--cyan);border:1px solid #21434c;border-radius:999px;padding:3px 9px;margin-bottom:9px}
pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}pre{background:#030507;border:1px solid var(--line);border-radius:14px;padding:16px;overflow-x:auto;margin:0;white-space:pre;line-height:1.55}code{background:#111922;border-radius:5px;padding:1px 5px}pre code{background:none;padding:0}
.signal{border:1px solid #263543;background:rgba(8,14,20,.82);border-radius:20px;padding:18px;position:relative;overflow:hidden;box-shadow:0 30px 90px rgba(0,0,0,.3)}.signal:after{content:"";position:absolute;width:220px;height:220px;right:-100px;top:-110px;border-radius:50%;background:rgba(185,255,92,.08);filter:blur(8px)}
.signal-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:15px}.live{font-size:11px;color:var(--lime);font-weight:800;letter-spacing:.08em}
.product{display:grid;grid-template-columns:74px 1fr auto;gap:14px;align-items:center;padding:15px 0;border-top:1px solid #18232e}.product:first-of-type{border-top:0}.thumb{width:74px;height:74px;border-radius:14px;background:linear-gradient(135deg,#18242d,#0b1117);display:grid;place-items:center;color:#5e7180;font-size:11px}
.product-name{font-weight:750}.product-meta{font-size:12px;color:var(--muted);margin-top:3px}.profit{text-align:right}.profit strong{display:block;color:var(--lime);font-size:20px}.profit span{font-size:11px;color:var(--muted)}
.score{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 8px;background:rgba(185,255,92,.08);color:var(--lime);font-size:11px;font-weight:800;margin-top:7px}
.stat-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:16px}.stat{background:#080d12;border:1px solid #18232e;border-radius:12px;padding:12px}.stat b{display:block;font-size:20px}.stat span{font-size:11px;color:var(--muted)}
.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:30px}.flow-step{position:relative;padding:20px 16px;border:1px solid var(--line);border-radius:15px;background:rgba(9,14,20,.82)}.flow-step:not(:last-child):after{content:"→";position:absolute;right:-10px;top:50%;transform:translateY(-50%);color:#526274;z-index:2}.flow-num{font-size:11px;color:var(--lime);font-weight:800}
.callout{border:1px solid rgba(185,255,92,.24);background:linear-gradient(110deg,rgba(185,255,92,.08),rgba(114,232,255,.04));border-radius:20px;padding:28px;margin-top:28px}.callout strong{font-size:20px}
.price{font-size:30px;font-weight:800;margin:7px 0}.plan ul{padding-left:18px;margin:10px 0 18px;color:#c5cfdb}.plan .btn{width:100%}.plan.featured{border-color:rgba(185,255,92,.55);box-shadow:0 0 50px rgba(185,255,92,.06)}
.steps{counter-reset:s;list-style:none;padding:0;margin:20px 0 0;display:grid;gap:15px}.steps li{counter-increment:s;position:relative;padding-left:44px}.steps li:before{content:counter(s);position:absolute;left:0;top:0;width:30px;height:30px;border-radius:50%;border:1px solid var(--lime);color:var(--lime);display:grid;place-items:center;font-weight:800;font-size:13px}
.footer{padding:32px 0 52px;border-top:1px solid rgba(255,255,255,.07);color:var(--muted);font-size:13px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}.footer nav{display:flex;gap:14px;flex-wrap:wrap}
.notice{border:1px solid #4a3d1c;background:#16120a;color:#f1dca8;border-radius:12px;padding:12px 14px;font-size:14px}.error{border-color:#5a2626;background:#170b0b;color:#ffc9c9}.ok{border-color:#2d4a1c;background:#0d160a;color:#d6f5c0}
.keybox{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.keybox code{word-break:break-all;font-size:14px;padding:8px 10px}input[type=password],input[type=text]{width:100%;min-height:44px;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:#05070a;color:var(--text);font:inherit}.hidden{display:none!important}
.cta-card{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}.h-sm{font-size:22px}.h-page{font-size:clamp(28px,5vw,40px)}.mb8{margin-bottom:8px}.mt10{margin-top:10px}.mt12{margin-top:12px}.mt14{margin-top:14px}.mt16{margin-top:16px}.mt18{margin-top:18px}.mt20{margin-top:20px}.mt22{margin-top:22px}.m006{margin:0 0 6px}.m0{margin:0}.page-pad{padding:24px 0 56px}.break{word-break:break-all}
.doc{max-width:820px;padding:24px 0 56px}.doc pre{white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:15px;line-height:1.8;background:var(--panel)}
.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
@media (max-width:980px){.hero{grid-template-columns:1fr;gap:34px;padding-top:52px}.flow{grid-template-columns:1fr 1fr}.flow-step:not(:last-child):after{display:none}.grid{grid-template-columns:1fr 1fr}}
@media (max-width:620px){.wrap{width:min(calc(100% - 28px),var(--max))}.hero{padding:42px 0}.grid,.grid.two,.flow{grid-template-columns:1fr}.links{gap:11px;font-size:12px}.nav{padding:9px 0}.lead{font-size:16px}.section{padding:52px 0}.actions .btn{flex:1 1 100%}.stat-row{grid-template-columns:1fr 1fr}.product{grid-template-columns:58px 1fr}.thumb{width:58px;height:58px}.profit{grid-column:2;text-align:left}.hero h1{font-size:clamp(40px,13vw,58px)}}
"""

_NAV = """<header class="wrap nav"><a class="brand" href="/"><span class="mark">EP</span>EC Pulse API</a>
<nav class="links" aria-label="メイン"><a href="/#features">機能</a><a href="/#pricing">料金</a><a href="/#quickstart">クイックスタート</a><a href="/docs">API Docs</a><a href="/account">アカウント</a></nav></header>"""

_FOOTER = """<footer class="wrap footer"><span>© EC Pulse API</span><nav aria-label="フッター">
<a href="/docs">API Docs</a><a href="/health">Status</a><a href="/legal/terms">利用規約</a><a href="/legal/privacy">プライバシー</a>
<a href="/legal/billing">料金・解約</a><a href="/legal/commercial-transactions">特定商取引法に基づく表記</a></nav></footer>"""


def _page(title: str, description: str, body: str, script: str = "") -> str:
    script_tag = f"<script>{script}</script>" if script else ""
    return (
        '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<meta name="description" content="{html.escape(description)}">\n'
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
        f"<title>{html.escape(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        f"{_NAV}\n{body}\n{_FOOTER}\n{script_tag}\n</body></html>"
    )


def _hash(source: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(source.encode()).digest()).decode() + "'"


def csp_for(page: str) -> str:
    """CSP that allows only this page's own inline <style>/<script> blocks."""
    styles = " ".join(_hash(s) for s in re.findall(r"<style>(.*?)</style>", page, re.S))
    scripts = " ".join(_hash(s) for s in re.findall(r"<script>(.*?)</script>", page, re.S))
    policy = [
        "default-src 'none'",
        f"style-src {styles}",
        "img-src 'self' data:",
        "connect-src 'self'",
        "form-action 'self'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
    ]
    if scripts:
        policy.insert(2, f"script-src {scripts}")
    return "; ".join(policy)


_LANDING_BODY = r"""<main>
<section class="wrap hero" aria-labelledby="hero-title">
<div>
<span class="kicker">EC Pulse / Profit Intelligence</span>
<h1 id="hero-title">売れる商品を、<br><span class="hero-accent">探す前に絞り込む。</span></h1>
<p class="lead">「何を仕入れれば儲かる？」を、勘と検索作業だけに任せない。市場の痛点、商品候補、価格、競合、口コミをつなぎ、<strong>仕入れ判断に必要な材料</strong>を一つの流れにします。</p>
<div class="actions"><a class="btn primary" href="/account">利益候補を探し始める →</a><a class="btn" href="/docs">APIとして組み込む</a></div>
<div class="hero-note"><span class="pulse" aria-hidden="true"></span><span>EC Pulse API — 商品データを「利益につながる判断」へ変えるエンジン</span></div>
</div>
<div class="signal" aria-label="利益候補のデモ">
<div class="signal-top"><div><span class="tag">Opportunity Radar / DEMO</span><div class="signal-title">今日見るべき商品候補</div></div><span class="live">● SIGNALS</span></div>
<div class="product"><div class="thumb">PRODUCT</div><div><div class="product-name">軽量・収納系 EC商品</div><div class="product-meta">需要シグナル ↑　口コミの不満あり　競合価格 ¥4,980</div><span class="score">Opportunity 86 / 100</span></div><div class="profit"><strong>¥1,840</strong><span>想定利益余地*</span></div></div>
<div class="product"><div class="thumb">PRODUCT</div><div><div class="product-name">レビュー改善型アクセサリ</div><div class="product-meta">痛点集中　価格帯安定　出品者少なめ*</div><span class="score">Opportunity 79 / 100</span></div><div class="profit"><strong>¥1,220</strong><span>想定利益余地*</span></div></div>
<div class="stat-row"><div class="stat"><b>3</b><span>市場候補</span></div><div class="stat"><b>42%</b><span>痛点集中度*</span></div><div class="stat"><b>¥3,140</b><span>参考仕入れ*</span></div><div class="stat"><b>4.6</b><span>競争余地*</span></div></div>
<p class="small muted mt13">*デモ表示。実際の数値は取得した市場データ・価格・口コミ等から算出されます。利益を保証するものではありません。</p>
</div>
</section>

<section class="wrap section" id="problem">
<span class="kicker">The real problem</span>
<h2>ECで儲ける人ほど、<br>「検索」ではなく「判断」に時間を使う。</h2>
<div class="grid">
<div class="card"><span class="tag">01 / 探す</span><h3>商品候補が多すぎる</h3><p class="muted">Amazon、楽天、Yahoo!、SNS、レビューを別々に見ていたら、候補を絞るだけで時間が消える。</p></div>
<div class="card"><span class="tag">02 / 見抜く</span><h3>売れそうでも利益が残らない</h3><p class="muted">販売価格だけでは判断できない。仕入れ価格、競合、価格変化、需要の兆候を一緒に見る必要があります。</p></div>
<div class="card"><span class="tag">03 / 逃さない</span><h3>見つけた機会が消える</h3><p class="muted">価格が下がった、競合が増えた、需要の痛点が強くなった。変化を監視して次の判断につなげます。</p></div>
</div>
<div class="callout"><strong>EC Pulseの仕事は「検索結果を増やす」ことではない。</strong><p class="muted mt7">調査 → 比較 → 痛点抽出 → 商品候補 → 利益余地 → 監視までをつなげ、あなたが「仕入れる / 見送る」を決めやすくすることです。</p></div>
</section>

<section class="wrap section" id="engine">
<span class="kicker">From signal to decision</span>
<h2>「何を仕入れる？」までを、一本のデータフローに。</h2>
<div class="flow">
<div class="flow-step"><div class="flow-num">01 / SIGNAL</div><h3>市場を読む</h3><p class="muted small">商品・検索・口コミから市場の変化を集める。</p></div>
<div class="flow-step"><div class="flow-num">02 / PAIN</div><h3>痛点を読む</h3><p class="muted small">不満・要望を集計し、売れる切り口を見つける。</p></div>
<div class="flow-step"><div class="flow-num">03 / PRODUCT</div><h3>候補を探す</h3><p class="muted small">Amazon・楽天・Yahoo!を横断して候補を比較。</p></div>
<div class="flow-step"><div class="flow-num">04 / MARGIN</div><h3>利益余地を見る</h3><p class="muted small">価格・競合・変化を重ねて仕入れ判断を支援。</p></div>
<div class="flow-step"><div class="flow-num">05 / WATCH</div><h3>機会を追う</h3><p class="muted small">価格監視とOpportunityで変化を逃さない。</p></div>
</div>
</section>

<section class="wrap section" id="features">
<span class="kicker">What you can do</span>
<h2>人間がやっていた面倒を、データ処理に変える。</h2>
<div class="grid">
<div class="card"><span class="tag">PRODUCT DISCOVERY</span><h3>商品を横断して候補化</h3><p class="muted">Amazon・楽天・Yahoo!ショッピングの検索結果を正規化。商品名、価格、在庫などを同じ形式で扱えます。</p></div>
<div class="card"><span class="tag">CONSUMER INSIGHT</span><h3>口コミを「売れる理由」に変換</h3><p class="muted">レビューやコメントから痛点・頻度・傾向を抽出。商品改善や広告訴求の材料にできます。</p></div>
<div class="card"><span class="tag">OPPORTUNITY</span><h3>価格変化を利益機会として追う</h3><p class="muted">価格履歴とOpportunity分析で、単なる「現在価格」ではなく変化を見る。</p></div>
</div>
</section>

<section class="wrap section" id="workflow">
<span class="kicker">A practical buying loop</span>
<h2>使い方は「調べる → 買う」ではない。<br>「仮説 → 検証 → 監視 → 次の仕入れ」。</h2>
<div class="grid two">
<div class="card"><h3>仕入れ担当なら</h3><ol class="steps"><li><strong>狙いたい市場を入力</strong><br><span class="muted">キーワードや商品URLから調査を開始。</span></li><li><strong>候補を比較</strong><br><span class="muted">価格・在庫・競合・口コミを同じ土俵で見る。</span></li><li><strong>仕入れ候補を監視</strong><br><span class="muted">価格や市場の変化を追い、次の判断につなげる。</span></li></ol></div>
<div class="card"><h3>事業者・開発者なら</h3><pre><code>POST /v1/products/search

{
  "query": "ワイヤレスイヤホン",
  "marketplaces": ["amazon","rakuten","yahoo"],
  "limit": 5
}

→ 正規化された商品候補
→ 価格・在庫・市場情報
→ 自社の仕入れ/分析システムへ</code></pre><p class="small muted mt12">APIとして既存のEC業務・社内ツール・AIエージェントに組み込めます。</p></div>
</div>
</section>


<section class="wrap section" id="profit-check">
<span class="kicker">Buying math / free tool</span>
<h2>「いくらなら仕入れていい？」を、先に数字にする。</h2>
<p class="muted">売価とコスト条件を入れると、目標粗利を守るための<strong>仕入れ上限価格</strong>を計算します。EC Pulseの市場データと組み合わせれば、「安いから買う」ではなく「この条件なら検討する」に変えられます。</p>
<div class="grid two">
<div class="card">
<label for="sale-price" class="small muted">想定販売価格（円）</label>
<input id="sale-price" type="text" inputmode="decimal" value="4980" aria-describedby="profit-help">
<label for="fee-rate" class="small muted label-block">販売手数料（%）</label>
<input id="fee-rate" type="text" inputmode="decimal" value="10">
<label for="shipping-cost" class="small muted label-block">送料・梱包（円）</label>
<input id="shipping-cost" type="text" inputmode="decimal" value="500">
<label for="margin-rate" class="small muted label-block">目標粗利率（%）</label>
<input id="margin-rate" type="text" inputmode="decimal" value="30">
<p id="profit-help" class="small muted mt12">税金・広告費・返品・為替・人件費などは別途考慮してください。</p>
</div>
<div class="signal" aria-live="polite">
<span class="tag">DECISION OUTPUT</span>
<h3 class="decision-title">仕入れ上限</h3>
<div id="max-buy" class="max-buy">¥2,488</div>
<p class="muted">この価格以下なら、入力した条件上では目標粗利率を維持できます。</p>
<div class="stat-row">
<div class="stat"><b id="gross-profit">¥1,494</b><span>目標粗利</span></div>
<div class="stat"><b id="fee-cost">¥498</b><span>販売手数料</span></div>
<div class="stat"><b id="break-even">¥3,982</b><span>損益分岐点</span></div>
<div class="stat"><b id="margin-check">30%</b><span>目標粗利率</span></div>
</div>
</div>
</div>
</section>

<section class="wrap section" id="pricing">
<span class="kicker">Start with evidence</span>
<h2>まず無料で「使えるか」を確かめる。</h2>
<div class="grid">
<div class="card plan"><span class="tag">FREE</span><h3>小さく検証</h3><div class="price">¥0</div><ul><li>毎月100クレジット</li><li>30リクエスト/分</li><li>全エンドポイントを試せる</li></ul><a class="btn" href="/account">無料で始める</a></div>
<div class="card plan featured"><span class="tag">PRO</span><h3>仕入れ判断を回す</h3><div class="price">Stripeで表示</div><ul><li>月間クレジットを付与</li><li>300リクエスト/分</li><li>Stripeで管理・解約</li></ul><a class="btn primary" href="/account#billing">Proを試す</a></div>
<div class="card plan"><span class="tag">BUSINESS</span><h3>調査を自動化</h3><div class="price">Stripeで表示</div><ul><li>3,000リクエスト/分</li><li>大量検索・リサーチ・監視</li><li>業務システムへの組み込み</li></ul><a class="btn" href="/account#billing">Businessを見る</a></div>
</div>
<p class="small muted mt14">料金とクレジット数はStripeの決済画面で確定前に表示されます。</p>
</section>

<section class="wrap section" id="quickstart">
<span class="kicker">Quick start</span>
<h2>最初の1商品から始める。</h2>
<div class="grid two">
<ol class="steps">
<li><strong>Googleでログイン</strong><br><span class="muted">アカウントを作成。</span></li>
<li><strong>APIキーを発行</strong><br><span class="muted">Freeプランのクレジットで検証。</span></li>
<li><strong>商品を検索・取得</strong><br><span class="muted">まず一つの市場、一つの商品から試す。</span></li>
</ol>
<div class="card"><span class="tag">FIRST TEST</span><h3>「売れるかも」をデータで確かめる</h3><p class="muted">APIキーを発行したら、商品検索・比較・口コミ分析・価格監視へ進めます。</p><div class="actions"><a class="btn primary" href="/account">利益候補を探す</a><a class="btn" href="/docs">API Docs</a></div></div>
</div>
</section>

<section class="wrap section" id="security">
<span class="kicker">Built for real operations</span>
<h2>利益判断に使うデータだから、基盤も堅く。</h2>
<div class="grid">
<div class="card"><h3>クレジットの整合性</h3><p class="muted">入力エラーでは消費せず、取得先障害などで失敗した処理は返却する設計。</p></div>
<div class="card"><h3>SSRF対策</h3><p class="muted">プライベートIP・ループバック・メタデータアドレスへの接続をリダイレクト後も含めて拒否。</p></div>
<div class="card"><h3>APIキー保護</h3><p class="muted">顧客キーはハッシュで保存し、ローテーション・失効にも対応。</p></div>
</div>
</section>

<section class="wrap section">
<div class="cta-card card">
<div><span class="kicker">Make the next buying decision faster</span><h2 class="m006">検索する時間を減らして、仕入れを考える時間を増やす。</h2><p class="m0 muted">利益を保証するサービスではありません。利益につながる判断材料を、早く・繰り返し集めるための基盤です。</p></div>
<div class="m0 actions"><a class="btn primary" href="/account">無料で始める →</a><a class="btn" href="/docs">APIを見る</a></div>
</div>
</section>
</main>"""

_LANDING_SCRIPT = r"""
(function(){
function n(id){var v=parseFloat(String(document.getElementById(id).value).replace(/,/g,""));return Number.isFinite(v)&&v>=0?v:0}
function yen(v){return "¥"+Math.max(0,Math.round(v)).toLocaleString("ja-JP")}
function calc(){
 var sale=n("sale-price"),fee=n("fee-rate")/100,ship=n("shipping-cost"),margin=n("margin-rate")/100;
 var feeCost=sale*fee,targetProfit=sale*margin,maxBuy=sale-feeCost-ship-targetProfit,breakEven=sale-feeCost-ship;
 document.getElementById("max-buy").textContent=yen(maxBuy);
 document.getElementById("gross-profit").textContent=yen(targetProfit);
 document.getElementById("fee-cost").textContent=yen(feeCost);
 document.getElementById("break-even").textContent=yen(breakEven);
 document.getElementById("margin-check").textContent=Math.round(margin*100)+"%";
}
["sale-price","fee-rate","shipping-cost","margin-rate"].forEach(function(id){document.getElementById(id).addEventListener("input",calc)});
calc();
})();
"""

LANDING_PAGE = _page(
    "EC Pulse API — 仕入れ判断を速くするProfit Intelligence",
    "市場の痛点、商品候補、価格、口コミ、競合をつなぎ、EC事業者の仕入れ判断を支援するコマースデータAPI。",
    _LANDING_BODY,
    _LANDING_SCRIPT,
)

_ACCOUNT_BODY = r"""<main class="page-pad wrap">
<h1 class="h-page">アカウント</h1>
<div id="status" class="notice" role="status">読み込み中…</div>

<section id="signed-out" class="mt18 card hidden">
<h2 class="h-sm">ログインして APIキーを発行</h2>
<p class="muted">Googleアカウントでログインすると、Freeプラン（毎月100クレジット）のAPIキーを発行できます。</p>
<a class="btn primary" href="/auth/google">Googleでログイン</a>
</section>

<div id="signed-in" class="hidden">
<div class="mt18 grid">
<div class="card"><div class="muted small">ログイン中</div><div class="break" id="user-email">—</div></div>
<div class="card"><div class="muted small">プラン</div><div class="stat" id="plan">—</div></div>
<div class="card"><div class="muted small">残りクレジット</div><div class="stat" id="credits">—</div></div>
</div>

<section class="mt16 card">
<h2 class="h-sm">APIキー</h2>
<p class="muted" id="key-info">—</p>
<div id="new-key" class="notice ok hidden"><p class="mb8"><strong>新しいAPIキー（この画面でのみ表示されます）</strong></p>
<div class="keybox"><code id="new-key-value"></code><button class="btn" id="copy-key" type="button">コピー</button></div></div>
<div class="actions"><button class="btn primary" id="issue-key" type="button">APIキーを発行</button><button class="btn hidden" id="rotate-key" type="button">キーを再発行（旧キーは失効）</button></div>
</section>

<section class="mt16 card">
<h2 class="h-sm">直近30日の利用状況</h2>
<p class="muted" id="usage-empty">まだ利用履歴はありません。</p>
<div class="table-scroll"><table id="usage-table" class="hidden"><thead><tr><th>エンドポイント</th><th>リクエスト</th><th>クレジット</th></tr></thead><tbody id="usage-rows"></tbody></table></div>
</section>

<section class="mt16 card" id="billing">
<h2 class="h-sm">プラン変更・お支払い</h2>
<p class="muted">決済とプラン管理は Stripe で行います。操作にはAPIキーが必要です（このページを開いている間だけ使用し、保存しません）。</p>
<label for="billing-key" class="small muted">APIキー</label>
<input id="billing-key" type="password" autocomplete="off" placeholder="ecp_live_…">
<div class="actions"><button class="btn primary" type="button" data-plan="pro">Proにアップグレード</button><button class="btn" type="button" data-plan="business">Businessにアップグレード</button><button class="btn" type="button" id="portal">請求情報・解約（Stripe）</button></div>
<p class="mt12 muted small">解約するとFreeプランに戻ります。詳しくは <a href="/legal/billing">料金・解約ポリシー</a>。</p>
</section>

<form class="mt20" method="post" action="/auth/logout"><button class="btn" type="submit">ログアウト</button></form>
</div>
</main>"""

_ACCOUNT_SCRIPT = r"""
(function(){
var $=function(id){return document.getElementById(id)};
function show(el,on){el.classList.toggle('hidden',!on)}
function status(msg,kind){var s=$('status');s.textContent=msg;s.className='notice'+(kind?' '+kind:'');show(s,!!msg)}
async function call(method,url,opts){
  opts=opts||{};
  var headers={'Accept':'application/json'};
  if(opts.body){headers['Content-Type']='application/json'}
  if(opts.key){headers['X-API-Key']=opts.key}
  var r=await fetch(url,{method:method,headers:headers,credentials:'same-origin',body:opts.body?JSON.stringify(opts.body):undefined});
  var data=null;try{data=await r.json()}catch(e){}
  return {status:r.status,ok:r.ok,data:data||{}};
}
function detail(res){var d=res.data&&res.data.detail;return typeof d==='string'?d:('HTTP '+res.status)}
async function loadAccount(){
  var acc=await call('GET','/v1/customer/account');
  if(!acc.ok){status('アカウント情報を取得できませんでした: '+detail(acc),'error');return}
  $('plan').textContent=String(acc.data.plan||'free').toUpperCase();
  $('credits').textContent=acc.data.provisioned?String(acc.data.credits_balance):'100（発行時に付与）';
  if(acc.data.key_prefix){$('key-info').textContent='有効なキー: '+acc.data.key_prefix+'…（キー全体は発行時のみ表示）';show($('issue-key'),false);show($('rotate-key'),true)}
  else{$('key-info').textContent='まだAPIキーは発行されていません。';show($('issue-key'),true);show($('rotate-key'),false)}
  var rows=[];
  if(acc.data.provisioned){var usage=await call('GET','/v1/customer/usage?days=30');rows=(usage.ok&&usage.data.by_endpoint)||[]}
  var body=$('usage-rows');body.textContent='';
  rows.forEach(function(r){var tr=document.createElement('tr');[r.endpoint,r.requests,r.credits].forEach(function(v){var td=document.createElement('td');td.textContent=String(v);tr.appendChild(td)});body.appendChild(tr)});
  show($('usage-table'),rows.length>0);show($('usage-empty'),rows.length===0);
}
async function issue(rotate){
  if(rotate&&!confirm('現在のAPIキーは直ちに使えなくなります。再発行しますか？'))return;
  var b=rotate?$('rotate-key'):$('issue-key');b.disabled=true;
  try{
    var res=await call('POST','/v1/customer/key',{body:{rotate:rotate}});
    if(!res.ok){status('APIキーを発行できませんでした: '+detail(res),'error');return}
    if(res.data.api_key){$('new-key-value').textContent=res.data.api_key;$('billing-key').value=res.data.api_key;show($('new-key'),true);status('APIキーを発行しました。今すぐ安全な場所に保存してください。','ok')}
    else{status(res.data.warning||'既存のキーがあります。','')}
    await loadAccount();
  }finally{b.disabled=false}
}
async function billing(url){
  var key=$('billing-key').value.trim();
  if(!key){status('APIキーを入力してください。','error');$('billing-key').focus();return}
  var res=await call('POST',url,{key:key});
  if(res.ok&&res.data.url){window.location.href=res.data.url;return}
  status('Stripeに接続できませんでした: '+detail(res),'error');
}
async function init(){
  var me=await call('GET','/auth/me');
  if(me.status===503){status('ログイン機能は現在ご利用いただけません: '+detail(me),'error');return}
  if(!me.ok){status('','');show($('signed-out'),true);return}
  status('','');show($('signed-in'),true);
  $('user-email').textContent=(me.data.user&&me.data.user.email)||'—';
  await loadAccount();
}
$('issue-key').addEventListener('click',function(){issue(false)});
$('rotate-key').addEventListener('click',function(){issue(true)});
$('copy-key').addEventListener('click',function(){navigator.clipboard&&navigator.clipboard.writeText($('new-key-value').textContent).then(function(){$('copy-key').textContent='コピーしました'})});
document.querySelectorAll('[data-plan]').forEach(function(b){b.addEventListener('click',function(){billing('/v1/billing/checkout?plan='+b.getAttribute('data-plan'))})});
$('portal').addEventListener('click',function(){billing('/v1/billing/portal')});
init().catch(function(){status('通信エラーが発生しました。時間をおいて再読み込みしてください。','error')});
})();
"""

ACCOUNT_PAGE = _page(
    "アカウント — EC Pulse API",
    "EC Pulse API のAPIキー発行、残りクレジット、利用状況、プラン管理。",
    _ACCOUNT_BODY,
    _ACCOUNT_SCRIPT,
)


# The document file names are also accepted as slugs, e.g. /legal/privacy-policy.
_LEGAL_ALIASES = {filename.removesuffix(".md"): slug for slug, (filename, _) in LEGAL_DOCUMENTS.items()}


def legal_page(slug: str) -> str | None:
    entry = LEGAL_DOCUMENTS.get(_LEGAL_ALIASES.get(slug, slug))
    if not entry:
        return None
    filename, title = entry
    try:
        text = (_LEGAL_DIR / filename).read_text(encoding="utf-8")
    except OSError:
        return None
    body = (
        f'<main class="wrap doc"><p class="muted small"><a href="/">トップ</a> / {html.escape(title)}</p>'
        f"<pre>{html.escape(text)}</pre></main>"
    )
    return _page(f"{title} — EC Pulse API", f"EC Pulse API {title}", body)


FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="8" fill="#07090d"/>'
    '<rect x="2.5" y="2.5" width="27" height="27" rx="6" fill="none" stroke="#b9ff66" stroke-width="2"/>'
    '<text x="16" y="21" text-anchor="middle" font-family="Arial,sans-serif" font-size="12" font-weight="700" fill="#b9ff66">EP</text>'
    "</svg>"
)

ROBOTS_TXT = "User-agent: *\nAllow: /\nDisallow: /v1/\nDisallow: /api/\nDisallow: /auth/\nDisallow: /billing\nDisallow: /account\n"

PAGE_CSP = {
    "/": csp_for(LANDING_PAGE),
    "/account": csp_for(ACCOUNT_PAGE),
}
# Legal pages share the page shell and have no script, so one policy fits all of them.
LEGAL_CSP = csp_for(_page("", "", ""))

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
:root{--bg:#07090d;--panel:#0d1118;--panel2:#111722;--line:#202733;--text:#f5f7fa;--muted:#9aa5b5;--accent:#b9ff66;--accent2:#7ce7ff;--warn:#ffcf66;--err:#ff8a8a;--max:1160px}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.65;-webkit-text-size-adjust:100%}
a{color:inherit}a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--accent2);outline-offset:2px}
.wrap{width:min(calc(100% - 32px),var(--max));margin:auto}
.nav{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:72px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;font-weight:750;letter-spacing:-.02em;text-decoration:none}
.mark{width:28px;height:28px;border:1px solid var(--accent);border-radius:8px;display:grid;place-items:center;font-size:11px;color:var(--accent)}
.links{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;color:var(--muted)}.links a{text-decoration:none}.links a:hover{color:var(--text)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:44px;padding:10px 18px;border-radius:10px;border:1px solid var(--line);background:var(--panel2);color:var(--text);font:inherit;font-weight:650;font-size:15px;text-decoration:none;cursor:pointer}
.btn:hover{border-color:#3a4558}.btn.primary{background:var(--accent);border-color:var(--accent);color:#08100a}.btn.primary:hover{filter:brightness(1.05)}
.btn[disabled]{opacity:.5;cursor:not-allowed}
h1{font-size:clamp(32px,6vw,56px);line-height:1.1;letter-spacing:-.03em;margin:14px 0 18px}
h2{font-size:clamp(24px,3.6vw,34px);line-height:1.25;letter-spacing:-.02em;margin:8px 0 14px}
h3{font-size:18px;margin:0 0 6px}
p{margin:0 0 12px}.muted{color:var(--muted)}.small{font-size:13px}
.kicker{color:var(--accent);font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.hero{padding:56px 0 40px;display:grid;grid-template-columns:1.05fr .95fr;gap:48px;align-items:center}
.lead{font-size:18px;color:#c9d2de;max-width:36em}
.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px}
.section{padding:56px 0;border-top:1px solid var(--line)}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:22px}
.grid.two{grid-template-columns:repeat(2,1fr)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;min-width:0}
.card p:last-child{margin-bottom:0}
.tag{display:inline-block;font-size:12px;color:var(--accent2);border:1px solid #23414a;border-radius:999px;padding:2px 9px;margin-bottom:8px}
pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}
pre{background:#05070a;border:1px solid var(--line);border-radius:12px;padding:16px;overflow-x:auto;margin:0;white-space:pre;line-height:1.55}
code{background:#111722;border-radius:5px;padding:1px 5px}pre code{background:none;padding:0}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.table-scroll{overflow-x:auto}
.price{font-size:28px;font-weight:750;margin:6px 0}.plan ul{padding-left:18px;margin:10px 0 16px;color:#c9d2de}.plan .btn{width:100%}
.plan.featured{border-color:var(--accent)}
.steps{counter-reset:s;list-style:none;padding:0;margin:20px 0 0;display:grid;gap:14px}
.steps li{counter-increment:s;position:relative;padding-left:44px}.steps li:before{content:counter(s);position:absolute;left:0;top:0;width:30px;height:30px;border-radius:50%;border:1px solid var(--accent);color:var(--accent);display:grid;place-items:center;font-weight:700;font-size:14px}
.footer{padding:32px 0 48px;border-top:1px solid var(--line);color:var(--muted);font-size:13px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.footer nav{display:flex;gap:14px;flex-wrap:wrap}
.notice{border:1px solid #4a3d1c;background:#16120a;color:#f1dca8;border-radius:12px;padding:12px 14px;font-size:14px}
.error{border-color:#5a2626;background:#170b0b;color:#ffc9c9}
.ok{border-color:#2d4a1c;background:#0d160a;color:#d6f5c0}
.stat{font-size:30px;font-weight:750}
.keybox{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.keybox code{word-break:break-all;font-size:14px;padding:8px 10px}
input[type=password],input[type=text]{width:100%;min-height:44px;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:#05070a;color:var(--text);font:inherit}
.hidden{display:none !important}
.cta-card{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}.h-sm{font-size:22px}.h-page{font-size:clamp(28px,5vw,40px)}.mb8{margin-bottom:8px}.mt10{margin-top:10px}.mt12{margin-top:12px}.mt14{margin-top:14px}.mt16{margin-top:16px}.mt18{margin-top:18px}.mt20{margin-top:20px}.mt22{margin-top:22px}.m006{margin:0 0 6px}.m0{margin:0}.page-pad{padding:24px 0 56px}.break{word-break:break-all}
.doc{max-width:820px;padding:24px 0 56px}.doc pre{white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:15px;line-height:1.8;background:var(--panel)}
@media (max-width:900px){.hero{grid-template-columns:1fr;gap:28px;padding-top:32px}.grid{grid-template-columns:1fr 1fr}}
@media (max-width:620px){.grid,.grid.two{grid-template-columns:1fr}.links{gap:12px;font-size:13px}.nav{padding:10px 0}.lead{font-size:16px}.section{padding:40px 0}.actions .btn{flex:1 1 100%}}
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
<section class="wrap hero">
<div>
<span class="kicker">EC事業者のためのコマースデータAPI</span>
<h1>商品ページを、<br>判断に使えるデータへ。</h1>
<p class="lead">EC Pulse API は、商品ページの情報取得、Amazon・楽天・Yahoo!ショッピング横断の商品検索、価格比較、価格監視、レビュー・口コミの分析を、ひとつのAPIキーとクレジットで提供します。</p>
<div class="actions"><a class="btn primary" href="/account">無料で始める（Googleログイン）</a><a class="btn" href="/docs">API Docs を見る</a></div>
<p class="mt14 muted small">Freeプランは毎月100クレジット。クレジットカード登録は不要です。</p>
</div>
<div class="card" aria-label="レスポンス例">
<span class="tag">POST /v1/products</span>
<pre><code>{
  "url": "https://shop.example.jp/item/123",
  "title": "ワイヤレスイヤホン ブラック",
  "price": 12800,
  "currency": "JPY",
  "availability": "InStock",
  "cache": { "hit": false, "ttl_seconds": 300 }
}</code></pre>
<p class="mt10 muted small">ページ内の構造化データ（JSON-LD 等）から商品名・価格・在庫などを抽出します。項目はページの公開内容によって異なります。</p>
</div>
</section>

<section class="wrap section" id="usecases">
<span class="kicker">こんな業務に</span>
<h2>手作業の調査とコピペを、APIの呼び出しに置き換える</h2>
<div class="grid">
<div class="card"><h3>競合の価格チェック</h3><p class="muted">競合商品のURLを登録しておけば、価格変化をWebhookで受け取れます。毎朝ブラウザで巡回する必要はありません。</p></div>
<div class="card"><h3>仕入れ・商品選定</h3><p class="muted">キーワードで Amazon・楽天・Yahoo!ショッピングを横断検索し、価格帯や出品状況を一度に比較できます。</p></div>
<div class="card"><h3>レビューからの改善点抽出</h3><p class="muted">口コミやレビュー文を送ると、配送・価格・品質などの不満点を件数と割合で集計します。</p></div>
</div>
</section>

<section class="wrap section" id="features">
<span class="kicker">主な機能</span>
<h2>エンドポイントとクレジット消費</h2>
<p class="muted">クレジットは処理が成功した分だけ消費されます。入力エラー（4xx）では消費されず、取得先の障害で失敗した処理は自動で返却されます。</p>
<div class="table-scroll"><table>
<thead><tr><th>機能</th><th>エンドポイント</th><th>消費クレジット</th></tr></thead>
<tbody>
<tr><td>商品情報の取得</td><td><code>POST /v1/products</code></td><td>1</td></tr>
<tr><td>横断商品検索</td><td><code>POST /v1/products/search</code></td><td>件数(limit) × マーケットプレイス数</td></tr>
<tr><td>商品比較</td><td><code>POST /v1/products/compare</code></td><td>URL数（2〜20）</td></tr>
<tr><td>リサーチ取り込み</td><td><code>POST /v1/research/ingest</code></td><td>URL数（1〜20）</td></tr>
<tr><td>消費者インサイト</td><td><code>POST /v1/consumer-insights/analyze</code></td><td>コメント50件ごとに1</td></tr>
<tr><td>価格監視の登録</td><td><code>POST /v1/monitors</code></td><td>1</td></tr>
<tr><td>価格履歴</td><td><code>GET /v1/monitors/{id}/history</code></td><td>1</td></tr>
<tr><td>価格機会の分析</td><td><code>GET /v1/monitors/{id}/opportunity</code></td><td>2</td></tr>
<tr><td>監視一覧・利用状況</td><td><code>GET /v1/monitors</code>, <code>GET /v1/account</code></td><td>0</td></tr>
</tbody></table></div>
</section>

<section class="wrap section" id="pricing">
<span class="kicker">料金</span>
<h2>クレジット制のシンプルなプラン</h2>
<div class="grid">
<div class="card plan"><h3>Free</h3><div class="price">¥0</div><ul><li>毎月100クレジット</li><li>30リクエスト/分</li><li>全エンドポイント利用可</li></ul><a class="btn" href="/account">無料で始める</a></div>
<div class="card plan featured"><h3>Pro</h3><div class="price">Stripeで表示</div><ul><li>請求ごとに月間クレジットを付与</li><li>300リクエスト/分</li><li>Stripe カスタマーポータルで管理・解約</li></ul><a class="btn primary" href="/account#billing">Proにアップグレード</a></div>
<div class="card plan"><h3>Business</h3><div class="price">Stripeで表示</div><ul><li>請求ごとに月間クレジットを付与</li><li>3,000リクエスト/分</li><li>大量リサーチ・監視向け</li></ul><a class="btn" href="/account#billing">Businessにアップグレード</a></div>
</div>
<p class="mt14 muted small">有料プランの金額と付与クレジット数は、Stripe の決済画面で確定前に表示されます。詳細は <a href="/legal/billing">料金・解約ポリシー</a> をご覧ください。</p>
</section>

<section class="wrap section" id="quickstart">
<span class="kicker">クイックスタート</span>
<h2>3ステップで最初のレスポンスまで</h2>
<div class="grid two">
<ol class="steps">
<li><strong>Googleでログイン</strong><br><span class="muted"><a href="/account">アカウントページ</a>からログインします。</span></li>
<li><strong>APIキーを発行</strong><br><span class="muted">キーは発行時に一度だけ表示されます。安全な場所に保存してください。</span></li>
<li><strong>リクエストを送る</strong><br><span class="muted"><code>X-API-Key</code> ヘッダーにキーを付けて呼び出します。残りクレジットは <code>X-EC-Credits-Remaining</code> ヘッダーで確認できます。</span></li>
</ol>
<pre><code>curl -X POST https://ec-pulse-api.vercel.app/v1/products/search \
  -H "X-API-Key: $EC_PULSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"ワイヤレスイヤホン",
       "marketplaces":["amazon","rakuten","yahoo"],
       "limit":5}'</code></pre>
</div>
<div class="mt22 table-scroll"><table>
<thead><tr><th>ステータス</th><th>意味</th></tr></thead>
<tbody>
<tr><td>401</td><td>APIキーがない・無効・失効済み</td></tr>
<tr><td>402</td><td>クレジット不足（消費は行われません）</td></tr>
<tr><td>400 / 422</td><td>入力エラー、または非公開ネットワークのURL</td></tr>
<tr><td>429</td><td>レート制限超過（<code>Retry-After</code> 秒後に再試行）</td></tr>
<tr><td>502 / 503</td><td>取得先またはデータベースの一時的な障害（消費分は返却）</td></tr>
</tbody></table></div>
</section>

<section class="wrap section" id="security">
<span class="kicker">セキュリティ</span>
<h2>安心して業務に組み込めるように</h2>
<div class="grid">
<div class="card"><h3>APIキーはハッシュで保存</h3><p class="muted">平文のキーは保存しません。キーはいつでもローテーション・失効できます。</p></div>
<div class="card"><h3>SSRF対策</h3><p class="muted">プライベートIP・ループバック・メタデータアドレスへの接続を、リダイレクト後も含めて拒否します。</p></div>
<div class="card"><h3>任意のリクエスト署名</h3><p class="muted">HMAC署名を有効にすると、改ざん・リプレイを防げます。<a href="/docs">API Docs</a> を参照。</p></div>
</div>
</section>

<section class="wrap section">
<div class="cta-card card">
<div><h2 class="m006">まずは商品URLを1つ試してください</h2><p class="m0 muted">Freeプランの100クレジットで、全機能を試せます。</p></div>
<div class="m0 actions"><a class="btn primary" href="/account">APIキーを発行する</a><a class="btn" href="/docs">API Docs</a></div>
</div>
</section>
</main>"""

LANDING_PAGE = _page(
    "EC Pulse API — EC事業者のためのコマースデータAPI",
    "EC Pulse API: 商品情報取得、Amazon・楽天・Yahoo!ショッピング横断検索、価格比較・価格監視、レビュー分析を提供するクレジット制API。",
    _LANDING_BODY,
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

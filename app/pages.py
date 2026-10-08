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
:root{
  --paper:#f3f0e8;--paper-2:#ebe7dc;--card:#fbfaf6;--ink:#121211;--ink-2:#45433e;--ink-3:#6b685f;
  --line:#d8d3c6;--line-2:#c4bead;--signal:#d23c14;--signal-dk:#ff6a3d;--signal-ink:#a8300f;--signal-soft:#f9dfd5;
  --go:#17704a;--go-soft:#d9ecdf;--night:#121211;--night-2:#1c1c1a;--night-line:#33322e;--night-ink:#f3f0e8;--night-mute:#aaa69b;
  --mono:ui-monospace,"SFMono-Regular","SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --sans:"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic UI","Yu Gothic",Meiryo,system-ui,-apple-system,"Segoe UI",sans-serif;
  --max:1240px;--gut:clamp(16px,4vw,40px);--r:14px
}
*{box-sizing:border-box}.sr-only{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.75;font-feature-settings:"palt" 1;text-rendering:optimizeLegibility}
::selection{background:var(--signal);color:#fff}
a{color:inherit;text-underline-offset:3px}
a:focus-visible,button:focus-visible,input:focus-visible,[tabindex]:focus-visible,.mobile-menu summary:focus-visible{outline:3px solid var(--signal);outline-offset:3px;border-radius:4px}.mobile-menu summary{list-style:none;cursor:pointer;user-select:none}.mobile-menu summary::-webkit-details-marker{display:none}.mobile-menu summary:after{content:"＋";margin-left:8px;font-family:var(--mono)}.mobile-menu[open] summary:after{content:"−"}
.skip{position:absolute;left:-9999px;top:8px;z-index:20;background:var(--ink);color:var(--paper);padding:8px 14px;border-radius:8px}
.skip:focus{left:8px}
.wrap{width:min(100% - var(--gut)*2,var(--max));margin-inline:auto}
.mono{font-family:var(--mono);font-feature-settings:normal;letter-spacing:0}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1}

/* header */
.site-head{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--paper) 88%,transparent);backdrop-filter:saturate(1.4) blur(10px);-webkit-backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.nav{display:flex;align-items:center;gap:20px;min-height:64px}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:-.02em;text-decoration:none;font-size:17px;white-space:nowrap}
.mark{width:26px;height:26px;border-radius:7px;background:var(--ink);display:grid;place-items:center}
.mark i{display:block;width:12px;height:12px;border-radius:50%;border:2.5px solid var(--paper);border-right-color:var(--signal)}
.links{display:flex;gap:4px;margin-left:auto;font-size:14px}
.links a{text-decoration:none;color:var(--ink-2);padding:8px 10px;border-radius:8px}
.links a:hover{background:var(--paper-2);color:var(--ink)}.links a.active{color:var(--ink);background:var(--paper-2);box-shadow:inset 0 -2px 0 var(--signal)}
.nav .btn{min-height:40px;padding:8px 16px;font-size:14px}
.mobile-menu{display:none}

/* buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;min-height:52px;padding:12px 22px;border-radius:999px;border:1.5px solid var(--ink);background:transparent;color:var(--ink);font:inherit;font-weight:700;font-size:15px;line-height:1.3;text-decoration:none;cursor:pointer;transition:background .2s,color .2s,transform .2s}
.btn:hover{background:var(--ink);color:var(--paper)}
.btn.primary{background:var(--signal);border-color:var(--signal);color:#fff}
.btn.primary:hover{background:var(--signal-ink);border-color:var(--signal-ink)}
.btn .arr{transition:transform .2s}.btn:hover .arr{transform:translateX(3px)}
.btn[disabled]{opacity:.45;cursor:not-allowed}
.textlink{font-weight:700;text-decoration:underline;text-decoration-thickness:1.5px}

/* type */
h1,h2,h3{font-weight:800;letter-spacing:-.035em;margin:0;line-height:1.12;word-break:auto-phrase}
.ln{display:inline-block}
p,li,dd,.badge,.cap{word-break:auto-phrase}
h1{font-size:clamp(36px,10vw,124px);line-height:1.02;letter-spacing:-.06em}
h2{font-size:clamp(30px,4.6vw,58px);letter-spacing:-.045em}
h3{font-size:19px;letter-spacing:-.02em;line-height:1.4}
p{margin:0 0 14px}
.lead{font-size:clamp(16px,1.6vw,19px);color:var(--ink-2);max-width:34em;line-height:1.85}
.muted{color:var(--ink-3)}.small{font-size:13px;line-height:1.7}
.kicker{display:inline-flex;align-items:center;gap:10px;font-size:13px;font-weight:700;letter-spacing:.04em;color:var(--ink-2)}
.kicker:before{content:"";width:8px;height:8px;border-radius:50%;background:var(--signal)}
.sec-head{display:grid;grid-template-columns:minmax(0,8fr) minmax(0,4fr);gap:clamp(20px,5vw,80px);align-items:end;margin-bottom:clamp(32px,5vw,64px)}
.sec-head .lead{margin:0}
.sec-no{font-family:var(--mono);font-size:12px;color:var(--ink-3);letter-spacing:.08em;display:block;margin-bottom:18px}

/* layout */
.section{padding:clamp(72px,10vw,140px) 0;border-top:1px solid var(--line)}
.section.night{background:var(--night);color:var(--night-ink);border-top:0}
.night .lead,.night .muted{color:var(--night-mute)}.night .kicker,.night .sec-no{color:var(--night-mute)}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:clamp(18px,2.4vw,28px);min-width:0}
.card p:last-child{margin-bottom:0}
.actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:28px}

/* hero */
.hero{padding:clamp(40px,6vw,88px) 0 clamp(56px,8vw,112px);display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:clamp(28px,4vw,56px) clamp(32px,5vw,72px);align-items:start}
.hero-title{grid-column:1/-1}
@media (min-width:1021px){.hero{grid-template-columns:minmax(0,1fr) minmax(0,1.08fr);grid-template-areas:"title console" "copy console";align-items:start}.hero-title{grid-area:title}.hero-copy{grid-area:copy}.hero .console{grid-area:console;align-self:center}.hero h1{font-size:clamp(48px,5.2vw,80px)}}
.hero-copy{padding-top:8px}
.hero h1 em{font-style:normal;color:var(--signal)}
.hero .lead{margin-top:0}
.hero-note{margin-top:18px;font-size:13px;color:var(--ink-3);display:flex;gap:16px;flex-wrap:wrap}.hero-signal-tape{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin-top:14px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--line)}.hero-signal-tape span{background:var(--card);padding:10px 11px;font-size:10.5px;line-height:1.45;color:var(--ink-3)}.hero-signal-tape b{display:block;font-family:var(--mono);font-size:9px;letter-spacing:.06em;color:var(--signal-ink);margin-bottom:3px}
.hero-note span:before{content:"✓ ";color:var(--go);font-weight:800}.signal-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px}.signal-chip{border-top:1px solid var(--line);padding-top:10px;display:grid;gap:2px}.signal-chip strong{font-family:var(--mono);font-size:11px;letter-spacing:.05em}.signal-chip span{font-size:11px;color:var(--ink-3);line-height:1.45}.signal-chip em{font-style:normal;color:var(--signal-ink)}.proof-rail{margin-top:24px;display:flex;align-items:center;gap:12px;max-width:560px;padding:12px 14px;border:1px solid var(--line);border-radius:14px;background:rgba(251,250,246,.72);box-shadow:0 12px 30px -26px rgba(18,18,17,.55)}.proof-rail div{display:grid;gap:0;min-width:58px}.proof-rail strong{font-family:var(--mono);font-size:22px;line-height:1}.proof-rail span{font-size:10px;color:var(--ink-3);letter-spacing:.04em}.proof-rail i{font-style:normal;color:var(--signal-ink);font-family:var(--mono)}.proof-rail p{margin:0 0 0 4px;padding-left:12px;border-left:1px solid var(--line);font-size:11px;line-height:1.5;color:var(--ink-3)}

/* console (hero demo) */
.console{background:var(--night);color:var(--night-ink);border-radius:20px;padding:0;overflow:hidden;box-shadow:0 1px 0 rgba(0,0,0,.04),0 30px 60px -30px rgba(18,18,17,.55)}
.console-top{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid var(--night-line);font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--night-mute);text-transform:uppercase}
.signal{display:inline-flex;align-items:center;gap:8px}
.console-top{flex-wrap:wrap;row-gap:8px}.console-top>*,.console-meta>*{white-space:nowrap}
.console-meta{display:inline-flex;align-items:center;gap:12px;margin-left:auto}
.autoplay{appearance:none;font:inherit;letter-spacing:inherit;text-transform:none;color:var(--night-ink);background:transparent;border:1px solid var(--night-line);border-radius:999px;min-height:28px;padding:2px 12px;cursor:pointer}
.autoplay:hover{border-color:var(--night-mute)}.sample-badge{display:inline-flex;align-items:center;min-height:28px;padding:2px 9px;border:1px solid var(--night-line);border-radius:999px;background:rgba(255,255,255,.025)}
.autoplay[hidden]{display:none}.signal:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--signal)}
.stages{display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid var(--night-line)}
.stage{appearance:none;background:none;border:0;border-right:1px solid var(--night-line);color:var(--night-mute);font:inherit;font-size:12px;padding:12px 6px 11px;cursor:pointer;text-align:center;position:relative;line-height:1.3}
.stage:last-child{border-right:0}
.stage b{display:block;font-family:var(--mono);font-size:10px;font-weight:400;letter-spacing:.08em;margin-bottom:2px}
.stage[aria-selected=true]{color:var(--night-ink);background:var(--night-2)}
.stage[aria-selected=true]:after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--signal)}
.stage .prog{position:absolute;left:0;bottom:-1px;height:2px;width:0;background:rgba(226,67,26,.45)}
.panel{padding:22px 20px 24px;min-height:318px}
.js .panel{display:none}.js .panel.on{display:block;animation:fade .45s ease both}
.panel h2{margin:0 0 4px;font-size:15px;font-weight:700;letter-spacing:-.01em}
.panel .cap{font-size:12.5px;color:var(--night-mute);margin:0 0 18px;line-height:1.6}
.rows{display:grid;gap:10px}
.row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 14px;align-items:center;font-size:13.5px}
.row .lbl{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .val{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:13px;color:var(--night-ink)}
.bar{grid-column:1/-1;height:6px;border-radius:99px;background:var(--night-line);overflow:hidden}
.bar i{display:block;height:100%;border-radius:inherit;background:var(--night-mute);transform-origin:left;animation:grow .9s cubic-bezier(.2,.7,.2,1) both}
.bar i.hot{background:var(--signal)}
.rg{position:relative}.rg i{position:absolute;top:0;bottom:0}.rg-a{left:27%;width:54%}.rg-r{left:31%;width:69%}.rg-y{left:25%;width:50%}
.scale{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10px;color:var(--night-mute);margin-top:4px}
.w100{width:100%}.w92{width:92%}.w84{width:84%}.w38{width:38%}.w24{width:24%}.w17{width:17%}.w12{width:12%}
.cands{display:grid;gap:8px}
.cand{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 12px;border:1px solid var(--night-line);border-radius:10px;font-size:13px}
.cand.dim{opacity:.38;text-decoration:line-through;text-decoration-color:var(--night-mute)}
.cand .mp{font-family:var(--mono);font-size:10px;letter-spacing:.06em;color:var(--night-mute);border:1px solid var(--night-line);border-radius:6px;padding:2px 6px}
.cand .tag{font-family:var(--mono);font-size:11px;color:var(--signal-dk)}
.spark{width:100%;height:auto;display:block;margin:4px 0 14px}
.spark .area{fill:rgba(226,67,26,.12)}.spark .ln{fill:none;stroke:var(--night-ink);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.spark .avg{stroke:var(--night-mute);stroke-dasharray:4 5;stroke-width:1}.spark .dot{fill:var(--signal)}
.spark text{fill:var(--night-mute);font-family:var(--mono);font-size:10px}
.kv{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.kv div{border:1px solid var(--night-line);border-radius:10px;padding:10px 12px}
.kv small{display:block;font-size:10.5px;color:var(--night-mute);font-family:var(--mono);letter-spacing:.04em}
.kv strong{font-family:var(--mono);font-size:16px;font-weight:600}
.verdict{border:1px solid var(--signal);border-radius:12px;padding:16px;margin-top:4px}
.verdict .big{font-family:var(--mono);font-size:clamp(30px,4vw,40px);font-weight:600;letter-spacing:-.02em;line-height:1.1}
.verdict ul{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:6px;font-size:13px}
.verdict li{display:flex;justify-content:space-between;gap:12px;border-top:1px solid var(--night-line);padding-top:6px}
.verdict li span:last-child{font-family:var(--mono);text-align:right}
.console-foot{padding:11px 18px;border-top:1px solid var(--night-line);font-size:11px;color:var(--night-mute);font-family:var(--mono);display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}.console-hint{color:var(--night-ink)}

/* problem */
.pains{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1.5px solid var(--ink)}
.pain{padding:28px 28px 8px 0;border-right:1px solid var(--line)}
.pain+.pain{padding-left:28px}.pain:last-child{border-right:0}
.pain .verb{font-size:clamp(44px,5.4vw,72px);font-weight:800;letter-spacing:-.06em;line-height:1;margin:0 0 18px}
.pain .now{color:var(--ink-2)}
.pain .then{margin-top:18px;padding-top:14px;border-top:1px dashed var(--line-2);font-weight:700}
.pain .then:before{content:"EC Pulse → ";font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--signal-ink);font-weight:400;display:block}.outcome-line{display:flex;align-items:center;gap:12px;margin-top:12px;padding:10px 12px;border-top:1px solid var(--line);font-family:var(--mono);font-size:10px;color:var(--ink-3);letter-spacing:.03em}.outcome-line span{display:flex;gap:6px;align-items:baseline}.outcome-line b{font-family:var(--sans);font-size:12px;color:var(--ink-2);letter-spacing:0}.outcome-line i{font-style:normal;color:var(--signal-ink)}.friction-note{margin-top:28px;padding:14px 16px;border:1px dashed var(--line-2);border-radius:12px;display:flex;justify-content:space-between;gap:16px;align-items:baseline;background:var(--card)}.friction-note strong{font-family:var(--mono);font-size:12px;color:var(--signal-ink)}.friction-note span{font-size:13px;color:var(--ink-2)}

/* discovery */
.compare{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);gap:16px}
.flow{border:1px solid var(--night-line);border-radius:18px;padding:clamp(20px,3vw,32px)}
.flow.new{border-color:var(--signal);background:linear-gradient(180deg,rgba(226,67,26,.08),transparent 60%)}
.flow h3{font-size:15px;font-weight:700;letter-spacing:.02em;color:var(--night-mute);margin-bottom:20px}
.flow.new h3{color:var(--night-ink)}
.flow ol{list-style:none;margin:0;padding:0;display:grid;gap:0}
.flow li{display:grid;grid-template-columns:30px minmax(0,1fr);gap:14px;padding:13px 0;border-top:1px solid var(--night-line);align-items:baseline}
.flow li b{font-family:var(--mono);font-size:11px;color:var(--night-mute);font-weight:400}
.flow li span{font-size:16px}.flow li em{justify-self:start;font-family:var(--mono);font-size:9px;letter-spacing:.06em;color:var(--signal-dk);border:1px solid var(--night-line);border-radius:999px;padding:2px 6px;font-style:normal}
.flow.old li span{color:var(--night-mute)}
.flow.old .who{color:var(--night-ink)}
.flow.new li{transition:color .4s,opacity .4s}
.js .flow.new li{opacity:.28}.js .flow.new li.lit{opacity:1}
.flow.new li.end span{font-weight:800;color:var(--signal-dk)}
.flow .foot{margin:18px 0 0;font-size:13px;color:var(--night-mute)}.decision-path{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:16px}.decision-path div{border:1px solid var(--night-line);border-radius:12px;padding:12px}.decision-path b{display:block;font-family:var(--mono);font-size:10px;color:var(--night-mute);margin-bottom:5px}.decision-path span{font-size:13px}.decision-path .last{border-color:var(--signal)}

/* how / steps */
.steps{list-style:none;margin:0;padding:0;border-top:1.5px solid var(--ink)}
.step{display:grid;grid-template-columns:44px minmax(0,.8fr) minmax(0,1.3fr) minmax(0,1.25fr);gap:clamp(14px,3vw,40px);padding:clamp(22px,3vw,34px) 0;border-bottom:1px solid var(--line);align-items:start}
.step .no{font-family:var(--mono);font-size:13px;color:var(--signal-ink)}
.step h3{font-size:clamp(20px,2.2vw,26px)}
.step p{color:var(--ink-2);margin:0}
.step .api{display:grid;gap:6px;font-family:var(--mono);font-size:12px}
.step .api code{background:var(--paper-2);border-radius:6px;padding:3px 8px;width:fit-content;max-width:100%;white-space:nowrap;font-size:11.5px;overflow:hidden;text-overflow:ellipsis}
.step .api span{color:var(--ink-3)}.usecases{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:28px}.usecase{border:1px solid var(--line);border-radius:14px;padding:16px;background:var(--card);transition:transform .2s,box-shadow .2s,border-color .2s}.usecase:hover{transform:translateY(-3px);border-color:var(--line-2);box-shadow:0 18px 38px -30px rgba(18,18,17,.55)}.usecase b{font-family:var(--mono);font-size:10px;color:var(--signal-ink);letter-spacing:.06em}.usecase h3{font-size:16px;margin-top:7px}.usecase p{font-size:13px;color:var(--ink-2);margin:6px 0 0}.usecase a{display:inline-flex;gap:5px;margin-top:11px;font-family:var(--mono);font-size:10px;color:var(--signal-ink);text-decoration:none}.usecase a:hover{text-decoration:underline}

/* output card */
.output{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,.9fr);gap:clamp(24px,4vw,56px);align-items:start}
.decision{background:var(--card);border:1.5px solid var(--ink);border-radius:20px;overflow:hidden}
.decision header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 20px;background:var(--ink);color:var(--paper);font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.decision .prod{padding:20px 20px 4px}.evidence-strip{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:9px 20px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-family:var(--mono);font-size:10px;letter-spacing:.04em;color:var(--ink-3)}.evidence-strip span:first-child{color:var(--signal-ink);font-weight:700}
.decision .prod h3{font-size:clamp(20px,2.4vw,26px)}
.drow{display:grid;grid-template-columns:150px minmax(0,1fr);gap:16px;padding:16px 20px;border-top:1px solid var(--line);align-items:baseline}
.drow dt{font-family:var(--mono);font-size:11.5px;letter-spacing:.05em;color:var(--ink-3);text-transform:uppercase}
.drow dd{margin:0;font-size:15px}
.drow dd strong{font-family:var(--mono);font-size:22px;font-weight:600;letter-spacing:-.01em}
.drow.key{background:var(--signal-soft)}.drow.key dt,.drow.key .muted{color:var(--ink-2)}
.drow.key dd strong{color:var(--signal-ink);font-size:clamp(26px,3vw,34px)}
.pill{display:inline-block;font-family:var(--mono);font-size:11px;border-radius:99px;padding:2px 9px;border:1px solid currentColor;margin-left:8px;vertical-align:2px}
.pill.go{color:var(--go)}.pill.sig{color:var(--signal-ink)}
.map{list-style:none;margin:0;padding:0;display:grid;gap:0;border-top:1.5px solid var(--ink)}
.map li{display:grid;grid-template-columns:minmax(0,1fr);gap:4px;padding:16px 0;border-bottom:1px solid var(--line)}
.map li b{font-size:15px}
.map li code{font-family:var(--mono);font-size:12px;color:var(--ink-2);overflow-wrap:anywhere}
 .lineage{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1.2fr;align-items:center;gap:7px;margin-top:14px;padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:var(--paper-2);font-family:var(--mono);font-size:9px;letter-spacing:.05em;color:var(--ink-3)}.lineage strong{color:var(--signal-ink)}.lineage i{font-style:normal;color:var(--line-2)}.disclaim{margin-top:18px;font-size:13px;color:var(--ink-3)}.provenance{margin-top:16px;border:1px solid var(--line);border-radius:14px;padding:15px 16px;background:var(--paper-2)}.provenance-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:8px}.provenance-head b{font-family:var(--mono);font-size:10px;letter-spacing:.07em;color:var(--signal-ink)}.provenance-head span{font-size:11px;color:var(--ink-3)}.provenance p{font-size:13px;color:var(--ink-2);margin:0}.provenance code{font-size:11px}

/* FAQ */
.faq{display:grid;gap:0;border-top:1.5px solid var(--ink)}
.faq details{border-bottom:1px solid var(--line);padding:0}
.faq summary{list-style:none;cursor:pointer;padding:22px 42px 22px 0;position:relative;font-weight:800;font-size:17px}
.faq summary::-webkit-details-marker{display:none}
.faq summary:after{content:"＋";position:absolute;right:0;top:20px;font-family:var(--mono);font-weight:400;color:var(--signal-ink)}
.faq details[open] summary:after{content:"−"}
.faq .answer{padding:0 42px 24px 0;color:var(--ink-2);max-width:72ch}
.faq .answer p:last-child{margin-bottom:0}

/* calculator */
.calc{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:16px}
.calc form{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:clamp(20px,3vw,32px);display:grid;gap:16px;align-content:start}.calc .result{display:none}.js .calc .result{display:grid}
.field{display:grid;grid-template-columns:minmax(0,1fr) 150px;gap:14px;align-items:center}
.field label{font-weight:700;font-size:15px;line-height:1.4}
.field label small{display:block;font-weight:400;color:var(--ink-3);font-size:12px}
.inp{display:flex;align-items:center;border:1.5px solid var(--line-2);border-radius:12px;background:#fff;overflow:hidden}
.inp:focus-within{border-color:var(--ink);box-shadow:0 0 0 3px var(--signal-soft)}.inp:has(input[aria-invalid=true]){border-color:var(--signal);background:#fff6f2}
.inp span{padding:0 10px;color:var(--ink-3);font-family:var(--mono);font-size:13px}
.inp input{border:0;outline:0;width:100%;min-height:46px;padding:0 10px;font-family:var(--mono);font-size:17px;text-align:right;background:transparent;color:var(--ink);font-variant-numeric:tabular-nums}
.calc form hr{border:0;border-top:1px dashed var(--line-2);margin:4px 0}.calc-assumption{display:flex;gap:8px;align-items:flex-start;padding:10px 12px;border-radius:10px;background:var(--paper-2);font-size:11px;color:var(--ink-3);line-height:1.55}.calc-assumption b{font-family:var(--mono);color:var(--signal-ink);white-space:nowrap}.presets{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.presets span{font-size:11px;color:var(--ink-3);font-family:var(--mono)}.presets button{appearance:none;border:1px solid var(--line-2);background:var(--paper-2);color:var(--ink-2);border-radius:999px;padding:6px 10px;font:inherit;font-size:11px;cursor:pointer}.presets button:hover,.presets button:focus-visible{border-color:var(--signal);color:var(--signal-ink);background:var(--signal-soft)}
.result{background:var(--night);color:var(--night-ink);border-radius:20px;padding:clamp(22px,3.4vw,40px);display:grid;gap:22px;align-content:start}
.result .label{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--night-mute)}
.result .ceiling{font-family:var(--mono);font-size:clamp(48px,7vw,88px);font-weight:600;letter-spacing:-.04em;line-height:1;font-variant-numeric:tabular-nums}
.result .ceiling.neg{color:#ff8a6b}
.result .msg{font-size:15px;color:var(--night-mute);margin:0}.result .muted{color:var(--night-mute)}
.stack{display:flex;height:16px;border-radius:99px;overflow:hidden;background:var(--night-line)}
.stack i{display:block;height:100%;transition:width .5s cubic-bezier(.2,.7,.2,1)}
.s-fee{background:#6b6860}.s-ship{background:#8f8b80}.s-profit{background:var(--go)}.s-buy{background:var(--signal)}
.legend{list-style:none;margin:0;padding:0;display:grid;gap:8px;font-size:14px}
.legend li{display:grid;grid-template-columns:12px minmax(0,1fr) auto;gap:10px;align-items:center}
.legend li i{width:12px;height:12px;border-radius:3px}
.legend li span:last-child{font-family:var(--mono);font-variant-numeric:tabular-nums}
.check{border-top:1px solid var(--night-line);padding-top:18px;display:grid;gap:8px}
.check .row2{display:flex;justify-content:space-between;gap:12px;font-size:14px}
.check .row2 span:last-child{font-family:var(--mono)}
.badge{display:inline-flex;align-items:center;gap:8px;font-weight:700;font-size:15px;border-radius:10px;padding:10px 14px}
.badge.ok{background:rgba(23,112,74,.18);color:#7fe0ad}.badge.ng{background:rgba(226,67,26,.18);color:#ff9d80}

/* pricing */
.plans{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:stretch}
.plan{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);border-radius:20px;padding:clamp(22px,3vw,32px)}
.plan.featured{border:1.5px solid var(--ink);box-shadow:0 24px 50px -32px rgba(18,18,17,.45)}
.plan .for{font-size:14px;color:var(--ink-2);margin:6px 0 22px;min-height:3.4em}
.plan .price{font-family:var(--mono);font-size:clamp(28px,3vw,36px);font-weight:600;letter-spacing:-.02em;margin:0}
.plan .price.tbd{font-family:var(--sans);font-size:15px;font-weight:700;letter-spacing:0;line-height:1.6;padding:6px 0 4px;color:var(--ink-2)}
.plan .price small{font-size:13px;color:var(--ink-3);font-weight:400;letter-spacing:0;margin-left:4px}
.plan ul{list-style:none;padding:0;margin:20px 0 26px;display:grid;gap:10px;font-size:14.5px}
.plan li{display:grid;grid-template-columns:18px minmax(0,1fr);gap:8px}
.plan li:before{content:"—";color:var(--signal-ink);font-family:var(--mono)}
.plan .btn{margin-top:auto;width:100%}.plan-note{margin-top:10px;font-size:11px;color:var(--ink-3);line-height:1.5}.plan.featured .plan-note{color:var(--ink-2)}
.fit-guide{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:16px}.fit-guide span{border-top:1px solid var(--line);padding:10px 2px 0;font-size:12px;color:var(--ink-2)}.fit-guide b{display:block;font-family:var(--mono);font-size:9px;letter-spacing:.06em;color:var(--signal-ink);margin-bottom:3px}.tagline{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--signal-ink)}

/* developers */
.dev{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.15fr);gap:clamp(24px,4vw,56px);align-items:start}
.dev ol{margin:0;padding:0;list-style:none;counter-reset:s;display:grid;gap:22px}
.dev ol li{counter-increment:s;display:grid;grid-template-columns:40px minmax(0,1fr);gap:14px}
.dev ol li:before{content:counter(s,decimal-leading-zero);font-family:var(--mono);font-size:13px;color:var(--signal-dk);padding-top:3px}
.dev ol li p{margin:4px 0 0;color:var(--night-mute);font-size:14.5px}
pre,code{font-family:var(--mono);font-size:13px}
pre{background:#0a0a09;color:#ecebe4;border:1px solid var(--night-line);border-radius:14px;padding:18px 20px;overflow-x:auto;margin:0;line-height:1.7}
code{background:var(--paper-2);border-radius:5px;padding:1px 6px}
pre code,.night code{background:none;padding:0}
.night code{color:var(--night-ink)}
pre .c{color:#8d8a80}pre .k{color:#ff9d80}.code-shell{position:relative}.code-copy{position:absolute;right:10px;top:10px;z-index:1;border:1px solid var(--night-line);background:var(--night);color:var(--night-ink);border-radius:999px;padding:6px 10px;font:inherit;font-family:var(--mono);font-size:10px;cursor:pointer}.code-copy:hover{border-color:var(--night-mute)}
.response-preview{display:grid;gap:6px;margin-top:12px;padding:12px 14px;border:1px solid var(--night-line);border-radius:12px;background:var(--night-2)}.response-preview span{font-family:var(--mono);font-size:9px;letter-spacing:.07em;color:var(--night-mute)}.response-preview code{font-size:12px;color:var(--night-ink);overflow-wrap:anywhere}.response-preview small{font-size:10px;color:var(--night-mute)}.errs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:var(--night-line);border:1px solid var(--night-line);border-radius:14px;overflow:hidden;margin-top:16px}
.errs div{background:var(--night);padding:14px 16px;font-size:13px;color:var(--night-mute)}.dev-next{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:12px;padding:12px 14px;border:1px solid var(--night-line);border-radius:12px;background:var(--night-2);font-size:12px;color:var(--night-mute)}.dev-next b{color:var(--night-ink);font-family:var(--mono);font-size:10px;letter-spacing:.05em}
.errs b{display:block;font-family:var(--mono);font-size:15px;color:var(--night-ink);font-weight:600}

/* trust */
.trust{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:0;border-top:1.5px solid var(--ink)}
.trust div{padding:24px 24px 8px 0;border-right:1px solid var(--line)}
.trust div+div{padding-left:24px}.trust div:last-child{border-right:0}
.trust h3{font-size:17px;margin-bottom:10px}
.trust p{color:var(--ink-2);font-size:14.5px}

/* final */
.final{padding:clamp(80px,11vw,160px) 0;text-align:left}
.final h2{font-size:clamp(36px,6.4vw,88px);max-width:12em}
.final .actions{margin-top:36px}.final-reassure{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0 0;font-family:var(--mono);font-size:9px;letter-spacing:.05em;color:var(--ink-3)}.final-reassure span{padding:5px 8px;border:1px solid var(--line);border-radius:999px;background:var(--card)}.final-path{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;max-width:780px;margin-top:30px}.final-path div{border-top:1px solid var(--line);padding-top:12px}.final-path b{font-family:var(--mono);font-size:10px;color:var(--signal-ink)}.final-path span{display:block;font-size:13px;color:var(--ink-2);margin-top:4px}

/* tables / misc shared */
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:11px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--ink-3);font-weight:600;font-family:var(--mono);font-size:12px;letter-spacing:.04em}
.table-scroll{overflow-x:auto}
.footer{padding:40px 0 56px;border-top:1px solid var(--line);color:var(--ink-3);font-size:13px;display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}
.footer nav{display:flex;gap:6px 18px;flex-wrap:wrap}
.footer a{text-decoration:none;display:inline-block;padding:4px 0}.footer a:hover{text-decoration:underline}.footer-signal{display:inline-flex;align-items:center;gap:5px;margin-left:8px;font-family:var(--mono);font-size:10px;letter-spacing:.05em;color:var(--signal-ink)}.footer-signal:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--signal)}
mark.legal-input{background:#fbf3dc;color:#5a4610;border:1px dashed #c9a94e;border-radius:4px;padding:0 3px}
.notice{border:1px solid #e4cf98;background:#fbf3dc;color:#5a4610;border-radius:12px;padding:12px 14px;font-size:14px}
.error{border-color:#efb8a8;background:#fbe7e1;color:#7b230b}
.ok{border-color:#b6dcc4;background:#e3f2e8;color:#14532f}
.stat{font-family:var(--mono);font-size:30px;font-weight:600;letter-spacing:-.02em}
.keybox{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.keybox code{word-break:break-all;font-size:14px;padding:8px 10px;background:#fff}
input[type=password],input[type=text]{width:100%;min-height:48px;padding:10px 14px;border-radius:12px;border:1.5px solid var(--line-2);background:#fff;color:var(--ink);font:inherit}
.hidden{display:none !important}
.doc{max-width:900px;padding:48px 0 88px}.account-page{padding-top:clamp(42px,7vw,82px);padding-bottom:88px}.account-head{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(280px,.85fr);gap:32px 72px;align-items:end;padding-bottom:38px;border-bottom:1px solid var(--line)}.account-head h1 em{font-style:normal;color:var(--signal)}.account-head .lead{margin:0 0 5px}.account-status{margin-top:18px}.signed-out{display:flex;justify-content:space-between;align-items:end;gap:24px;padding:28px}.section-label{display:flex;justify-content:space-between;align-items:center;gap:16px}.billing-card{scroll-margin-top:88px}.not-found{min-height:58vh;display:flex;flex-direction:column;justify-content:center}.not-found-code{font-family:var(--mono);font-size:clamp(88px,18vw,190px);font-weight:600;letter-spacing:-.08em;line-height:.85;color:var(--signal);margin-bottom:24px}.not-found h1 em{font-style:normal;color:var(--signal)}.doc-crumb{display:flex;gap:9px;align-items:center;color:var(--ink-3);font-size:13px;margin-bottom:34px}.doc-crumb a{font-weight:700;text-decoration:none}.doc-head{padding-bottom:34px;border-bottom:1px solid var(--line)}.doc-head h1{font-size:clamp(34px,6vw,64px);margin-top:16px;max-width:14ch}.doc-head .lead{margin-top:18px}.doc-content{max-width:780px;padding:34px 0}.doc-content h1{font-size:30px;margin:0 0 18px}.doc-content h2{font-size:25px;margin:42px 0 14px}.doc-content h3{font-size:19px;margin:30px 0 10px}.doc-content p{color:var(--ink-2);margin:0 0 16px}.doc-content blockquote{margin:0 0 24px;padding:14px 18px;border-left:3px solid var(--signal);background:var(--signal-soft);border-radius:0 12px 12px 0;color:var(--ink-2)}.doc-content ul{padding-left:22px;color:var(--ink-2)}.doc-content code{background:var(--paper-2);padding:2px 6px;border-radius:5px}.legal-table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}.legal-table th,.legal-table td{padding:12px 14px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.legal-table th{font-size:12px;font-family:var(--mono);letter-spacing:.05em;background:var(--paper-2)}.legal-table tr:last-child td{border-bottom:0}.doc-actions{border-top:1px solid var(--line);padding-top:24px;display:flex;gap:10px;flex-wrap:wrap}
.cta-card{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}
.h-sm{font-size:22px}.h-page{font-size:clamp(30px,5vw,48px)}.page-pad{padding:32px 0 72px}.break{word-break:break-all}
.mb8{margin-bottom:8px}.mt10{margin-top:10px}.mt12{margin-top:12px}.mt14{margin-top:14px}.mt16{margin-top:16px}.mt18{margin-top:18px}.mt20{margin-top:20px}.mt22{margin-top:22px}.m006{margin:0 0 6px}.m0{margin:0}

@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes prog{from{width:0}to{width:100%}}
@media (prefers-reduced-motion:reduce){*,*:before,*:after{animation:none !important;transition:none !important;scroll-behavior:auto !important}.js .flow.new li{opacity:1}}

@media (max-width:1020px){
  .hero{grid-template-columns:minmax(0,1fr)}
  .sec-head{grid-template-columns:minmax(0,1fr);align-items:start}
  .output,.calc,.dev{grid-template-columns:minmax(0,1fr)}
  .step{grid-template-columns:52px minmax(0,1fr) minmax(0,1.2fr)}
  .step .api{grid-column:2/-1}
  .trust{grid-template-columns:repeat(2,minmax(0,1fr))}
  .trust div:nth-child(2){border-right:0}.trust div:nth-child(3){padding-left:0}
}
@media (max-width:760px){
  .links{display:none}
  .mobile-menu{display:block;margin-left:auto}
  .mobile-menu summary{list-style:none;cursor:pointer;border:1px solid var(--line-2);border-radius:999px;padding:0 14px;min-height:40px;display:flex;align-items:center;font-size:13px;font-weight:700;background:var(--card);white-space:nowrap}
 .mobile-menu summary::-webkit-details-marker{display:none}
  .mobile-menu-panel{position:absolute;left:var(--gut);right:var(--gut);top:calc(100% + 8px);max-height:calc(100vh - 96px);overflow-y:auto;padding:8px;background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 20px 45px -24px rgba(18,18,17,.5);display:grid;gap:2px}
  .mobile-menu-panel a{padding:12px 14px;min-height:44px;display:flex;align-items:center;border-radius:10px;text-decoration:none;font-weight:700}
  .mobile-menu-panel a:hover{background:var(--paper-2)}
  .mobile-menu summary:after{content:"＋";font-family:var(--mono);margin-left:7px}.mobile-menu[open] summary:after{content:"−"}
  .nav .nav-cta{margin-left:0;min-height:40px;padding:8px 12px;font-size:12px;white-space:nowrap}
  .brand{font-size:15px;gap:7px}.mark{width:24px;height:24px}.nav{gap:8px}
  .grid,.grid.two,.plans,.pains,.compare,.trust,.errs{grid-template-columns:minmax(0,1fr)}
  .pain,.pain+.pain,.trust div,.trust div+div{padding:22px 0 6px;border-right:0;border-bottom:1px solid var(--line)}
  .step{grid-template-columns:minmax(0,1fr);gap:10px}
  .step .api{grid-column:auto}
  .step .api code{white-space:normal;overflow-wrap:anywhere}
  .drow{grid-template-columns:minmax(0,1fr);gap:4px}
  .field{grid-template-columns:minmax(0,1fr) 128px}
  .stage{font-size:11px;padding:10px 2px}
  .stage b{font-size:9px}
  .panel{padding:18px 16px 20px;min-height:0}
  .kv{grid-template-columns:repeat(3,minmax(0,1fr))}
  .kv strong{font-size:14px}
  .actions .btn{flex:1 1 100%}
  .account-head{grid-template-columns:minmax(0,1fr);gap:18px}.signed-out{display:grid;align-items:start}.account-page{padding-top:34px}
  .plan .for{min-height:0}
}
@media (max-width:359px){
  .brand{font-size:14px;gap:6px}.mobile-menu summary{padding:0 10px}.mobile-menu summary:after{margin-left:5px}.nav .nav-cta{padding:8px 10px}
  .section h2,.final h2{font-size:26px}
}

/* award-level experience layer: restrained motion, depth and editorial craft */
:root{--scroll:0}
body:before{content:"";position:fixed;inset:0;pointer-events:none;z-index:-1;background:radial-gradient(circle at 12% 8%,rgba(210,60,20,.07),transparent 26%),radial-gradient(circle at 88% 34%,rgba(23,112,74,.045),transparent 24%);opacity:.9}
.site-head:after{content:"";position:absolute;left:0;bottom:-1px;width:calc(var(--scroll)*100%);height:2px;background:var(--signal);transform-origin:left}
.brand{transition:transform .25s ease}.brand:hover{transform:translateY(-1px)}
.mark{position:relative;overflow:hidden;box-shadow:0 0 0 1px rgba(255,255,255,.05) inset}.mark:after{content:"";position:absolute;inset:-80%;background:linear-gradient(115deg,transparent 42%,rgba(255,255,255,.22) 50%,transparent 58%);transform:translateX(-45%) rotate(8deg);transition:transform .7s ease}.brand:hover .mark:after{transform:translateX(45%) rotate(8deg)}
.hero{position:relative}.hero:before{content:"";position:absolute;inset:0;pointer-events:none;background-image:linear-gradient(to right,rgba(18,18,17,.045) 1px,transparent 1px),linear-gradient(to bottom,rgba(18,18,17,.035) 1px,transparent 1px);background-size:64px 64px;mask-image:linear-gradient(to bottom,black,transparent 72%);opacity:.45}
.hero-title,.hero-copy,.console{position:relative;z-index:1}
.hero-title h1{max-width:12ch;text-wrap:balance}
.hero h1 em{text-shadow:0 0 36px rgba(210,60,20,.13)}
.console{transform:perspective(1400px) rotateX(.4deg);transition:transform .6s cubic-bezier(.2,.7,.2,1),box-shadow .6s ease}
.console:hover{transform:perspective(1400px) rotateX(0) translateY(-4px);box-shadow:0 36px 80px -34px rgba(18,18,17,.62)}
.section{position:relative;isolation:isolate}
.section>.wrap{position:relative}
.sec-head h2{max-width:15ch;text-wrap:balance}
.btn{will-change:transform}.btn:active{transform:translateY(1px) scale(.985)}
.card,.plan,.decision,.flow,.calc form,.result{transition:transform .35s ease,box-shadow .35s ease,border-color .35s ease}
.card:hover,.plan:hover{transform:translateY(-3px);box-shadow:0 18px 42px -30px rgba(18,18,17,.5)}
.js .section .sec-head,.js .section .pains,.js .section .compare,.js .section .steps,.js .section .output,.js .section .calc,.js .section .plans,.js .section .dev,.js .section .trust,.js .section .cta-card{opacity:0;transform:translateY(18px)}
.js .reveal-in{opacity:1 !important;transform:none !important;transition:opacity .75s ease,transform .75s cubic-bezier(.2,.7,.2,1)}
.js .hero-title{animation:heroIn .9s cubic-bezier(.2,.7,.2,1) .05s forwards}.js .hero-copy{animation:heroIn .9s cubic-bezier(.2,.7,.2,1) .18s forwards}.js .console{animation:heroIn .9s cubic-bezier(.2,.7,.2,1) .3s forwards}
@keyframes heroIn{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){body:before{display:none}.console{transform:none}.card,.plan{transition:none}.js .hero-title,.js .hero-copy,.js .console{animation:none;opacity:1;transform:none}}
@media (max-width:760px){.hero:before{background-size:42px 42px;opacity:.28}.console:hover{transform:none}.card:hover,.plan:hover{transform:none;box-shadow:none}.hero-signal-tape,.fit-guide,.signal-grid,.decision-path,.usecases,.final-path{grid-template-columns:1fr}.lineage{grid-template-columns:1fr auto 1fr}.friction-note{display:grid}.console-hint{display:none}.signal-chip{padding-top:8px}.provenance-head{display:grid;gap:3px}}

"""

_NAV = """<a class="skip" href="#main">本文へ移動</a>
<header class="site-head"><div class="wrap nav"><a class="brand" href="/" aria-label="EC Pulse API ホーム"><span class="mark" aria-hidden="true"><i></i></span>EC Pulse</a>
<nav class="links" aria-label="メイン"><a href="/#features">仕組み</a><a href="/#calc">仕入れ上限</a><a href="/#pricing">料金</a><a href="/#quickstart">開発者</a><a href="/#faq">FAQ</a><a href="/account">アカウント</a></nav>
<details class="mobile-menu"><summary>メニュー</summary><div class="mobile-menu-panel"><a href="/#features">仕組み</a><a href="/#calc">仕入れ上限</a><a href="/#pricing">料金</a><a href="/#quickstart">開発者</a><a href="/#faq">FAQ</a><a href="/account">アカウント</a><a href="/docs">API Docs</a></div></details>
<a class="btn primary nav-cta" href="/account">無料でAPIキー</a></div></header>"""

_FOOTER = """<footer class="wrap footer"><span>© EC Pulse API — 仕入れ判断のための市場シグナル <span class="footer-signal" aria-label="API first">● API FIRST</span></span><nav aria-label="フッター">
<a href="/docs">API Docs</a><a href="/redoc">ReDoc</a><a href="/health">Status</a><a href="/legal/terms">利用規約</a><a href="/legal/privacy">プライバシー</a>
<a href="/legal/billing">料金・解約</a><a href="/legal/commercial-transactions">特定商取引法に基づく表記</a><a href="/legal/acceptable-use">利用制限</a><a href="https://github.com/shunai394-hash/ec-pulse-api" target="_blank" rel="noopener noreferrer">GitHub</a></nav></footer>"""


# Shared by every page: the mobile menu closes on Escape, outside click and link
# click, so it never stays open over content after same-page navigation.
_NAV_SCRIPT = r"""
(function(){
var m=document.querySelector('.mobile-menu');if(!m)return;var s=m.querySelector('summary');
function close(focus){if(!m.open)return;m.open=false;if(focus)s.focus()}
var navLinks=[].slice.call(document.querySelectorAll('.links a[href^="/#"]'));
var sections=navLinks.map(function(a){return document.getElementById(a.getAttribute('href').slice(2))}).filter(Boolean);
function syncNav(){var y=window.scrollY+120,best=null;sections.forEach(function(sec){if(sec.offsetTop<=y)best=sec.id});navLinks.forEach(function(a){var on=best&&a.getAttribute('href')==="/#"+best;a.classList.toggle('active',!!on);if(on)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current')})}
syncNav();window.addEventListener('scroll',syncNav,{passive:true});
document.addEventListener('keydown',function(e){if(e.key==='Escape')close(true)});
document.addEventListener('click',function(e){if(!m.contains(e.target))close(false)});
[].forEach.call(m.querySelectorAll('.mobile-menu-panel a'),function(a){a.addEventListener('click',function(){close(false)})});
})();
"""


def _page(title: str, description: str, body: str, script: str = "") -> str:
    script_tag = f"<script>{_NAV_SCRIPT}</script>" + (f"<script>{script}</script>" if script else "")
    return (
        '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="theme-color" content="#f3f0e8">\n'
        '<meta name="color-scheme" content="light">\n'
        f'<meta name="description" content="{html.escape(description)}">\n'
        f'<meta property="og:title" content="{html.escape(title)}">\n'
        f'<meta property="og:description" content="{html.escape(description)}">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:site_name" content="EC Pulse API">\n'
        '<meta property="og:locale" content="ja_JP">\n'
        '<meta name="twitter:card" content="summary">\n'
        f'<meta name="twitter:title" content="{html.escape(title)}">\n'
        f'<meta name="twitter:description" content="{html.escape(description)}">\n'
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


_LANDING_BODY = r"""<main id="main">
<section class="wrap hero" aria-labelledby="hero-title">
<div class="hero-title">
<span class="kicker">EC事業者の仕入れ判断のための市場シグナルAPI</span>
<h1 id="hero-title" class="mt22"><span class="ln">売れる商品を、</span><br><span class="ln"><em>探す前に</em>絞り込む。</span></h1>
</div>
<div class="hero-copy">
<p class="lead">EC Pulse は、Amazon・楽天市場・Yahoo!ショッピングの商品データと、レビューやコメントにある顧客の不満、価格の動きを集めて、判断できる形でAPIから返します。あなたが考えるのは「利益が残るか」だけです。</p>
<div class="actions">
<a class="btn primary" href="/account">無料でAPIキーを取得 <span class="arr" aria-hidden="true">→</span></a>
<a class="btn" href="#calc">仕入れ上限を計算する</a>
</div>
<noscript><p class="notice mt18">デモの切り替えと仕入れ上限の自動計算にはJavaScriptが必要です。API Docsとアカウントページはそのまま利用できます。</p></noscript>
<p class="hero-note"><span>毎月100クレジット無料</span><span>カード登録不要</span><span>成功した処理だけ課金</span><span>10 MCPツール対応</span></p>
<div class="proof-rail" aria-label="EC Pulseの判断フロー"><div><strong>3</strong><span>モール</span></div><i aria-hidden="true">→</i><div><strong>5</strong><span>シグナル</span></div><i aria-hidden="true">→</i><div><strong>1</strong><span>判断</span></div><p>検索結果を増やすのではなく、判断材料を圧縮する。</p></div><div class="hero-signal-tape" aria-label="プロダクトの設計方針"><span><b>API FIRST</b>データ取得を入口に</span><span><b>DECISION READY</b>判断材料まで整形</span><span><b>HUMAN IN LOOP</b>最終判断は人が行う</span></div><div class="signal-grid" aria-label="サービスの要点"><div class="signal-chip"><strong>API FIRST</strong><span>画面ではなくAPIを中心に設計</span></div><div class="signal-chip"><strong><em>100</em> CREDITS</strong><span>Freeで毎月100クレジット</span></div><div class="signal-chip"><strong><em>10</em> MCP TOOLS</strong><span>Claudeからも同じAPIを利用</span></div></div>
</div>

<div class="console" id="console" aria-label="EC Pulse が判断材料を作る流れ（デモ表示）">
<div class="console-top"><span class="signal">Signal → Decision</span><span class="console-meta"><button class="autoplay" id="autoplay" type="button" aria-pressed="false" hidden>一時停止</button><span class="sample-badge">DEMO / SAMPLE DATA</span></span></div><p class="sr-only" id="demo-note">以下は操作イメージのサンプルデータです。実データの取得結果ではありません。</p>
<div class="stages" role="tablist" aria-label="判断までの5段階" aria-orientation="horizontal" aria-describedby="demo-note">
<button class="stage" role="tab" id="t1" aria-controls="p1" aria-selected="true"><b>01</b>市場</button>
<button class="stage" role="tab" id="t2" aria-controls="p2" aria-selected="false" tabindex="-1"><b>02</b>痛点</button>
<button class="stage" role="tab" id="t3" aria-controls="p3" aria-selected="false" tabindex="-1"><b>03</b>候補</button>
<button class="stage" role="tab" id="t4" aria-controls="p4" aria-selected="false" tabindex="-1"><b>04</b>価格</button>
<button class="stage" role="tab" id="t5" aria-controls="p5" aria-selected="false" tabindex="-1"><b>05</b>判断</button>
</div>
<div class="panel on" role="tabpanel" id="p1" aria-labelledby="t1" aria-hidden="false" tabindex="0">
<h2>3つのモールを一度に集める</h2>
<p class="cap">キーワード「ワイヤレスイヤホン」で横断検索。各モールの価格帯を同じ目盛りで並べます。</p>
<div class="rows">
<div class="row"><span class="lbl">Amazon <span class="muted">5件</span></span><span class="val">¥2,180–6,480</span><div class="bar rg"><i class="rg-a"></i></div></div>
<div class="row"><span class="lbl">楽天市場 <span class="muted">5件</span></span><span class="val">¥2,480–7,980</span><div class="bar rg"><i class="rg-r"></i></div></div>
<div class="row"><span class="lbl">Yahoo!ショッピング <span class="muted">5件</span></span><span class="val">¥1,980–5,980</span><div class="bar rg"><i class="rg-y hot"></i></div></div>
</div>
<div class="scale" aria-hidden="true"><span>¥0</span><span>¥4,000</span><span>¥8,000</span></div>
</div>
<div class="panel" role="tabpanel" id="p2" aria-labelledby="t2" aria-hidden="true" tabindex="0">
<h2>顧客がいちばん困っていること</h2>
<p class="cap">レビュー212件から不満を分類。件数と割合、実際のコメント例を返します。</p>
<div class="rows">
<div class="row"><span class="lbl">フィットしない <span class="muted">耳から外れる</span></span><span class="val">38%</span><div class="bar"><i class="w38 hot"></i></div></div>
<div class="row"><span class="lbl">壊れやすい <span class="muted">ヒンジが割れた</span></span><span class="val">24%</span><div class="bar"><i class="w24"></i></div></div>
<div class="row"><span class="lbl">耐久性 <span class="muted">電池が劣化</span></span><span class="val">17%</span><div class="bar"><i class="w17"></i></div></div>
<div class="row"><span class="lbl">価格 <span class="muted">値段が高い</span></span><span class="val">12%</span><div class="bar"><i class="w12"></i></div></div>
</div>
</div>
<div class="panel" role="tabpanel" id="p3" aria-labelledby="t3" aria-hidden="true" tabindex="0">
<h2>痛点を解消できる商品だけ残す</h2>
<p class="cap">上位の痛点ごとに3モールを再検索し、候補を並べます。</p>
<div class="cands">
<div class="cand"><span class="mp">AMZ</span><span>イヤーフック付きモデル A</span><span class="tag">フィット</span></div>
<div class="cand"><span class="mp">RKT</span><span>イヤーピース3サイズ付きモデル B</span><span class="tag">フィット</span></div>
<div class="cand"><span class="mp">YHO</span><span>補強ヒンジ・防水モデル C</span><span class="tag">耐久</span></div>
<div class="cand dim"><span class="mp">AMZ</span><span>大型ケース付きモデル D</span><span class="tag">—</span></div>
</div>
</div>
<div class="panel" role="tabpanel" id="p4" aria-labelledby="t4" aria-hidden="true" tabindex="0">
<h2>今が仕入れどきか</h2>
<p class="cap">候補 A の価格を監視。履歴の最安・最高・平均と比べたシグナルを返します。</p>
<svg class="spark" viewBox="0 0 320 110" role="img" aria-label="価格推移のサンプル。直近で過去最安値を更新">
<path class="area" d="M0 40 L40 34 L80 46 L120 30 L160 42 L200 36 L240 52 L280 64 L320 82 L320 110 L0 110 Z"/>
<line class="avg" x1="0" y1="45" x2="320" y2="45"/>
<path class="ln" d="M0 40 L40 34 L80 46 L120 30 L160 42 L200 36 L240 52 L280 64 L320 82"/>
<circle class="dot" cx="316" cy="81" r="5"/>
<text x="4" y="58">平均</text>
</svg>
<div class="kv">
<div><small>現在</small><strong>¥2,280</strong></div>
<div><small>平均比</small><strong>−18%</strong></div>
<div><small>シグナル</small><strong>最安値</strong></div>
</div>
</div>
<div class="panel" role="tabpanel" id="p5" aria-labelledby="t5" aria-hidden="true" tabindex="0">
<h2>仕入れるか、見送るか</h2>
<p class="cap">販売想定 ¥4,980・手数料10%・送料等 ¥500・目標粗利30% の場合</p>
<div class="verdict">
<small class="mono">仕入れ上限</small>
<div class="big">¥2,488</div>
<ul>
<li><span>候補 A の現在価格</span><span>¥2,280</span></li>
<li><span>上限までの余裕</span><span>¥208</span></li>
<li><span>次のアクション</span><span>監視を継続し値下がりを通知</span></li>
</ul>
</div>
</div>
<div class="console-foot"><span>表示はサンプルです。結果は実際のデータによって変わります。</span><span class="console-hint">クリック / ← → で切替</span><a href="#output" class="textlink">出力の見方</a></div>
</div>
</section>

<section class="section" id="problem" aria-labelledby="problem-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">01 — PROBLEM</span><h2 id="problem-title"><span class="ln">利益を削っているのは、</span><br><span class="ln">仕入れ値だけではない。</span></h2></div>
<p class="lead">候補を探し、3つのモールを行き来し、レビューを読み、価格をメモする。判断の前の作業に時間を使うほど、良い仕入れの機会は先に取られていきます。</p>
</div>
<div class="pains">
<div class="pain"><p class="verb">探す</p><p class="now">キーワードを変えながら、モールごとに同じ検索を繰り返す。</p><p class="then">3モールを1回の呼び出しで横断検索</p></div>
<div class="pain"><p class="verb">読む</p><p class="now">何百件ものレビューを読んで、不満の傾向を手で数える。</p><p class="then">不満を分類し、割合と実例で返す</p></div>
<div class="pain"><p class="verb">見張る</p><p class="now">値下がりを逃さないよう、毎日ページを開いて価格を確かめる。</p><p class="then">価格を監視し、変化をWebhookで通知</p></div>
</div><div class="friction-note"><strong>FRICTION → DECISION</strong><span>探す・読む・見張るをAPIに寄せ、最後の「仕入れるか」を人に残します。</span></div><div class="outcome-line" aria-label="利用前と利用後"><span>BEFORE <b>候補を集める</b></span><i aria-hidden="true">→</i><span>AFTER <b>候補を判断する</b></span></div>
</div>
</section>

<section class="section night" id="discovery" aria-labelledby="discovery-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">02 — SEARCH → DISCOVERY</span><h2 id="discovery-title"><span class="ln">検索から始めない。</span><br><span class="ln">発見から始める。</span></h2></div>
<p class="lead">普通は、あなたがキーワードを考えて、結果を1件ずつ比べます。EC Pulse は順番が逆です。市場のデータから、見るべき候補が先に浮かび上がります。</p>
</div>
<div class="compare">
<div class="flow old"><h3>これまでの探し方</h3><ol>
<li><b>01</b><span class="who">あなたがキーワードを考える</span></li>
<li><b>02</b><span>モールごとに検索結果を開く</span></li>
<li><b>03</b><span>レビューを1件ずつ読む</span></li>
<li><b>04</b><span>価格をスプレッドシートに写す</span></li>
<li><b>05</b><span>勘で決める</span></li>
</ol><p class="foot">比較の手間は、候補の数だけ増えていく。</p></div>
<div class="flow new" id="flow-new"><h3>EC Pulse の探し方</h3><ol>
<li><b>01</b><span>市場データを3モールから集める</span><em>INPUT</em></li>
<li><b>02</b><span>レビューから顧客の痛点を抽出する</span><em>SIGNAL</em></li>
<li><b>03</b><span>痛点を解決できる商品候補を探す</span></li>
<li><b>04</b><span>価格の履歴と今の水準を比べる</span></li>
<li><b>05</b><span>利益が残る仕入れ上限を出す</span><em>DECISION</em></li>
<li class="end"><b>→</b><span>あなたは、仕入れるかどうかだけを決める</span></li>
</ol><p class="foot">比較は API が終わらせる。残るのは判断だけ。</p></div>
</div><div class="decision-path" aria-label="判断の出口"><div><b>INPUT</b><span>市場・痛点・価格</span></div><div><b>OUTPUT</b><span>候補と仕入れ上限</span></div><div class="last"><b>NEXT</b><span>仕入れる / 監視する / 見送る</span></div></div>
</div>
</section>

<section class="section" id="features" aria-labelledby="features-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">03 — HOW IT WORKS</span><h2 id="features-title"><span class="ln">5つのシグナルを、</span><br><span class="ln">1つの判断に。</span></h2></div>
<p class="lead">各段階は独立したAPIです。全部つなげても、必要なところだけ使っても構いません。クレジットは成功した処理だけに使われ、取得先の障害で失敗した分は自動で戻ります。</p>
</div>
<ol class="steps">
<li class="step"><span class="no">01</span><h3>市場を集める</h3><p>Amazon・楽天市場・Yahoo!ショッピングを横断検索し、商品名・価格・在庫・URLを同じ形式で返します。</p><div class="api"><code>POST /v1/products/search</code><span>件数 × モール数 クレジット</span></div></li>
<li class="step"><span class="no">02</span><h3>痛点を見つける</h3><p>レビューやコメントから不満を分類し、件数・割合・実際のコメント例を返します。URLを渡せば本文の取得から行います。</p><div class="api"><code>POST /v1/consumer-insights/analyze</code><span>コメント50件ごとに1</span><code>POST /v1/research/ingest</code><span>URL数</span></div></li>
<li class="step"><span class="no">03</span><h3>候補を絞る</h3><p>上位の痛点ごとに3モールを再検索し、痛点に対する商品の方向性と候補商品、広告で試す訴求案を返します。</p><div class="api"><code>GET /v1/research/runs/{id}/opportunity</code><span>検索件数に応じて</span></div></li>
<li class="step"><span class="no">04</span><h3>価格を確かめる</h3><p>商品ページから価格を取得し、複数商品を並べて比較します。監視中の商品は履歴の最安・最高・平均と比べた水準を返します。</p><div class="api"><code>POST /v1/products</code><span>1</span><code>POST /v1/products/compare</code><span>URL数</span><code>GET /v1/monitors/{id}/opportunity</code><span>2</span></div></li>
<li class="step"><span class="no">05</span><h3>見張り続ける</h3><p>気になる商品を5分〜1週間の間隔で監視。価格が変わるとあなたのシステムへWebhookで通知します。</p><div class="api"><code>POST /v1/monitors</code><span>登録時に1</span><code>GET /v1/monitors/{id}/history</code><span>1</span></div></li>
</ol><div class="usecases" aria-label="代表的な使い方"><article class="usecase"><b>USE CASE 01</b><h3>新商品を探す</h3><p>3モールの候補を集め、レビューの痛点と価格を同じ判断面に置く。</p><a href="#features">検索フローを見る <span aria-hidden="true">→</span></a></article><article class="usecase"><b>USE CASE 02</b><h3>勝ち筋を監視する</h3><p>候補商品の価格履歴を追い、変化をWebhookで自社システムへ渡す。</p><a href="#pricing">利用量を見る <span aria-hidden="true">→</span></a></article><article class="usecase"><b>USE CASE 03</b><h3>AIから調査する</h3><p>ClaudeなどからMCPツール経由で検索・比較・分析・監視を実行する。</p><a href="#quickstart">開発者フローへ <span aria-hidden="true">→</span></a></article></div>
</div>
</section>

<section class="section" id="output" aria-labelledby="output-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">04 — WHAT YOU SEE</span><h2 id="output-title"><span class="ln">並ぶのは、判断に</span><br><span class="ln">必要な数字だけ。</span></h2></div>
<p class="lead">EC Pulse が返すのは検索結果の羅列ではなく、仕入れの判断材料です。下の例は、実際のAPIレスポンスの項目だけで組み立てています。</p>
</div>
<div class="output">
<article class="decision" aria-label="判断カードの例">
<header><span>Decision card</span><span>出力例・サンプル</span></header><div class="evidence-strip"><span>TRACEABLE OUTPUT</span><span>件数・価格・計算式を確認できます</span></div>
<div class="prod"><p class="small muted m0">キーワード</p><h3>ワイヤレスイヤホン</h3></div>
<dl class="m0">
<div class="drow"><dt>いちばんの痛点</dt><dd><strong>38%</strong> フィットしない<span class="pill sig">212件中81件</span></dd></div>
<div class="drow"><dt>商品候補</dt><dd><strong>15</strong> 件 — Amazon 5・楽天 5・Yahoo! 5</dd></div>
<div class="drow"><dt>価格シグナル</dt><dd><strong>−18%</strong> 平均比<span class="pill go">過去最安値</span></dd></div>
<div class="drow"><dt>現在価格</dt><dd><strong>¥2,280</strong></dd></div>
<div class="drow key"><dt>仕入れ上限</dt><dd><strong>¥2,488</strong><br><span class="small muted">販売 ¥4,980・手数料10%・送料等 ¥500・目標粗利30% で計算</span></dd></div>
</dl>
</article>
<div>
<ol class="map">
<li><b>いちばんの痛点</b><code>pain_points[0].share_percent / count</code></li>
<li><b>商品候補</b><code>product_candidates[]</code> — 痛点ごとに3モールを検索</li>
<li><b>価格シグナル</b><code>signal: historical_low | below_average | normal</code><code>metrics.discount_vs_average_percent</code></li>
<li><b>現在価格</b><code>current_price</code></li>
<li><b>仕入れ上限</b>販売価格・手数料・送料・目標粗利率から計算（下の計算機と同じ式）</li>
</ol>
<p class="disclaim">EC Pulse は判断の材料を出すツールです。売上や利益を保証するものではありません。痛点の分類はルールベースの集計なので、仕入れ前には元のコメントも確認してください。</p><div class="lineage" aria-label="データの流れ"><span>SOURCE</span><i aria-hidden="true">→</i><span>NORMALIZE</span><i aria-hidden="true">→</i><span>SIGNAL</span><i aria-hidden="true">→</i><strong>DECISION</strong></div><div class="provenance"><div class="provenance-head"><b>TRACEABILITY</b><span>サンプル表示</span></div><p>数字の意味を追えるよう、件数・価格・計算条件を同じ画面で示します。実データの取得結果ではなく、<code>/v1/products/search</code> などのAPI出力項目を説明するための例です。</p></div>
</div>
</div>
</div>
</section>

<section class="section" id="calc" aria-labelledby="calc-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">05 — BUY CEILING</span><h2 id="calc-title"><span class="ln">いくらまでなら、</span><br><span class="ln">仕入れていいか。</span></h2></div>
<p class="lead">欲しいのは価格そのものではなく、「この値段以下なら仕入れていい」という線です。数字を変えると、その場で計算し直します。</p>
</div>
<div class="calc">
<form id="calc-form" aria-describedby="calc-help" novalidate>
<p id="calc-help" class="small muted m0">すべて税込・1個あたりで入力してください。計算はこのページの中だけで行い、どこにも送信しません。</p><div class="calc-assumption"><b>LOCAL</b><span>入力値はブラウザ内だけで計算。APIキーや入力内容はこの計算機から送信しません。</span></div><div class="presets" aria-label="計算例"><span>試す：</span><button type="button" data-preset="balanced">標準</button><button type="button" data-preset="tight">薄利</button><button type="button" data-preset="premium">高単価</button></div>
<div class="field"><label for="c-price">販売価格<small>売りたい価格</small></label><div class="inp"><span>¥</span><input id="c-price" name="price" type="number" inputmode="numeric" min="0" step="1" value="4980"></div></div>
<div class="field"><label for="c-fee">販売手数料<small>モールの手数料率</small></label><div class="inp"><input id="c-fee" name="fee" type="number" inputmode="decimal" min="0" max="100" step="0.1" value="10"><span>%</span></div></div>
<div class="field"><label for="c-ship">送料・梱包<small>1個あたり</small></label><div class="inp"><span>¥</span><input id="c-ship" name="ship" type="number" inputmode="numeric" min="0" step="1" value="500"></div></div>
<div class="field"><label for="c-other">その他コスト<small>広告費・保管料など</small></label><div class="inp"><span>¥</span><input id="c-other" name="other" type="number" inputmode="numeric" min="0" step="1" value="0"></div></div>
<div class="field"><label for="c-margin">目標粗利率<small>販売価格に対して</small></label><div class="inp"><input id="c-margin" name="margin" type="number" inputmode="decimal" min="0" max="100" step="0.1" value="30"><span>%</span></div></div>
<hr>
<div class="field"><label for="c-buy">候補の仕入れ値<small>比べたい価格（任意）</small></label><div class="inp"><span>¥</span><input id="c-buy" name="buy" type="number" inputmode="numeric" min="0" step="1" value="2280"></div></div>
</form>
<noscript><p class="notice mt18">仕入れ上限の計算結果はJavaScript有効時に表示されます。入力値はこのページ内でのみ計算されます。</p></noscript>
<div class="result">
<div aria-live="polite" aria-atomic="true"><p class="label m0">仕入れ上限</p><p class="ceiling m0" id="r-ceiling">¥2,488</p><p class="msg mt12" id="r-msg">この価格以下で仕入れられれば、目標粗利率 30% を確保できます。</p></div>
<div class="stack" aria-hidden="true"><i class="s-buy" id="b-buy"></i><i class="s-fee" id="b-fee"></i><i class="s-ship" id="b-ship"></i><i class="s-profit" id="b-profit"></i></div>
<ul class="legend">
<li><i class="s-buy"></i><span>仕入れ上限</span><span id="l-buy">¥2,488</span></li>
<li><i class="s-fee"></i><span>販売手数料</span><span id="l-fee">¥498</span></li>
<li><i class="s-ship"></i><span>送料・その他</span><span id="l-ship">¥500</span></li>
<li><i class="s-profit"></i><span>目標粗利</span><span id="l-profit">¥1,494</span></li>
</ul>
<div class="check" id="r-check">
<div class="row2"><span>候補の仕入れ値</span><span id="k-buy">¥2,280</span></div>
<div class="row2"><span>この値段での粗利</span><span id="k-profit">¥1,702（34.2%）</span></div>
<p class="badge ok m0" id="k-badge">上限より ¥208 安い — 仕入れ条件を満たしています</p>
</div>
<p class="small m0 muted">計算式：仕入れ上限 = 販売価格 ×（1 − 手数料率 − 目標粗利率）− 送料・梱包 − その他コスト。<a href="/docs" class="textlink">APIではこの判断材料を自動取得できます。</a></p>
</div>
</div>
</div>
</section>

<section class="section" id="pricing" aria-labelledby="pricing-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">06 — PRICING</span><h2 id="pricing-title"><span class="ln">使った分だけの、</span><br><span class="ln">クレジット制。</span></h2></div>
<p class="lead">1回の呼び出しに必要なクレジットは処理の量で決まります。入力エラーやクレジット不足のリクエストでは消費されません。</p>
</div>
<div class="plans">
<div class="plan"><span class="tagline">まず試す</span><h3 class="mt10">Free</h3><p class="for">1つの商品ジャンルで、市場と痛点を調べてみたい人に。</p><p class="price">¥0<small>/ 月</small></p>
<ul><li>毎月100クレジット</li><li>30リクエスト / 分</li><li>すべてのAPIを利用可能</li><li>カード登録不要</li></ul>
<a class="btn" href="/account">無料でAPIキーを取得</a></div>
<div class="plan featured"><span class="tagline">毎日の仕入れ調査に</span><h3 class="mt10">Pro</h3><p class="for">複数ジャンルの候補探しと価格監視を、日々の業務に組み込む人に。</p><p class="price tbd">月額と付与クレジットは<br>Stripeの決済画面で確認できます</p>
<ul><li>請求ごとに月間クレジットを付与</li><li>300リクエスト / 分</li><li>価格監視とWebhook通知</li><li>Stripeでいつでも解約</li></ul>
<a class="btn primary" href="/account#billing">Proで仕入れ調査を始める</a><p class="plan-note">最終的な月額と付与クレジットは、決済確定前にStripe画面で確認できます。</p></div>
<div class="plan"><span class="tagline">規模を広げる</span><h3 class="mt10">Business</h3><p class="for">大量の商品リサーチや監視を、自社システムで自動化するチームに。</p><p class="price tbd">月額と付与クレジットは<br>Stripeの決済画面で確認できます</p>
<ul><li>請求ごとに月間クレジットを付与</li><li>3,000リクエスト / 分</li><li>大量のリサーチと監視向け</li><li>Stripeでいつでも解約</li></ul>
<a class="btn" href="/account#billing">Businessで自動化する</a><p class="plan-note">大規模利用を想定。実際の料金・付与クレジットはStripe画面で確定前に確認してください。</p></div>
</div><div class="fit-guide" aria-label="プランの選び方"><span><b>TRY</b>まずAPIを触る → Free</span><span><b>OPERATE</b>日々の調査 → Pro</span><span><b>AUTOMATE</b>大量処理 → Business</span></div>
<p class="small muted mt20">有料プランの金額と付与クレジット数は、Stripeの決済画面で確定前に表示されます。<a href="/legal/billing">料金・解約ポリシー</a></p>
</div>
</section>

<section class="section night" id="quickstart" aria-labelledby="qs-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">07 — FOR DEVELOPERS</span><h2 id="qs-title"><span class="ln">仕入れ調査を、</span><br><span class="ln">APIで自動化する。</span></h2></div>
<p class="lead">EC PulseはAPIが本体。スプレッドシート、社内ツール、ClaudeなどのAIエージェントから、同じ認証・クレジット体系で呼び出せます。<br><strong>まず1回呼ぶ → 判断材料を見る → 自動化する。</strong></p>
</div>
<div class="dev">
<ol>
<li><div><strong>Googleでログイン</strong><p><a href="/account" class="textlink">アカウントページ</a>から。Freeプランが自動で使えます。</p></div></li>
<li><div><strong>APIキーを発行</strong><p>キーは発行時に一度だけ表示されます。安全な場所に保存してください。</p></div></li>
<li><div><strong>呼び出す</strong><p><code>X-API-Key</code> ヘッダーを付けるだけ。残りクレジットは <code>X-EC-Credits-Remaining</code> で返ります。</p></div></li>
<li><div><strong>詳しく見る</strong><p><a href="/docs" class="textlink">API Docs（Swagger）</a>・<a href="/redoc" class="textlink">ReDoc</a></p></div></li>
<li><div><strong>Claudeから使う</strong><p>Claude Code プラグインの10のMCPツールが、同じAPIで検索・比較・レビュー分析・価格監視を会話から実行します。<a href="https://github.com/shunai394-hash/ec-pulse-api/tree/main/plugins/ec-pulse" class="textlink" target="_blank" rel="noopener noreferrer">プラグインの導入方法<span class="sr-only">（GitHub、新しいタブで開きます）</span></a></p></div></li>
</ol>
<div>
<div class="code-shell"><button type="button" class="code-copy" id="copy-curl">curlをコピー</button><pre tabindex="0" aria-label="curlでの呼び出し例" id="curl-example"><code><span class="c"># 3モールを横断して、仕入れ候補を集める</span>
curl -X POST https://ec-pulse-api-two.vercel.app/v1/products/search \
  -H <span class="k">"X-API-Key: $EC_PULSE_API_KEY"</span> \
  -H "Content-Type: application/json" \
  -d '{"query":"ワイヤレスイヤホン",
       "marketplaces":["amazon","rakuten","yahoo"],
       "limit":5}'</code></pre></div>
<div class="errs">
<div><b>401</b>APIキーがない・無効</div>
<div><b>402</b>クレジット不足（消費なし）</div>
<div><b>400 / 422</b>入力エラー・非公開URL</div>
<div><b>429</b>レート制限（Retry-After）</div>
<div><b>502</b>取得先の障害（自動返却）</div>
<div><b>503</b>一時的な障害</div>
</div>
</div>
<div class="response-preview" aria-label="レスポンスのイメージ"><span>RESPONSE CONTRACT</span><code>{"products":[...],"credits_remaining":...}</code><small>実際のレスポンスはAPI Docsで確認できます。</small></div><div class="dev-next"><b>DEVELOPER PATH</b><span>ログイン → APIキー発行 → 1回呼ぶ → レスポンス確認 → 自動化</span></div>
</div>
</div>
</section>

<section class="section" id="security" aria-labelledby="trust-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">08 — TRUST</span><h2 id="trust-title"><span class="ln">判断の材料を出す。</span><br><span class="ln">判断は、あなたが。</span></h2></div>
<p class="lead">EC Pulse は「必ず売れる」とは言いません。そのかわり、根拠になったデータと計算をそのまま見せます。</p>
</div>
<div class="trust">
<div><h3>根拠を隠さない</h3><p>痛点には件数と実際のコメント例、価格シグナルには比較した最安・最高・平均を添えて返します。</p></div>
<div><h3>失敗には課金しない</h3><p>入力エラーやクレジット不足では消費せず、取得先の障害で失敗した処理は自動で返却します。</p></div>
<div><h3>APIキーを守る</h3><p>キーはハッシュで保存し、平文は持ちません。いつでもローテーション・失効でき、HMAC署名にも対応します。</p></div>
<div><h3>AIに任せても、根拠を残す</h3><p>ClaudeなどのAIエージェントから同じAPIを呼べます。レビューの痛点分類は現在ルールベースで、元コメントや件数も確認できる設計です。</p></div>
<div><h3>社内ネットワークに触れない</h3><p>プライベートIP・ループバック・メタデータアドレスへの接続を、リダイレクト後も含めて拒否します。</p></div>
</div>
</div>
</section>

<section class="section" id="faq" aria-labelledby="faq-title">
<div class="wrap">
<div class="sec-head">
<div><span class="sec-no">09 — FAQ</span><h2 id="faq-title"><span class="ln">始める前に、</span><br><span class="ln">知っておきたいこと。</span></h2></div>
<p class="lead">最初の一歩で迷わないように、料金・データ・AI・失敗時の扱いを先に答えます。</p>
</div>
<div class="faq">
<details><summary>本当に無料で試せますか？</summary><div class="answer"><p>Freeプランは毎月100クレジット、30リクエスト/分、カード登録なしで利用できます。メータード処理の成功時だけクレジットを消費します。</p></div></details>
<details><summary>AIが勝手に「売れる」と判断するサービスですか？</summary><div class="answer"><p>いいえ。EC Pulseは市場データ、レビューの痛点、価格シグナルをAPIで返し、判断材料を作ります。売上や利益を保証しません。痛点分類は現在ルールベースです。</p></div></details>
<details><summary>失敗した取得にもクレジットがかかりますか？</summary><div class="answer"><p>入力エラーやクレジット不足では消費しません。取得先の障害で失敗した処理は返却する設計です。</p></div></details>
<details><summary>有料プランの価格はどこで確認できますか？</summary><div class="answer"><p>Pro / Businessの最終的な月額と付与クレジットは、Stripeの決済画面で確認してから確定します。公開前に料金・法務情報も最終確定する必要があります。</p></div></details>
<details><summary>EC Pulseは利益を保証しますか？</summary><div class="answer"><p>いいえ。市場データ、顧客の痛点、価格シグナルを整理して判断を速くするサービスです。市場環境・仕入れ条件・販売条件によって結果は変わるため、最終判断は利用者が行います。</p></div></details>
</div>
</div>
</section>

<section class="wrap final" aria-labelledby="final-title">
<span class="kicker">START</span>
<h2 id="final-title" class="mt18"><span class="ln">まずは、気になっている</span><br><span class="ln">商品をひとつ。</span></h2>
<div class="actions"><a class="btn primary" href="/account">無料でAPIキーを取得 <span class="arr" aria-hidden="true">→</span></a><a class="btn" href="/docs">API仕様を見る</a><a class="textlink" href="/#faq">よくある質問を確認</a></div><p class="final-reassure"><span>NO CARD</span><span>100 FREE CREDITS / MONTH</span><span>SUCCESSFUL PROCESSING ONLY</span></p><div class="final-path" aria-label="開始手順"><div><b>01 / ACCESS</b><span>GoogleでログインしてFreeを開始</span></div><div><b>02 / KEY</b><span>APIキーを発行して保存</span></div><div><b>03 / SIGNAL</b><span>気になる商品を1回検索して判断材料を見る</span></div></div>
</section>
</main>
"""

_LANDING_SCRIPT = r"""
(function(){
var d=document,root=d.documentElement;root.classList.add('js');
var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* Global polish: reveal sections and keep a quiet scroll-progress signal. */
var revealTargets=[].slice.call(d.querySelectorAll('.section .sec-head,.section .pains,.section .compare,.section .steps,.section .output,.section .calc,.section .plans,.section .dev,.section .trust,.section .cta-card'));
function reveal(el){el.classList.add('reveal-in')}
if(reduce){revealTargets.forEach(reveal)}
else if('IntersectionObserver' in window){var rio=new IntersectionObserver(function(entries){entries.forEach(function(e){if(e.isIntersecting){reveal(e.target);rio.unobserve(e.target)}})},{threshold:.12,rootMargin:'0px 0px -8% 0px'});revealTargets.forEach(function(el){rio.observe(el)})}
else{revealTargets.forEach(reveal)}
function scrollSignal(){var h=d.documentElement.scrollHeight-window.innerHeight;root.style.setProperty('--scroll',h>0?Math.min(1,window.scrollY/h):0)}
scrollSignal();window.addEventListener('scroll',scrollSignal,{passive:true});

/* Hero console: five stages of the decision flow. Auto-advances unless the
   visitor prefers reduced motion or is interacting with it. */
var tabs=[].slice.call(d.querySelectorAll('.stage')),panels=tabs.map(function(t){return d.getElementById(t.getAttribute('aria-controls'))});
var cur=0,timer=null,stopped=false,hover=false,DWELL=3600,btn=d.getElementById('autoplay');
function show(i,focus){
  cur=(i+tabs.length)%tabs.length;
  tabs.forEach(function(t,j){
    var on=j===cur;
    t.setAttribute('aria-selected',on?'true':'false');
    t.tabIndex=on?0:-1;
    panels[j].classList.toggle('on',on);
    panels[j].setAttribute('aria-hidden',on?'false':'true');
  });
  if(focus)tabs[cur].focus();
}
function schedule(){clearTimeout(timer);if(reduce||stopped||hover)return;timer=setTimeout(function(){show(cur+1);schedule()},DWELL)}
/* Visible pause control (WCAG 2.2.2): hover/focus pausing alone is not enough on touch screens. */
function setStopped(on){stopped=on;if(btn){btn.setAttribute('aria-pressed',on?'true':'false');btn.textContent=on?'自動再生':'一時停止';btn.setAttribute('aria-label',on?'デモの自動切り替えを再開':'デモの自動切り替えを一時停止')}schedule()}
if(btn&&!reduce&&tabs.length){btn.hidden=false;setStopped(false);btn.addEventListener('click',function(){hover=false;setStopped(!stopped)})}
tabs.forEach(function(t,j){
  t.addEventListener('click',function(){show(j);setStopped(true)});
  t.addEventListener('keydown',function(e){
    var k=e.key;if(k==='ArrowRight'||k==='ArrowLeft'||k==='Home'||k==='End'){e.preventDefault();setStopped(true);
      show(k==='Home'?0:k==='End'?tabs.length-1:cur+(k==='ArrowRight'?1:-1),true)}
  });
});
var con=d.getElementById('console');
if(con){
  /* Only a real mouse pauses on hover; taps emulate mouse events and would never "leave". */
  con.addEventListener('pointerenter',function(e){if(e.pointerType==='mouse'){hover=true;clearTimeout(timer)}});
  con.addEventListener('pointerleave',function(e){if(e.pointerType==='mouse'){hover=false;schedule()}});
  con.addEventListener('focusin',function(e){if(e.target!==btn){hover=true;clearTimeout(timer)}});
  con.addEventListener('focusout',function(e){if(!con.contains(e.relatedTarget)){hover=false;schedule()}});
}
if(tabs.length){show(0);schedule()}

/* Discovery flow: light each step in order when it scrolls into view, so the
   eye follows market data -> pain -> candidate -> price -> ceiling -> decision. */
var flow=d.getElementById('flow-new');
if(flow){
  var steps=[].slice.call(flow.querySelectorAll('li'));
  var lightAll=function(){steps.forEach(function(li,i){setTimeout(function(){li.classList.add('lit')},reduce?0:i*260)})};
  if(!('IntersectionObserver' in window)||reduce){lightAll()}
  else{var io=new IntersectionObserver(function(es){if(es[0].isIntersecting){lightAll();io.disconnect()}},{threshold:.35});io.observe(flow)}
}

/* Buy-ceiling calculator. Runs locally; nothing is sent anywhere. */
var f=d.getElementById('calc-form');
if(f){
  var yen=function(n){return (n<0?'−¥':'¥')+Math.round(Math.abs(n)).toLocaleString('ja-JP')};
  var num=function(id){var v=parseFloat(d.getElementById(id).value);return isFinite(v)&&v>=0?v:0};
  /* Out-of-range input is flagged instead of being silently clamped. */
  var invalid=function(){
    var bad=[];
    [].forEach.call(f.querySelectorAll('input'),function(el){
      var raw=el.value.trim(),v=parseFloat(raw),max=el.hasAttribute('max')?parseFloat(el.max):Infinity;
      var off=raw!==''&&(!isFinite(v)||v<0||v>max);
      if(off){el.setAttribute('aria-invalid','true');bad.push(el)}else{el.removeAttribute('aria-invalid')}
    });
    return bad;
  };
  var set=function(id,t){d.getElementById(id).textContent=t};
  var calc=function(){
    var price=num('c-price'),fee=Math.min(num('c-fee'),100)/100,ship=num('c-ship'),other=num('c-other'),margin=Math.min(num('c-margin'),100)/100,buyRaw=d.getElementById('c-buy').value.trim(),buy=num('c-buy');
    var feeY=price*fee,profitY=price*margin,costs=ship+other,ceiling=Math.floor(price-feeY-profitY-costs),bad=invalid();
    var ce=d.getElementById('r-ceiling');ce.textContent=price>0?yen(ceiling):'—';ce.classList.toggle('neg',price>0&&ceiling<=0);
    if(bad.length){set('r-msg',bad.some(function(el){return el.hasAttribute('max')&&parseFloat(el.value)>100})?'手数料率と目標粗利率は 0〜100% の範囲で入力してください。':'金額と率は 0 以上の数値で入力してください。');}
    else set('r-msg',price<=0?'販売価格を入力すると、仕入れ上限を計算します。':ceiling>0?'この価格以下で仕入れられれば、目標粗利率 '+(margin*100).toFixed(margin*100%1?1:0)+'% を確保できます。':'この条件では利益が残りません。販売価格・コスト・目標粗利率を見直してください。');
    var total=price>0?price:1,w=function(v){return Math.max(0,v)/total*100+'%'};
    d.getElementById('b-buy').style.width=w(ceiling);d.getElementById('b-fee').style.width=w(feeY);d.getElementById('b-ship').style.width=w(costs);d.getElementById('b-profit').style.width=w(profitY);
    set('l-buy',yen(Math.max(ceiling,0)));set('l-fee',yen(feeY));set('l-ship',yen(costs));set('l-profit',yen(profitY));
    var chk=d.getElementById('r-check');chk.classList.toggle('hidden',!buyRaw||price<=0);
    if(buyRaw&&price>0){
      var p=price-feeY-costs-buy,rate=p/price*100,b=d.getElementById('k-badge'),gap=ceiling-buy;
      set('k-buy',yen(buy));set('k-profit',yen(p)+'（'+rate.toFixed(1)+'%）');
      b.className='badge m0 '+(gap>=0&&ceiling>0?'ok':'ng');
      b.textContent=ceiling<=0?'この条件では、どの仕入れ値でも目標に届きません':gap>=0?'上限より '+yen(gap)+' 安い — 仕入れ条件を満たしています':'上限を '+yen(-gap)+' 超えています — この値段では目標粗利に届きません';
    }
  };
  f.addEventListener('input',calc);f.addEventListener('submit',function(e){e.preventDefault()});[].forEach.call(d.querySelectorAll('[data-preset]'),function(b){b.addEventListener('click',function(){var p={balanced:[4980,10,500,0,30,2280],tight:[3980,12,550,120,35,1900],premium:[12800,8,700,300,35,7200]}[b.getAttribute('data-preset')];if(!p)return;['c-price','c-fee','c-ship','c-other','c-margin','c-buy'].forEach(function(id,i){d.getElementById(id).value=p[i]});calc();d.getElementById('c-price').focus()})});calc();
var copyCurl=d.getElementById('copy-curl'),curl=d.getElementById('curl-example');if(copyCurl&&curl){copyCurl.addEventListener('click',function(){var value=curl.innerText.trim();var done=function(ok){copyCurl.textContent=ok?'コピーしました':'手動でコピー';setTimeout(function(){copyCurl.textContent='curlをコピー'},1800)};if(navigator.clipboard){navigator.clipboard.writeText(value).then(function(){done(true)}).catch(function(){done(false)})}else{done(false)}})}
}
})();
"""

LANDING_PAGE = _page(
    "EC Pulse — 売れる商品を、探す前に絞り込む。",
    "EC Pulse は Amazon・楽天市場・Yahoo!ショッピングの商品データ、レビューの痛点、価格の動きを集め、利益が残る仕入れ判断を速くする市場シグナルAPIです。",
    _LANDING_BODY,
    _LANDING_SCRIPT,
)

_ACCOUNT_BODY = r"""<main id="main" class="page-pad wrap account-page">
<div class="account-head">
<div><span class="kicker">CONTROL / EC PULSE</span><h1 class="h-page mt14">仕入れ調査を、<br><em>ここから動かす。</em></h1></div>
<p class="lead">APIキー、クレジット、利用状況、請求をひとつの場所で管理します。必要なときだけ操作し、調査はAPIへ渡せます。</p>
</div>
<div id="status" class="notice account-status hidden" role="status" aria-live="polite" aria-atomic="true"></div>
<noscript><div class="notice error mt18">アカウント管理にはJavaScriptが必要です。ブラウザのJavaScriptを有効にして再読み込みしてください。API DocsはJavaScriptなしでも確認できます。</div></noscript>
<div id="status-actions" class="actions hidden" aria-live="polite"><button class="btn" id="retry-account" type="button">もう一度確認する</button><a class="btn" href="/docs">API Docsを見る</a></div>

<section id="signed-out" class="mt18 card signed-out hidden">
<div><span class="kicker">START</span><h2 class="h-sm mt10">まず無料でAPIキーを取得</h2><p class="muted">Googleアカウントでログインすると、Freeプランの毎月100クレジットとAPIキーを使い始められます。</p></div>
<a class="btn primary" href="/auth/google">Googleでログイン <span class="arr" aria-hidden="true">→</span></a>
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
<div class="keybox"><code id="new-key-value" aria-label="新しいAPIキー"></code><button class="btn" id="copy-key" type="button" aria-describedby="copy-key-status">コピー</button></div><span id="copy-key-status" class="small muted" role="status" aria-live="polite"></span></div>
<div class="actions"><button class="btn primary" id="issue-key" type="button">APIキーを発行</button><button class="btn hidden" id="rotate-key" type="button">キーを再発行（旧キーは失効）</button></div>
</section>

<section class="mt16 card">
<h2 class="h-sm">直近30日の利用状況</h2>
<p class="muted" id="usage-empty">まだ利用履歴はありません。</p>
<div class="table-scroll"><table id="usage-table" class="hidden"><thead><tr><th>エンドポイント</th><th>リクエスト</th><th>クレジット</th></tr></thead><tbody id="usage-rows"></tbody></table></div>
</section>

<section class="mt16 card billing-card" id="billing">
<div class="section-label"><span class="kicker">BILLING</span><span class="small muted">Stripeで安全に管理</span></div>
<h2 class="h-sm mt10">プラン変更・お支払い</h2>
<p class="muted">決済とプラン管理は Stripe で行います。操作にはAPIキーが必要です。このページを閉じると入力したキーは保存されません。</p>
<label for="billing-key" class="small muted">APIキー</label>
<input id="billing-key" type="password" autocomplete="off" placeholder="ecp_live_…">
<div class="actions"><button class="btn primary" type="button" data-plan="pro">Proにアップグレード</button><button class="btn" type="button" data-plan="business">Businessにアップグレード</button><button class="btn" type="button" id="portal">請求情報・解約（Stripe）</button></div>
<p class="mt12 muted small">標準の解約は請求期間の終了時にFreeへ戻ります。即時解約を選ぶ場合は返金条件を確認してください。詳しくは <a href="/legal/billing">料金・解約ポリシー</a>。</p>
</section>

<form class="mt20" method="post" action="/auth/logout"><button class="btn" type="submit">ログアウト</button></form>
</div>
</main>"""

_ACCOUNT_SCRIPT = r"""
(function(){
var $=function(id){return document.getElementById(id)};
function show(el,on){el.classList.toggle('hidden',!on)}
function status(msg,kind){var s=$('status');s.textContent=msg;s.className='notice account-status'+(kind?' '+kind:'');show(s,!!msg);show($('status-actions'),!!msg&&kind==='error')}
function busy(b,label){if(!b.dataset.label)b.dataset.label=b.textContent;b.disabled=!!label;b.setAttribute('aria-busy',label?'true':'false');b.textContent=label||b.dataset.label}
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
var NETWORK='通信エラーが発生しました。接続を確認して、もう一度お試しください。';
async function loadAccount(quiet){
  if(!quiet)status('アカウント情報を読み込んでいます…');
  var acc=await call('GET','/v1/customer/account');
  if(!acc.ok){status('アカウント情報を取得できませんでした: '+detail(acc),'error');return}
  $('plan').textContent=String(acc.data.plan||'free').toUpperCase();
  $('credits').textContent=acc.data.provisioned?String(acc.data.credits_balance):'100（発行時に付与）';
  if(acc.data.key_prefix){$('key-info').textContent='有効なキー: '+acc.data.key_prefix+'…（キー全体は発行時のみ表示）';show($('issue-key'),false);show($('rotate-key'),true)}
  else{$('key-info').textContent='まだAPIキーは発行されていません。';show($('issue-key'),true);show($('rotate-key'),false)}
  var rows=[],empty='まだ利用履歴はありません。';
  if(acc.data.provisioned){
    var usage=await call('GET','/v1/customer/usage?days=30');
    if(usage.ok){rows=usage.data.by_endpoint||[]}else{empty='利用状況を取得できませんでした（'+detail(usage)+'）。時間をおいて再読み込みしてください。'}
  }
  var body=$('usage-rows');body.textContent='';
  rows.forEach(function(r){var tr=document.createElement('tr');[r.endpoint,r.requests,r.credits].forEach(function(v){var td=document.createElement('td');td.textContent=String(v);tr.appendChild(td)});body.appendChild(tr)});
  $('usage-empty').textContent=empty;
  show($('usage-table'),rows.length>0);show($('usage-empty'),rows.length===0);
  if(!quiet)status('');
}
async function issue(rotate){
  if(rotate&&!confirm('現在のAPIキーは直ちに使えなくなります。再発行しますか？'))return;
  var b=rotate?$('rotate-key'):$('issue-key');busy(b,rotate?'再発行しています…':'発行しています…');
  try{
    var res=await call('POST','/v1/customer/key',{body:{rotate:rotate}});
    if(!res.ok){status('APIキーを発行できませんでした: '+detail(res),'error');return}
    if(res.data.api_key){
      $('new-key-value').textContent=res.data.api_key;$('billing-key').value=res.data.api_key;
      busy($('copy-key'),'');$('copy-key-status').textContent='';show($('new-key'),true);
      status(rotate?'APIキーを再発行しました。旧キーは使えません。新しいキーを今すぐ安全な場所に保存してください。':'APIキーを発行しました。今すぐ安全な場所に保存してください。','ok');
    }else{status(res.data.warning||'既存のキーがあります。','')}
    await loadAccount(true);
  }catch(e){status(NETWORK,'error')}finally{busy(b,'')}
}
var copyTimer=null;
function copied(ok){
  var b=$('copy-key');b.textContent=ok?'コピーしました':'コピーできませんでした';
  $('copy-key-status').textContent=ok?'APIキーをクリップボードにコピーしました。':'コピーできませんでした。キーを選択して手動でコピーしてください。';
  clearTimeout(copyTimer);copyTimer=setTimeout(function(){b.textContent=b.dataset.label||'コピー'},2500);
}
function fallbackCopy(value){var ta=document.createElement('textarea');ta.value=value;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();var ok=false;try{ok=document.execCommand('copy')}catch(e){}finally{document.body.removeChild(ta)}copied(ok)}
async function billing(url,b){
  var key=$('billing-key').value.trim();
  if(!key){status('APIキーを入力してください。発行直後のキーは自動で入力されます。','error');$('billing-key').focus();return}
  var all=[].slice.call(document.querySelectorAll('#billing .actions .btn'));
  all.forEach(function(x){if(x!==b)x.disabled=true});busy(b,'Stripeに接続しています…');
  try{
    var res=await call('POST',url,{key:key});
    if(res.ok&&res.data.url){status('Stripeへ移動しています…','ok');window.location.href=res.data.url;return}
    status('Stripeに接続できませんでした: '+detail(res),'error');
  }catch(e){status(NETWORK,'error')}
  busy(b,'');all.forEach(function(x){x.disabled=false});
}
async function init(){
  status('接続を確認しています…');
  var me=await call('GET','/auth/me');
  if(me.status===503){status('ログイン機能は現在ご利用いただけません: '+detail(me),'error');return}
  var loginFailed=/[?&]login=failed\b/.test(location.search),back=(location.search.match(/[?&]billing=(success|cancel|portal)\b/)||[])[1];
  if((loginFailed||back)&&history.replaceState){history.replaceState(null,'',location.pathname+location.hash)}
  var BACK={success:['お支払いを受け付けました。プランとクレジットはStripeの確認後に反映されます（通常は数十秒）。表示が変わらない場合は再読み込みしてください。','ok'],cancel:['決済はキャンセルされました。プランは変更されていません。',''],portal:['Stripeの請求管理から戻りました。変更内容は確認後に反映されます（通常は数十秒）。','']}[back];
  if(!me.ok){
    show($('signed-in'),false);show($('signed-out'),true);
    if(BACK){status(BACK[0]+' ログインすると現在のプランを確認できます。',BACK[1]);return}
    if(loginFailed){status('Googleでのログインを完了できませんでした。キャンセルされたか、時間切れの可能性があります。下のボタンからもう一度お試しください。','error');return}
    status(location.hash==='#billing'?'有料プランへの変更は、Googleでログインし、APIキーを発行したあとにこのページで行えます。':'ログインするとAPIキー、利用量、請求情報を管理できます。');
    return;
  }
  show($('signed-out'),false);show($('signed-in'),true);
  $('user-email').textContent=(me.data.user&&me.data.user.email)||'—';
  await loadAccount(false);
  if(BACK&&$('status').classList.contains('hidden')){status(BACK[0],BACK[1])}
  if(location.hash==='#billing'||BACK){$('billing').scrollIntoView()}
}
$('issue-key').addEventListener('click',function(){issue(false)});
$('rotate-key').addEventListener('click',function(){issue(true)});
$('copy-key').addEventListener('click',function(){var b=$('copy-key');if(!b.dataset.label)b.dataset.label=b.textContent;var value=$('new-key-value').textContent;if(navigator.clipboard){navigator.clipboard.writeText(value).then(function(){copied(true)}).catch(function(){fallbackCopy(value)})}else{fallbackCopy(value)}});
[].forEach.call(document.querySelectorAll('[data-plan]'),function(b){b.addEventListener('click',function(){billing('/v1/billing/checkout?plan='+b.getAttribute('data-plan'),b)})});
$('portal').addEventListener('click',function(){billing('/v1/billing/portal',$('portal'))});
function start(){init().catch(function(){status(NETWORK,'error')})}
$('retry-account').addEventListener('click',function(){show($('status-actions'),false);start()});
start();
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


def _inline_markdown(value: str) -> str:
    value = html.escape(value, quote=False)
    bt = chr(96)
    value = re.sub(bt + r"([^" + bt + r"]+)" + bt, r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', value)
    # Operator-specific values not yet decided stay visible as placeholders, never guessed.
    value = re.sub(r"［[^］]*］", lambda m: f'<mark class="legal-input">{m.group(0)}</mark>', value)
    return value


def _markdown_to_html(source: str) -> str:
    lines = source.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("> "):
            out.append(f'<blockquote>{_inline_markdown(line[2:])}</blockquote>')
            i += 1
            continue
        if line.startswith("# "):
            out.append(f'<h1>{_inline_markdown(line[2:])}</h1>')
            i += 1
            continue
        if line.startswith("## "):
            out.append(f'<h2>{_inline_markdown(line[3:])}</h2>')
            i += 1
            continue
        if line.startswith("### "):
            out.append(f'<h3>{_inline_markdown(line[4:])}</h3>')
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            headers = [x.strip() for x in line.strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([x.strip() for x in lines[i].strip().strip("|").split("|")])
                i += 1
            head = "".join(f"<th>{_inline_markdown(x)}</th>" for x in headers)
            body = "".join("<tr>" + "".join(f"<td>{_inline_markdown(x)}</td>" for x in row) + "</tr>" for row in rows)
            out.append(f'<div class="table-scroll"><table class="legal-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            continue
        if line.startswith("- ") or line.startswith("* "):
            items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                items.append(f'<li>{_inline_markdown(lines[i].strip()[2:])}</li>')
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,3} |\> |[-*] |\|)", lines[i].strip()):
            paragraph.append(lines[i].strip())
            i += 1
        out.append("<p>" + _inline_markdown(" ".join(paragraph)) + "</p>")
    return "".join(out)


def legal_page(slug: str) -> str | None:
    entry = LEGAL_DOCUMENTS.get(_LEGAL_ALIASES.get(slug, slug))
    if not entry:
        return None
    filename, title = entry
    try:
        source = (_LEGAL_DIR / filename).read_text(encoding="utf-8")
    except OSError:
        return None
    source = re.sub(r"^# .*?\n+", "", source, count=1)
    pending = (
        '<p class="notice mt14 legal-pending">この文書には、運営者が確定する項目（<mark class="legal-input">［ ］</mark>で表示）が残っています。確定までの間、該当箇所は表示のとおり未記入です。</p>'
        if "［" in source else ""
    )
    body = (
        f'<main id="main" class="wrap doc"><div class="doc-crumb"><a href="/">EC Pulse</a><span>/</span>{html.escape(title)}</div>'
        f'<div class="doc-head"><span class="kicker">POLICY / {html.escape(slug.upper())}</span><h1>{html.escape(title)}</h1>{pending}'
        f'<p class="lead">EC Pulse APIをご利用いただく前に、対象のポリシーをご確認ください。</p></div>'
        f'<article class="doc-content" aria-label="{html.escape(title)}本文">{_markdown_to_html(source)}</article>'
        f'<div class="doc-actions"><a class="btn" href="/">トップへ戻る</a><a class="btn primary" href="/account">アカウントを開く</a></div></main>'
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

_NOT_FOUND_BODY = r"""<main id="main" class="wrap page-pad not-found">
<div class="not-found-code">404</div>
<span class="kicker">SIGNAL LOST</span>
<h1 class="h-page mt18">そのページは、<br><em>見つかりません。</em></h1>
<p class="lead mt18">URLが変わったか、まだ公開されていない可能性があります。EC Pulseの主要な入口から続けられます。</p>
<div class="actions mt20">
<a class="btn primary" href="/">EC Pulseへ戻る <span class="arr" aria-hidden="true">→</span></a>
<a class="btn" href="/docs">API Docs</a>
<a class="btn" href="/account">アカウント</a>
</div>
</main>"""

NOT_FOUND_PAGE = _page(
    "ページが見つかりません — EC Pulse API",
    "EC Pulse API のページが見つかりません。",
    _NOT_FOUND_BODY,
)
NOT_FOUND_CSP = csp_for(NOT_FOUND_PAGE)

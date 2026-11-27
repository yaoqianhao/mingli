"""图形化调参界面：把评分拆成线性因子，交给浏览器实时加权。

原理
----
所有引擎的评分都可写成  总分 = Σ (mul_i × w_i)
  mul_i —— 该因子是否被触发（或触发几次、占多少段权重），由盘面决定，前端不可改
  w_i   —— 该因子的权重，滑杆可改

于是前端只需做一次加权求和，不必重写任何命理规则。
拖滑杆 = 改 w，盘面结论实时变色。这是把"规则可调"从命令行延伸到可感知的界面。
"""
import html
import json

_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0e1016;color:#d6dae6;
 font-family:"Sarasa Mono SC","Noto Sans Mono CJK SC",-apple-system,Menlo,monospace;}
.wrap{display:grid;grid-template-columns:minmax(340px,1fr) minmax(380px,520px);
 gap:18px;padding:18px;max-width:1500px;margin:0 auto;align-items:start;}
@media(max-width:960px){.wrap{grid-template-columns:1fr}}
.card{background:#171a23;border:1px solid #262b39;border-radius:12px;overflow:hidden}
.card h2{margin:0;padding:12px 16px;font-size:13px;font-weight:600;letter-spacing:.08em;
 color:#8b93a7;border-bottom:1px solid #262b39;background:#141721}
pre{margin:0;padding:16px;font-size:13px;line-height:1.7;overflow-x:auto;
 font-family:inherit;white-space:pre;}
#verdict{padding:20px 18px;text-align:center;transition:background .25s ease}
#score{font-size:44px;font-weight:700;line-height:1;letter-spacing:-.02em}
#grade{font-size:15px;margin-top:8px;letter-spacing:.2em}
#hint{font-size:12px;margin-top:6px;opacity:.75}
#meter{height:6px;background:#0b0d13;position:relative;border-radius:3px;margin:0 18px 16px}
#meter i{position:absolute;top:-3px;width:3px;height:12px;background:#fff;
 border-radius:2px;transition:left .2s ease;box-shadow:0 0 8px rgba(255,255,255,.7)}
.row{display:grid;grid-template-columns:1fr 120px 58px;gap:10px;align-items:center;
 padding:7px 16px;border-bottom:1px solid #1e2230}
.row:hover{background:#1b1f2b}
.row .lab{font-size:13px;line-height:1.35}
.row .lab em{font-style:normal;color:#6d768a;font-size:11px;margin-left:6px}
input[type=range]{-webkit-appearance:none;width:100%;height:4px;border-radius:2px;
 background:#2c3142;outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:13px;height:13px;
 border-radius:50%;background:#7aa2ff;cursor:pointer;box-shadow:0 0 6px rgba(122,162,255,.6)}
input[type=range]::-moz-range-thumb{width:13px;height:13px;border:0;border-radius:50%;
 background:#7aa2ff;cursor:pointer}
.val{font-size:13px;text-align:right;font-variant-numeric:tabular-nums}
.pos{color:#5fd39a}.neg{color:#e8695f}
.top{display:flex;gap:8px;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid #262b39}
button{background:#222839;color:#c7cfe2;border:1px solid #333b51;border-radius:7px;
 padding:6px 13px;font-size:12px;cursor:pointer;font-family:inherit;transition:.15s}
button:hover{background:#2b3348;border-color:#4a5570}
button.on{background:#3a4a78;border-color:#5f7ac0;color:#e6ecff}
.thr{display:grid;grid-template-columns:1fr 130px 52px;gap:10px;align-items:center;
 padding:6px 16px;font-size:12.5px}
.note{padding:12px 16px;font-size:12px;color:#78819a;line-height:1.7;
 border-top:1px solid #262b39;background:#141721}
#sens{font-size:12px;padding:10px 16px;color:#9aa4bd;border-top:1px solid #1e2230}
</style></head><body>
<div class="wrap">
  <div>
    <div class="card"><h2>盘面</h2><pre>__PANEL__</pre></div>
    <div class="card" style="margin-top:18px">
      <h2>吉凶分界（阈值）</h2>
      <div id="thrs"></div>
      <div class="note">分数跨过阈值，结论就换一个词。把阈值调紧，等于提高"敢下判断"的门槛。</div>
    </div>
  </div>
  <div>
    <div class="card">
      <div id="verdict">
        <div id="score">—</div>
        <div id="grade"></div>
        <div id="hint"></div>
      </div>
      <div id="meter"><i style="left:50%"></i></div>
      <div class="top" id="presets"></div>
      <div id="rows"></div>
      <div id="sens"></div>
      <div class="note">__NOTE__</div>
    </div>
  </div>
</div>
<script>
const DATA = __DATA__;

function hue(score, span){
  let t = Math.max(-1, Math.min(1, score/span));
  return t >= 0 ? 46 + t*74 : 46 + t*46;   // 红(0) ← 黄(46) → 绿(120)
}

function state(){
  let s = 0;
  for (const f of DATA.factors) s += f.mul * f.w;
  return s;
}

function gradeOf(s){
  const t = DATA.thresholds;
  if (s >= t.daji) return ["大吉", t.daji];
  if (s >= t.ji) return ["吉", t.ji];
  if (s > t.ping_lo) return ["平／待定", null];
  if (s > t.xiong) return ["不利", t.ping_lo];
  return ["凶", t.xiong];
}

function render(){
  const s = state();
  const [g, edge] = gradeOf(s);
  const span = Math.max(4, ...DATA.factors.map(f => Math.abs(f.mul * f.w)), 1) * 1.6;
  const h = hue(s, span);
  const v = document.getElementById("verdict");
  v.style.background = `linear-gradient(160deg, hsl(${h},58%,17%), hsl(${h},45%,11%))`;
  v.style.borderBottom = `2px solid hsl(${h},60%,32%)`;
  document.getElementById("score").style.color = `hsl(${h},72%,66%)`;
  document.getElementById("score").textContent = (s >= 0 ? "+" : "") + s.toFixed(1);
  document.getElementById("grade").textContent = g;
  document.getElementById("grade").style.color = `hsl(${h},72%,70%)`;
  let hint = "";
  if (edge !== null) {
    const d = Math.abs(s - edge);
    hint = `距「${g}」的边界 ${d.toFixed(1)} 分`;
  } else {
    hint = "处于中间带，改动任一权重都可能翻盘";
  }
  document.getElementById("hint").textContent = hint;

  const pct = 50 + Math.max(-1, Math.min(1, s/span)) * 50;
  document.querySelector("#meter i").style.left = pct + "%";

  // 因子行
  document.querySelectorAll(".row").forEach((row, i) => {
    const f = DATA.factors[i];
    const contrib = f.mul * f.w;
    const val = row.querySelector(".val");
    val.textContent = (contrib >= 0 ? "+" : "") + contrib.toFixed(1);
    val.className = "val " + (contrib >= 0 ? "pos" : "neg");
    row.querySelector("em").textContent = "\u00d7" + f.mul;
  });

  // 敏感性
  const ranked = DATA.factors.map(f => [f.label, Math.abs(f.mul*f.w)])
                            .sort((a,b) => b[1]-a[1]);
  const totalAbs = ranked.reduce((a,b) => a+b[1], 0) || 1;
  document.getElementById("sens").textContent =
    "影响最大的因子：" + ranked[0][0] + "（占全部力度的 " +
    (ranked[0][1]/totalAbs*100).toFixed(0) + "%）";
}

function buildUI(){
  const rows = document.getElementById("rows");
  DATA.factors.forEach((f, i) => {
    const div = document.createElement("div");
    div.className = "row";
    div.innerHTML = `<div class="lab">${f.label}<em></em></div>
      <input type="range" min="${f.min}" max="${f.max}" step="0.1" value="${f.w}">
      <div class="val">0.0</div>`;
    const slider = div.querySelector("input");
    slider.addEventListener("input", e => {
      DATA.factors[i].w = parseFloat(e.target.value);
      render();
    });
    rows.appendChild(div);
  });

  const thr = document.getElementById("thrs");
  const names = {daji:"大吉 ≥", ji:"吉 ≥", ping_lo:"不利 >", xiong:"凶 ≤"};
  for (const k of ["daji","ji","ping_lo","xiong"]) {
    const div = document.createElement("div");
    div.className = "thr";
    div.innerHTML = `<div>${names[k]}</div>
      <input type="range" min="-12" max="12" step="0.1" value="${DATA.thresholds[k]}">
      <div class="val">${DATA.thresholds[k]}</div>`;
    const slider = div.querySelector("input");
    slider.addEventListener("input", e => {
      DATA.thresholds[k] = parseFloat(e.target.value);
      div.querySelector(".val").textContent = e.target.value;
      refreshPresetButtons();
      render();
    });
    thr.appendChild(div);
  }

  const pre = document.getElementById("presets");
  const def = document.createElement("button");
  def.textContent = "默认";
  def.onclick = () => { resetTo(DATA.defaults); };
  pre.appendChild(def);
  for (const [name, cfg] of Object.entries(DATA.presets)) {
    const b = document.createElement("button");
    b.textContent = name;
    b.dataset.name = name;
    b.onclick = () => { resetTo(cfg); markPreset(name); };
    pre.appendChild(b);
  }
  refreshPresetButtons();
}

function resetTo(cfg){
  DATA.factors.forEach(f => { if (cfg.w && cfg.w[f.key] !== undefined) f.w = cfg.w[f.key]; });
  if (cfg.thresholds) Object.assign(DATA.thresholds, cfg.thresholds);
  rebuildSliders();
  markPreset(null);
  render();
}

function rebuildSliders(){
  document.querySelectorAll(".row").forEach((row, i) => {
    row.querySelector("input").value = DATA.factors[i].w;
  });
  const ks = ["daji","ji","ping_lo","xiong"];
  document.querySelectorAll("#thrs .thr").forEach((row, i) => {
    row.querySelector("input").value = DATA.thresholds[ks[i]];
    row.querySelector(".val").textContent = DATA.thresholds[ks[i]];
  });
}

function markPreset(name){
  document.querySelectorAll("#presets button").forEach(b => {
    b.classList.toggle("on", b.dataset.name === name);
  });
}

function refreshPresetButtons(){}

buildUI();
render();
</script>
</body></html>
"""


def make_factor(key, label, mul, w):
    span = max(4.0, abs(w) * 3, 2.0)
    return {"key": key, "label": label, "mul": mul, "w": w,
            "min": round(-span, 1), "max": round(span, 1)}


def page(title: str, panel: str, factors: list[dict], thresholds: dict,
         presets: dict, note: str = "") -> str:
    data = {
        "factors": factors,
        "thresholds": thresholds,
        "defaults": {"w": {f["key"]: f["w"] for f in factors},
                     "thresholds": dict(thresholds)},
        "presets": presets,
    }
    return (_PAGE
            .replace("__TITLE__", html.escape(title))
            .replace("__PANEL__", html.escape(panel))
            .replace("__NOTE__", note or "拖滑杆即改权重，得分与结论实时变化。")
            .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))


def write(path: str, content: str):
    import os
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

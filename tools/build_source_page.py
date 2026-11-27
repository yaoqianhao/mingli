#!/usr/bin/env python3
"""生成 source-code.html：把 source/mingli/ 下的源码渲染成自包含的单页浏览界面。

用法（在仓库根目录执行）：

    python3 tools/build_source_page.py

页面没有任何外部依赖：侧栏目录、行号、语法高亮和文件内容全部内嵌在一个 HTML 里，
双击即可离线阅读。文件清单、分组与行数都从磁盘现读，不会和源码脱节。
"""
from __future__ import annotations

import html
import io
import json
import keyword
import pathlib
import sys
import tokenize

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "source" / "mingli"
OUT = ROOT / "source-code.html"

# 分组 → [(文件名, 一句话说明)]
GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("历法 · 符号层", [
        ("calendar.py", "儒略日、太阳黄经、二十四节气、真太阳时、四柱"),
        ("lunar.py", "朔的推算与闰月判定"),
        ("jiazi.py", "干支、藏干、十神、纳音、十二长生"),
    ]),
    ("命理", [
        ("bazi.py", "八字：十神、藏干、旺衰计分、大运"),
        ("ziwei.py", "紫微斗数：命身宫、五行局、十四主星、四化"),
    ]),
    ("卜筮", [
        ("liuyao.py", "六爻纳甲：八宫、世应、六亲、旬空、动变、用神评分"),
        ("meihua.py", "梅花易数：数起卦、时间起卦、体用互变"),
        ("qimen.py", "奇门遁甲：阴阳遁、三元定局、天地人神四盘"),
        ("liuren.py", "大六壬：月将过宫、四课、三传九宗门、十二天将"),
    ]),
    ("规则与工程", [
        ("rules.py", "权重参数、预设、JSON 存取"),
        ("web.py", "图形化调参页生成（滑杆 + 实时加权）"),
        ("calibrate.py", "校准：逻辑回归反推权重、交叉验证、bootstrap 区间"),
        ("caselog.py", "案例库：预注册、双段哈希链、校准曲线"),
        ("cli.py", "命令行与交互模式"),
        ("utils.py", "终端对齐（按东亚字符宽度）"),
    ]),
    ("包与测试", [
        ("__init__.py", "包元信息"),
        ("__main__.py", "python3 -m mingli 入口"),
        ("tests.py", "回归测试"),
    ]),
]

CSS = """\
*{box-sizing:border-box}
body{margin:0;background:#0d0f15;color:#c9cfdd;height:100vh;overflow:hidden;
 font-family:"Sarasa Mono SC","Noto Sans Mono CJK SC",Menlo,monospace}
.app{display:grid;grid-template-columns:252px 1fr;height:100vh}
aside{background:#12151d;border-right:1px solid #232838;overflow-y:auto;padding:14px 0}
h1{font-size:13px;font-weight:600;color:#8b93a7;letter-spacing:.12em;
 margin:0 0 4px 16px;padding-bottom:10px}
.sub{font-size:11px;color:#5c6478;margin:0 0 10px 16px}
.grp{font-size:10.5px;color:#4e566a;letter-spacing:.14em;margin:14px 16px 5px}
a{display:block;padding:6px 16px;font-size:12.5px;color:#9aa4bd;cursor:pointer;
 border-left:2px solid transparent;white-space:nowrap;text-decoration:none}
a:hover{background:#1a1f2b;color:#d6dcea}
a.on{background:#1c2434;color:#7aa2ff;border-left-color:#7aa2ff}
a i{float:right;font-style:normal;font-size:10.5px;color:#4e566a}
a em{display:block;font-style:normal;font-size:10.5px;color:#5c6478;margin-top:1px}
main{overflow:auto;position:relative}
header{position:sticky;top:0;background:#0d0f15ee;backdrop-filter:blur(8px);
 border-bottom:1px solid #232838;padding:12px 20px;font-size:12px;color:#7d869e;
 display:flex;justify-content:space-between;gap:16px;z-index:5}
header b{color:#c9cfdd;font-weight:500}
header a{display:inline;padding:0;color:#7aa2ff;font-size:12px}
pre{margin:0;padding:18px 20px 60px;font-size:12.5px;line-height:1.65;
 font-family:inherit;white-space:pre;tab-size:4}
.ln{color:#333b4d;user-select:none;display:inline-block;width:3.2em;text-align:right;
 padding-right:1.2em}
.kw{color:#c792ea}.str{color:#a5d6a7}.cm{color:#4e566a;font-style:italic}
.num{color:#f0a35e}
"""

JS = """\
const F = %(files)s;
const NAMES = %(names)s;
const pre = document.getElementById('code');
const fn = document.getElementById('fn');
const fl = document.getElementById('fl');
function show(name) {
  pre.innerHTML = F[name] || '';
  fn.textContent = 'source/mingli/' + name;
  fl.textContent = NAMES[name] + ' 行';
  for (const a of document.querySelectorAll('aside a')) a.classList.toggle('on', a.dataset.f === name);
  location.hash = name;
  document.querySelector('main').scrollTop = 0;
}
for (const a of document.querySelectorAll('aside a')) a.onclick = () => show(a.dataset.f);
const first = Object.keys(NAMES)[0];
const want = decodeURIComponent(location.hash.slice(1));
show(NAMES[want] ? want : first);
"""


def _classify(tok_type: int, text: str) -> str | None:
    if tok_type == tokenize.COMMENT:
        return "cm"
    if tok_type == tokenize.STRING:
        return "str"
    if tok_type == tokenize.NUMBER:
        return "num"
    if tok_type == tokenize.NAME and keyword.iskeyword(text):
        return "kw"
    return None


def _spans(source: str) -> dict[int, list[tuple[int, int, str]]]:
    """按行收集 (起列, 止列, css 类)，跨行字符串拆到各行。"""
    lines = source.splitlines()
    found: dict[int, list[tuple[int, int, str]]] = {}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return found
    for tok in tokens:
        cls = _classify(tok.type, tok.string)
        if cls is None:
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        for row in range(srow, erow + 1):
            if row < 1 or row > len(lines):
                continue
            start = scol if row == srow else 0
            end = ecol if row == erow else len(lines[row - 1])
            if end > start:
                found.setdefault(row, []).append((start, end, cls))
    return found


def render(source: str) -> str:
    """把一段源码渲染成带行号与高亮的 HTML 行。"""
    lines = source.splitlines()
    spans = _spans(source)
    out: list[str] = []
    for no, line in enumerate(lines, start=1):
        line = line.expandtabs(4)
        parts: list[str] = []
        cursor = 0
        for start, end, cls in sorted(spans.get(no, [])):
            start, end = max(0, start), min(len(line), end)
            if start < cursor or end <= start:
                continue
            parts.append(html.escape(line[cursor:start]))
            parts.append(f'<span class="{cls}">{html.escape(line[start:end])}</span>')
            cursor = end
        parts.append(html.escape(line[cursor:]))
        out.append(f'<span class="ln">{no}</span>{"" if line else ""}' + "".join(parts))
    return "\n".join(out)


def main(argv: list[str]) -> None:
    out = pathlib.Path(argv[1]) if len(argv) > 1 else OUT
    files: dict[str, str] = {}
    counts: dict[str, int] = {}
    sidebar: list[str] = []
    total = 0
    for group, entries in GROUPS:
        sidebar.append(f'<div class="grp">{html.escape(group)}</div>')
        for name, desc in entries:
            path = PKG / name
            source = path.read_text(encoding="utf-8")
            files[name] = render(source)
            counts[name] = len(source.splitlines())
            total += counts[name]
            sidebar.append(
                f'<a data-f="{name}">{name}<i>{counts[name]}</i>'
                f"<em>{html.escape(desc)}</em></a>"
            )
    payload = json.dumps(files, ensure_ascii=False).replace("</", "<\\/")
    names = json.dumps(counts, ensure_ascii=False)
    script = JS % {"files": payload, "names": names}
    page = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>命理推演器 · 源码总览</title>
<style>
{CSS}</style></head><body>
<div class="app">
<aside>
  <h1>命理推演器</h1>
  <div class="sub">{len(files)} 个文件 · {total:,} 行</div>
{chr(10).join(sidebar)}
</aside>
<main>
<header><span><b id="fn"></b>　<span id="fl"></span></span>
<a href="index.html">← 项目首页</a></header>
<pre id="code"></pre>
</main>
</div>
<script>
{script}
</script>
</body></html>
"""
    out.write_text(page, encoding="utf-8", newline="\n")
    print(f"写入 {out}：{len(files)} 个文件 / {total} 行")


if __name__ == "__main__":
    main(sys.argv)

"""命令行入口：python3 -m mingli <子命令>　（不带子命令则进入交互模式）"""
import argparse
import sys
from datetime import datetime

from . import bazi as bazi_mod
from . import liuyao as liuyao_mod
from . import meihua as meihua_mod
from . import qimen as qimen_mod
from .calendar import four_pillars, jieqi_of_year
from .lunar import lunar_date
from .rules import Rules, PRESETS
from . import liuren as liuren_mod
from . import ziwei as ziwei_mod
from . import calibrate as calib
from . import caselog as caselog_mod
from . import web as web_mod

ASK_MAP = {
    "财": "妻财", "求财": "妻财", "钱": "妻财", "买卖": "妻财",
    "官": "官鬼", "工作": "官鬼", "功名": "官鬼", "事业": "官鬼", "病": "官鬼",
    "父": "父母", "文书": "父母", "房": "父母", "长辈": "父母", "考试": "父母",
    "子": "子孙", "子女": "子孙", "医药": "子孙", "健康": "子孙",
    "兄": "兄弟", "朋友": "兄弟", "合伙": "兄弟", "竞争": "兄弟",
}

HTML_HEAD = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>推演盘</title>
<style>
body{background:#12131a;color:#d8dbe6;font-family:"Sarasa Mono SC","Noto Sans Mono CJK SC",Menlo,monospace;
     display:flex;justify-content:center;padding:36px 18px;}
pre{background:#191b24;border:1px solid #2b2f3d;border-radius:10px;padding:26px 30px;
    line-height:1.75;font-size:14px;box-shadow:0 8px 30px rgba(0,0,0,.45);overflow-x:auto;}
</style></head><body><pre>
"""
HTML_TAIL = "\n</pre></body></html>\n"


def emit(text: str, html_path: str | None = None):
    if html_path:
        import os
        os.makedirs(os.path.dirname(os.path.abspath(html_path)), exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(HTML_HEAD + text.replace("&", "&amp;").replace("<", "&lt;") + HTML_TAIL)
        print(f"已导出：{html_path}")
        print(text)
    else:
        print(text)


def parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"时间格式无法识别：{s}（示例：2026-11-27 15:30）")


def build_rules(a) -> Rules:
    r = Rules()
    if getattr(a, "rules_file", None):
        r = Rules.load(a.rules_file)
    if getattr(a, "preset", None):
        r.apply_preset(a.preset)
    if getattr(a, "set", None):
        r.apply_overrides(a.set)
    return r


def _daymonth(dt, lng=120.0, tz=8.0):
    q = four_pillars(dt, lng, tz)
    return q.day, q.month[1]


def month_zhi_of(dt: datetime | None, lng: float = 120.0, tz: float = 8.0) -> str:
    return four_pillars(dt or datetime.now(), lng, tz).month[1]


# ---------------- 各业务函数 ----------------
def do_bazi(dt, lng=120.0, tz=8.0, gender="m", day23=False, rules=None):
    b = bazi_mod.build(dt, lng, tz, gender, day23, rules)
    return bazi_mod.render(b)


def do_liuyao_coins(backs, dt=None, day_gz=None, month_zhi=None, ask=None,
                    lng=120.0, tz=8.0, rules=None):
    stamp = ""
    if dt:
        p = four_pillars(dt, lng, tz)
        day_gz, month_zhi = p.day, p.month[1]
        stamp = f"起卦时间 {dt:%Y-%m-%d %H:%M}　四柱 {p.year} {p.month} {p.day} {p.hour}\n"
    chart = liuyao_mod.cast_from_coins(backs, day_gz, month_zhi, rules)
    return stamp + liuyao_mod.render(chart, ASK_MAP.get(ask, ask) if ask else None)


def do_liuyao_named(name, moves, dt=None, day_gz=None, month_zhi=None, ask=None,
                    lng=120.0, tz=8.0, rules=None):
    stamp = ""
    if dt:
        p = four_pillars(dt, lng, tz)
        day_gz, month_zhi = p.day, p.month[1]
        stamp = f"起卦时间 {dt:%Y-%m-%d %H:%M}　四柱 {p.year} {p.month} {p.day} {p.hour}\n"
    chart = liuyao_mod.cast_from_hexagram(name, moves, day_gz, month_zhi, rules)
    return stamp + liuyao_mod.render(chart, ASK_MAP.get(ask, ask) if ask else None)


def do_meihua_nums(a, b, month_zhi=None, rules=None):
    return meihua_mod.render(meihua_mod.cast_by_numbers(a, b, rules=rules), month_zhi)


def do_meihua_time(dt, lng=120.0, tz=8.0, solar_nums=False, rules=None):
    c = meihua_mod.cast_by_time(dt, lng, tz, use_lunar=not solar_nums, rules=rules)
    return meihua_mod.render(c, four_pillars(dt, lng, tz).month[1])


def do_liuren(dt, lng=120.0, tz=8.0, rules=None):
    c = liuren_mod.build(dt, lng, tz, rules)
    ev = c.evaluate()
    return liuren_mod.render(c) + f"\n\n【评分】{ev['score']:+.1f} → {ev['grade']}"


def do_ziwei(dt, lng=120.0, tz=8.0, gender="m", rules=None):
    c = ziwei_mod.build(dt, lng, tz, gender, rules)
    return ziwei_mod.render(c)


def do_qimen(dt, lng=120.0, tz=8.0, rules=None):
    return qimen_mod.render(qimen_mod.build(dt, lng, tz, rules))


def do_jieqi(year, tz=8.0):
    out = [f"{year} 年二十四节气（UTC{tz:+g}）"]
    jie_names = {"立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
                 "立秋", "白露", "寒露", "立冬", "大雪", "小寒"}
    for name, t in jieqi_of_year(year, tz):
        out.append(f"  {name}　{t}" + ("　← 节（换月建）" if name in jie_names else ""))
    return "\n".join(out)


def do_lunar(dt, lng=120.0, tz=8.0):
    ld = lunar_date(dt, tz)
    p = four_pillars(dt, lng, tz)
    return (f"公历 {dt:%Y-%m-%d %H:%M}　→　农历 {ld['year']} 年 "
            f"{ld['month_name']}{ld['day_cn']}日\n"
            f"四柱：{p.year} {p.month} {p.day} {p.hour}\n"
            f"真太阳时：{p.meta['true_solar_time']}　节令：{p.meta['month_jie']}")


def _flat_dict(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat_dict(v, key))
        else:
            out[key] = v
    return out


def do_slider(engine, rules, **kw):
    """生成图形化调参页。返回 (html, 路径)。"""
    if engine == "liuyao":
        chart = kw["chart"]
        ask = ASK_MAP.get(kw.get("ask"), kw.get("ask")) if kw.get("ask") else None
        if not ask:
            raise SystemExit("六爻调参页需要 --ask 指定用神（财/官/父/子/兄）")
        ev = chart.evaluate(ask)
        panel = liuyao_mod.render(chart, ask, with_score=False)
        items = ev["items"]
        th = rules.get("liuyao.thresholds")
        prefix = "liuyao"
        title = f"六爻 · 用神{ask}"
    elif engine == "meihua":
        c = kw["chart"]
        sc = c.score(kw.get("month_zhi"))
        panel = meihua_mod.render(c, kw.get("month_zhi"), with_score=False)
        items = sc["items"]
        th = rules.get("meihua.thresholds")
        prefix = "meihua"
        title = "梅花易数 · 体用"
    elif engine == "qimen":
        c = kw["chart"]
        panel = qimen_mod.render(c, with_score=False)
        fac = c.factors()
        th = rules.get("qimen.thresholds")
        factors = [web_mod.make_factor(f["key"], f["label"], f["mul"], f["w"]) for f in fac]
        prefix = "qimen"
        items = None
        title = f"奇门 · {c.dun}遁{c.ju}局"
    elif engine == "liuren":
        c = kw["chart"]
        panel = liuren_mod.render(c)
        ev = c.evaluate()
        items = ev["items"]
        th = rules.get("liuren.thresholds")
        prefix = "liuren"
        title = f"大六壬 · {c.keti}"
    elif engine == "ziwei":
        c = kw["chart"]
        panel = ziwei_mod.render(c)
        fac = c.factors()
        th = rules.get("ziwei.thresholds")
        factors = [web_mod.make_factor(f["key"], f["label"], f["mul"], f["w"]) for f in fac]
        prefix = "ziwei"
        items = None
        title = f"紫微斗数 · {c.ju_name}"
    else:
        raise SystemExit("engine 只能是 liuyao / meihua / qimen / liuren")

    if items is not None:
        factors = []
        for it in items:
            raw = it["key"]
            key = raw if raw.startswith(prefix + ".") else f"{prefix}.{raw}"
            w = rules.get(key, it["delta"])
            factors.append(web_mod.make_factor(key, it["desc"], it.get("mul", 1), w))

    presets = {}
    for name, cfg in PRESETS.items():
        sub = cfg.get(prefix)
        if sub:
            presets[name] = {"w": {f"{prefix}.{k}": v for k, v in _flat_dict(sub).items()
                                   if not k.startswith("thresholds")},
                             "thresholds": sub.get("thresholds")}

    return web_mod.page(title, panel, factors, th, presets)


def _predict(engine, a, rules):
    """跑盘得到 (input_data, score, grade)。score/grade 一律由程序算出。"""
    from .rules import grade as _grade
    if engine == "liuyao":
        dt = a.date
        if a.coins:
            backs = ([int(x) for x in a.coins.replace("，", ",").split(",") if x.strip()]
                     if isinstance(a.coins, str) else list(a.coins))
            if a.date:
                p = four_pillars(a.date, a.lng, a.tz)
                dg, mz = p.day, p.month[1]
                inp = {"date": a.date.strftime("%Y-%m-%d %H:%M"), "coins": backs,
                       "ask": a.ask or ""}
            else:
                dg, mz = a.day, a.month
                inp = {"coins": backs, "day": dg, "month": mz, "ask": a.ask or ""}
            chart = liuyao_mod.cast_from_coins(backs, dg, mz, rules)
        else:
            moves = [] if (a.moves or "0").strip() == "0" else [int(x) for x in a.moves.split(",")]
            if a.date:
                p = four_pillars(a.date, a.lng, a.tz)
                dg, mz = p.day, p.month[1]
                inp = {"date": a.date.strftime("%Y-%m-%d %H:%M"),
                       "hexagram": a.hexagram, "moves": moves, "ask": a.ask or ""}
            else:
                dg, mz = a.day, a.month
                inp = {"hexagram": a.hexagram, "moves": moves, "day": dg,
                       "month": mz, "ask": a.ask or ""}
            chart = liuyao_mod.cast_from_hexagram(a.hexagram, moves, dg, mz, rules)
        ask = ASK_MAP.get(a.ask, a.ask) if a.ask else None
        if not ask:
            raise SystemExit("六爻录入必须给 --ask，否则无从取用神")
        ev = chart.evaluate(ask)
        return inp, ev["score"], ev["grade"]

    if engine == "meihua":
        dt = a.date or datetime.now()
        if a.nums:
            parts = [int(x) for x in a.nums.replace("，", ",").split(",")]
            c = meihua_mod.cast_by_numbers(parts[0], parts[1], rules=rules)
            inp = {"nums": parts, "month": month_zhi_of(a.date, a.lng, a.tz)}
        else:
            c = meihua_mod.cast_by_time(dt, a.lng, a.tz, rules=rules)
            inp = {"date": dt.strftime("%Y-%m-%d %H:%M")}
        mz = a.month if (a.nums and getattr(a, "month", None)) else \
            month_zhi_of(dt, a.lng, a.tz)
        sc = c.score(mz)
        return inp, sc["score"], sc["grade"]

    dt = a.date or datetime.now()
    if engine == "qimen":
        c = qimen_mod.build(dt, a.lng, a.tz, rules)
        total = sum(f["mul"] * f["w"] for f in c.factors())
        return ({"date": dt.strftime("%Y-%m-%d %H:%M")}, total,
                _grade(total, rules.get("qimen.thresholds")))

    if engine == "liuren":
        c = liuren_mod.build(dt, a.lng, a.tz, rules)
        ev = c.evaluate()
        return ({"date": dt.strftime("%Y-%m-%d %H:%M")}, ev["score"], ev["grade"])

    if engine == "ziwei":
        c = ziwei_mod.build(dt, a.lng, a.tz, a.gender, rules)
        total = sum(f["mul"] * f["w"] for f in c.factors())
        return ({"date": dt.strftime("%Y-%m-%d %H:%M"), "gender": a.gender},
                total, _grade(total, rules.get("ziwei.thresholds")))

    raise SystemExit(f"未知引擎：{engine}")


def do_log(a) -> str:
    log = caselog_mod.CaseLog(a.db)
    cmd = a.logcmd

    if cmd == "add":
        if not a.engine:
            raise SystemExit("log add 需要 --engine")
        inp, score, grade = _predict(a.engine, a, build_rules(a))
        rec = log.add(a.engine, inp, score, grade, ask=a.ask or "", note=a.note or "")
        return (f"已锁定预测 {rec['id']}\n"
                f"  引擎 {rec['engine']}　分数 {rec['score']:+.1f}　判词「{rec['grade']}」\n"
                f"  摘要 {rec['pred_hash']}\n"
                f"  此条已不可修改。事件落定后："
                f"log resolve {rec['id']} --result 1（吉）或 0（凶）")

    if cmd == "list":
        pending = True if a.pending else (False if a.resolved else None)
        rows = log.listing(pending=pending, engine=a.engine)
        return caselog_mod.render_list(log, rows)

    if cmd == "resolve":
        r = log.resolve(a.id, 1 if a.result in ("1", "吉", "y", "yes") else 0,
                        note=a.note or "")
        return (f"已回填 {r['id']}：{'吉' if r['result'] else '凶'}　"
                f"原判「{r['grade']}」（{r['score']:+.1f}）　"
                + ("命中" if (r['grade'] in ('吉', '大吉')) == bool(r['result'])
                   else "未中"))

    if cmd == "verify":
        ok, errs = log.verify()
        if ok:
            return f"哈希链完整：{len(log.records)} 条记录，无篡改迹象。"
        return "校验失败：\n" + "\n".join("  · " + e for e in errs)

    if cmd == "stats":
        return caselog_mod.render_stats(log)

    if cmd == "compare":
        return caselog_mod.compare(log, a.a, a.b, lng=a.lng, tz=a.tz,
                                   segments=a.segments)

    if cmd == "demo":
        # 生成一个演示库：按默认权重模拟结果 + 噪声，**不是真实占验**
        from .calibrate import make_demo
        import tempfile, json as _json, os as _os
        tmp = _os.path.join(tempfile.mkdtemp(), "d.json")
        make_demo(tmp, a.n, seed=2026)
        raw = _json.load(open(tmp, encoding="utf-8"))
        rules = build_rules(a)
        for case in raw["cases"]:
            class _NS:
                pass
            ns = _NS()
            ns.engine, ns.lng, ns.tz, ns.gender = "liuyao", 120.0, 8.0, "m"
            ns.coins, ns.hexagram, ns.moves, ns.nums = case["coins"], None, None, None
            ns.day = ns.month = None
            ns.ask = case["ask"]
            ns.date = datetime.strptime(case["date"], "%Y-%m-%d %H:%M")
            ns.preset = ns.set = ns.rules_file = None
            inp, score, grade = _predict("liuyao", ns, rules)
            rec = log.add("liuyao", inp, score, grade, ask=case["ask"],
                          note="演示数据（合成）")
            if a.resolve_demo:
                log.resolve(rec["id"], case["result"], note="合成结果")
        return (f"已生成演示库：{a.db}（{len(raw['cases'])} 条）\n"
                f"⚠ 这些是按默认权重模拟出来的，**不是真实占验记录**，只用来看流程。")

    if cmd == "export":
        cases = log.export(engine=a.engine)
        if not cases:
            return "没有可导出的已决案例。"
        import json as _json
        payload = {"_note": f"由案例记录库导出，engine={a.engine or 'mixed'}",
                   "engine": a.engine or "liuyao", "cases": cases}
        path = a.out or "output/cases_export.json"
        import os as _os
        _os.makedirs(_os.path.dirname(_os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(payload, f, ensure_ascii=False, indent=1)
        return (f"已导出 {len(cases)} 条到 {path}\n"
                f"接着跑：python3 -m mingli calibrate --data {path}")

    return "用法：log {add|list|resolve|verify|stats|export}"


def do_calibrate(a) -> str:
    import json as _json
    if a.make_demo:
        path = calib.make_demo(a.make_demo, a.cases)
        return (f"已生成合成数据：{path}\n"
                f"（按默认权重模拟 + 15% 噪声，**不是真实占验记录**，仅演示流程）\n\n"
                f"接着跑：python3 -m mingli calibrate --data {path}")

    with open(a.data, encoding="utf-8") as f:
        payload = _json.load(f)
    engine = a.engine or payload.get("engine")
    if not engine:
        raise SystemExit("数据文件里没有 engine 字段，请用 --engine 指定")
    cases = payload["cases"] if isinstance(payload, dict) else payload

    text, summary = calib.report(engine, cases, l2=a.l2, n_boot=a.boot,
                                 lng=a.lng, tz=a.tz, default_rules=build_rules(a))

    if a.emit and summary:
        from .rules import Rules as _R
        r = _R()
        for k, v in summary["weights"].items():
            r.set(k, round(v, 3))
        r.save(a.emit)
        text += (f"\n\n已导出权重：{a.emit}\n"
                 f"注意：这组权重是配合「score > 0 判吉」使用的，与原来的分档阈值"
                 f"不在同一尺度上。要载入需同时调整 {engine}.thresholds。")
    return text


def do_rules(rules: Rules) -> str:
    out = ["当前规则参数（点号路径 → 数值）：", ""]
    groups = {}
    for k, v in rules.flat():
        groups.setdefault(k.split(".")[0], []).append((k, v))
    for g, items in groups.items():
        out.append(f"[{g}]")
        for k, v in items:
            out.append(f"  {k:<34}{v}")
        out.append("")
    out.append(f"可用预设：{', '.join(PRESETS)}")
    out.append('调参示例：--set "liuyao.month.po=-5" --set "meihua.stage.hu=0.5"')
    out.append("        --preset classic　--rules-file my.json　--save-rules my.json")
    return "\n".join(out)


# ---------------- argparse ----------------
def build_parser():
    ap = argparse.ArgumentParser(
        prog="mingli", description="传统术数推演器（干支历 / 六爻 / 梅花 / 八字 / 奇门）")
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("--date", type=parse_dt, help="时间，如 '2026-11-27 15:30'")
        p.add_argument("--lng", type=float, default=120.0, help="经度（东经正），默认 120")
        p.add_argument("--tz", type=float, default=8.0, help="时区，默认 8")
        p.add_argument("--day23", action="store_true", help="以 23:00 换日（夜子时法）")
        p.add_argument("--html", help="同时导出 HTML 到指定路径")
        p.add_argument("--preset", choices=list(PRESETS), help="规则预设")
        p.add_argument("--set", action="append", metavar="K=V", help="逐项覆盖规则参数，可多次")
        p.add_argument("--rules-file", help="从 JSON 载入规则")
        p.add_argument("--save-rules", help="把最终规则另存为 JSON")

    p1 = sub.add_parser("bazi", help="排八字、十神、旺衰、大运")
    common(p1)
    p1.add_argument("--gender", choices=["m", "f"], default="m")
    p1.set_defaults(func=cmd_bazi)

    p2 = sub.add_parser("liuyao", help="六爻装卦断卦")
    common(p2)
    p2.add_argument("--coins", help="六次摇卦的背数 0-3，逗号分隔，自初爻起")
    p2.add_argument("--hexagram", help="已知卦名，如 天火同人")
    p2.add_argument("--moves", help="动爻位置，如 1,4；无动爻写 0")
    p2.add_argument("--day", help="日干支，如 戊午（不给 --date 时必填）")
    p2.add_argument("--month", help="月支，如 寅（不给 --date 时必填）")
    p2.add_argument("--ask", help="所问之事：财/官/父/子/兄，用于取用神")
    p2.set_defaults(func=cmd_liuyao)

    p3 = sub.add_parser("meihua", help="梅花易数起卦")
    common(p3)
    p3.add_argument("--nums", help="两个数字，如 37,82")
    p3.add_argument("--solar-nums", action="store_true", help="时间起卦改用公历数")
    p3.set_defaults(func=cmd_meihua)

    p4 = sub.add_parser("qimen", help="奇门遁甲起局（时家转盘）")
    common(p4)
    p4.set_defaults(func=cmd_qimen)

    p5 = sub.add_parser("jieqi", help="某年二十四节气表")
    p5.add_argument("year", type=int)
    p5.add_argument("--tz", type=float, default=8.0)
    p5.add_argument("--html", help="导出 HTML")
    p5.set_defaults(func=cmd_jieqi)

    p6 = sub.add_parser("lunar", help="公历转农历 + 四柱")
    common(p6)
    p6.set_defaults(func=cmd_lunar)

    p10 = sub.add_parser("ziwei", help="紫微斗数排盘（十四主星·四化·大限）")
    common(p10)
    p10.add_argument("--gender", choices=["m", "f"], default="m")
    p10.set_defaults(func=cmd_ziwei)

    p9 = sub.add_parser("liuren", help="大六壬起课（四课三传）")
    common(p9)
    p9.set_defaults(func=cmd_liuren)

    p8 = sub.add_parser("slider", help="生成图形化调参页（拖动权重实时看结论变化）")
    common(p8)
    p8.add_argument("--engine", required=True,
                    choices=["liuyao", "meihua", "qimen", "liuren", "ziwei"])
    p8.add_argument("--gender", choices=["m", "f"], default="m", help="紫微用")
    p8.add_argument("--coins", help="六爻：摇卦背数 0-3")
    p8.add_argument("--hexagram", help="六爻：卦名")
    p8.add_argument("--moves", help="六爻：动爻位置")
    p8.add_argument("--day", help="日干支（不给 --date 时用）")
    p8.add_argument("--month", help="月支（不给 --date 时用）")
    p8.add_argument("--ask", help="六爻：用神（财/官/父/子/兄）")
    p8.add_argument("--nums", help="梅花：两个数字")
    p8.add_argument("--solar-nums", action="store_true")
    p8.add_argument("--out", default="output/slider.html", help="输出路径")
    p8.set_defaults(func=cmd_slider)

    plog = sub.add_parser("log", help="案例记录：先锁预测，后填结果")
    logsub = plog.add_subparsers(dest="logcmd")
    plog.add_argument("--db", default="output/cases.json", help="记录库路径")

    def _logcommon(p):
        p.add_argument("--db", default=argparse.SUPPRESS, help="记录库路径")

    pa = logsub.add_parser("add", help="录入并锁定一次预测")
    _logcommon(pa)
    pa.add_argument("--engine", required=True,
                    choices=["liuyao", "meihua", "qimen", "liuren", "ziwei"])
    pa.add_argument("--date", type=parse_dt, help="起课时间（默认当前）")
    pa.add_argument("--lng", type=float, default=120.0)
    pa.add_argument("--tz", type=float, default=8.0)
    pa.add_argument("--gender", choices=["m", "f"], default="m")
    pa.add_argument("--coins"), pa.add_argument("--hexagram"), pa.add_argument("--moves")
    pa.add_argument("--nums")
    pa.add_argument("--day", help="日干支（不给 --date 时用）")
    pa.add_argument("--month", help="月支（不给 --date 时用）")
    pa.add_argument("--ask", help="所问何事（财/官/父/子/兄）")
    pa.add_argument("--note", help="备注：问的具体是什么事")
    pa.add_argument("--preset", choices=list(PRESETS))
    pa.add_argument("--set", action="append", metavar="K=V")
    pa.add_argument("--rules-file")
    pa.set_defaults(func=cmd_log)

    pb = logsub.add_parser("list", help="列出记录")
    _logcommon(pb)
    pb.add_argument("--pending", action="store_true", help="只看待决")
    pb.add_argument("--resolved", action="store_true", help="只看已决")
    pb.add_argument("--engine")
    pb.set_defaults(func=cmd_log)

    pcr = logsub.add_parser("resolve", help="回填结果")
    _logcommon(pcr)
    pcr.add_argument("id")
    pcr.add_argument("--result", required=True, help="1 吉 / 0 凶")
    pcr.add_argument("--note")
    pcr.set_defaults(func=cmd_log)

    pv = logsub.add_parser("verify", help="校验哈希链")
    _logcommon(pv)
    pv.set_defaults(func=cmd_log)

    ps = logsub.add_parser("stats", help="统计与校准曲线")
    _logcommon(ps)
    ps.set_defaults(func=cmd_log)

    pcm = logsub.add_parser("compare", help="同一批案例上比较两套规则集")
    _logcommon(pcm)
    pcm.add_argument("--a", default="default", help="规则集 A：default / 预设名 / @文件")
    pcm.add_argument("--b", required=True, help="规则集 B：default / 预设名 / @文件")
    pcm.add_argument("--lng", type=float, default=120.0)
    pcm.add_argument("--tz", type=float, default=8.0)
    pcm.add_argument("--segments", type=int, default=2, help="时间分段数，默认 2")
    pcm.set_defaults(func=cmd_log)

    pd = logsub.add_parser("demo", help="生成演示用记录库（合成数据）")
    _logcommon(pd)
    pd.add_argument("--n", type=int, default=30)
    pd.add_argument("--resolve-demo", action="store_true", help="同时填入合成结果")
    pd.add_argument("--preset", choices=list(PRESETS))
    pd.add_argument("--set", action="append", metavar="K=V")
    pd.add_argument("--rules-file")
    pd.set_defaults(func=cmd_log)

    pe = logsub.add_parser("export", help="导出给 calibrate")
    _logcommon(pe)
    pe.add_argument("--engine")
    pe.add_argument("--out")
    pe.set_defaults(func=cmd_log)

    pc = sub.add_parser("calibrate", help="用案例批量反推权重（带统计检验）")
    pc.add_argument("--data", help="案例 JSON 文件")
    pc.add_argument("--engine", choices=["liuyao", "meihua", "qimen", "liuren", "ziwei"],
                    help="引擎（数据文件里有 engine 字段时可省）")
    pc.add_argument("--l2", type=float, default=1.0, help="L2 正则强度，默认 1.0")
    pc.add_argument("--boot", type=int, default=120, help="bootstrap 次数，默认 120")
    pc.add_argument("--emit", help="把拟合权重导出为 rules JSON")
    pc.add_argument("--make-demo", metavar="PATH", help="生成合成示例数据")
    pc.add_argument("--cases", type=int, default=60, help="示例数据条数")
    pc.add_argument("--lng", type=float, default=120.0)
    pc.add_argument("--tz", type=float, default=8.0)
    pc.add_argument("--preset", choices=list(PRESETS))
    pc.add_argument("--set", action="append", metavar="K=V")
    pc.add_argument("--rules-file")
    pc.add_argument("--html")
    pc.set_defaults(func=cmd_calibrate)

    p7 = sub.add_parser("rules", help="查看 / 导出规则参数")
    p7.add_argument("--preset", choices=list(PRESETS))
    p7.add_argument("--set", action="append", metavar="K=V")
    p7.add_argument("--rules-file", help="从 JSON 载入")
    p7.add_argument("--save-rules", help="另存为 JSON")
    p7.set_defaults(func=cmd_rules)

    return ap


def _finish(a, text: str):
    if getattr(a, "save_rules", None):
        r = build_rules(a)
        r.save(a.save_rules)
        print(f"规则已保存：{a.save_rules}\n")
    emit(text, a.html)


def cmd_bazi(a):
    _finish(a, do_bazi(a.date or datetime.now(), a.lng, a.tz, a.gender, a.day23,
                       build_rules(a)))


def cmd_liuyao(a):
    rules = build_rules(a)
    if a.coins:
        backs = [int(x) for x in a.coins.replace("，", ",").split(",") if x.strip()]
        if len(backs) != 6:
            sys.exit("--coins 需要 6 个 0-3 的数字（自初爻至上爻）")
        if a.date:
            text = do_liuyao_coins(backs, a.date, ask=a.ask, lng=a.lng, tz=a.tz, rules=rules)
        else:
            if not (a.day and a.month):
                sys.exit("不给 --date 时请给 --day（日干支）和 --month（月支）")
            text = do_liuyao_coins(backs, None, a.day, a.month, a.ask, rules=rules)
    elif a.hexagram:
        if a.moves is None:
            sys.exit("用 --hexagram 时须同时给 --moves（如 1,4；无动爻写 0）")
        moves = [] if a.moves.strip() == "0" else [int(x) for x in a.moves.split(",")]
        if a.date:
            text = do_liuyao_named(a.hexagram, moves, a.date, ask=a.ask,
                                   lng=a.lng, tz=a.tz, rules=rules)
        else:
            if not (a.day and a.month):
                sys.exit("不给 --date 时请给 --day 和 --month")
            text = do_liuyao_named(a.hexagram, moves, None, a.day, a.month, a.ask,
                                   rules=rules)
    else:
        sys.exit("请给 --coins 或 --hexagram + --moves")
    _finish(a, text)


def cmd_meihua(a):
    rules = build_rules(a)
    if a.nums:
        parts = [int(x) for x in a.nums.replace("，", ",").split(",")]
        if len(parts) < 2:
            sys.exit("--nums 需要两个数字，如 37,82")
        text = do_meihua_nums(parts[0], parts[1], month_zhi_of(a.date, a.lng, a.tz), rules)
    elif a.date:
        text = do_meihua_time(a.date, a.lng, a.tz, a.solar_nums, rules)
    else:
        sys.exit("请给 --nums 或 --date")
    _finish(a, text)


def cmd_qimen(a):
    _finish(a, do_qimen(a.date or datetime.now(), a.lng, a.tz, build_rules(a)))


def cmd_jieqi(a):
    emit(do_jieqi(a.year, a.tz), a.html)


def cmd_lunar(a):
    emit(do_lunar(a.date or datetime.now(), a.lng, a.tz), a.html)


def cmd_ziwei(a):
    _finish(a, do_ziwei(a.date or datetime.now(), a.lng, a.tz, a.gender, build_rules(a)))


def cmd_liuren(a):
    _finish(a, do_liuren(a.date or datetime.now(), a.lng, a.tz, build_rules(a)))


def cmd_slider(a):
    rules = build_rules(a)
    kw = {}
    if a.engine == "liuyao":
        if a.coins:
            backs = ([int(x) for x in a.coins.replace("，", ",").split(",") if x.strip()]
                     if isinstance(a.coins, str) else list(a.coins))
            if a.date:
                p = four_pillars(a.date, a.lng, a.tz)
                dg, mz = p.day, p.month[1]
            else:
                dg, mz = a.day, a.month
            kw["chart"] = liuyao_mod.cast_from_coins(backs, dg, mz, rules)
        elif a.hexagram:
            moves = [] if (a.moves or "0").strip() == "0" else \
                [int(x) for x in a.moves.split(",")]
            if a.date:
                p = four_pillars(a.date, a.lng, a.tz)
                dg, mz = p.day, p.month[1]
            else:
                dg, mz = a.day, a.month
            kw["chart"] = liuyao_mod.cast_from_hexagram(a.hexagram, moves, dg, mz, rules)
        else:
            sys.exit("六爻需要 --coins 或 --hexagram + --moves")
        kw["ask"] = a.ask
    elif a.engine == "meihua":
        if a.nums:
            parts = [int(x) for x in a.nums.replace("，", ",").split(",")]
            kw["chart"] = meihua_mod.cast_by_numbers(parts[0], parts[1], rules=rules)
        elif a.date:
            kw["chart"] = meihua_mod.cast_by_time(a.date, a.lng, a.tz,
                                                  use_lunar=not a.solar_nums, rules=rules)
        else:
            sys.exit("梅花需要 --nums 或 --date")
        kw["month_zhi"] = month_zhi_of(a.date, a.lng, a.tz)
    elif a.engine == "qimen":
        kw["chart"] = qimen_mod.build(a.date or datetime.now(), a.lng, a.tz, rules)
    elif a.engine == "liuren":
        kw["chart"] = liuren_mod.build(a.date or datetime.now(), a.lng, a.tz, rules)
    else:
        kw["chart"] = ziwei_mod.build(a.date or datetime.now(), a.lng, a.tz,
                                      a.gender, rules)

    content = do_slider(a.engine, rules, **kw)
    web_mod.write(a.out, content)
    print(f"已生成：{a.out}")
    print("用浏览器打开这个文件，拖动滑杆即可看到结论实时变色。")


def cmd_log(a):
    if not getattr(a, "logcmd", None):
        print("用法：log {add|list|resolve|verify|stats|export}")
        return
    print(do_log(a))


def cmd_calibrate(a):
    emit(do_calibrate(a), a.html)


def cmd_rules(a):
    r = Rules()
    if a.rules_file:
        r = Rules.load(a.rules_file)
    if a.preset:
        r.apply_preset(a.preset)
    if a.set:
        r.apply_overrides(a.set)
    if a.save_rules:
        r.save(a.save_rules)
        print(f"规则已保存：{a.save_rules}\n")
    print(do_rules(r))


# ---------------- 交互模式 ----------------
MENU = """
┌─────────────── 推演器 ───────────────┐
│  1 八字排盘       2 六爻·摇卦        │
│  3 六爻·卦名      4 梅花·报数        │
│  5 梅花·时间      6 奇门起局         │
│  7 节气表         8 农历换算         │
│  9 规则参数      10 大六壬起课       │
│ 11 生成调参页    12 紫微斗数         │
│ 13 案例录入      14 案例统计/校验    │
│  0 退出                              │
└──────────────────────────────────────┘"""


def _ask(prompt, default=""):
    v = input(prompt).strip()
    return v if v else default


def _ask_dt(prompt="时间（YYYY-MM-DD HH:MM，回车取当前）: "):
    s = _ask(prompt)
    return datetime.now() if not s else parse_dt(s)


def interactive():
    rules = Rules()
    print(MENU)
    while True:
        c = _ask("\n选择> ")
        if c in ("0", "q", "quit", "exit"):
            print("再见。")
            return
        try:
            if c == "1":
                dt = _ask_dt()
                lng = float(_ask("经度（默认 120）: ", "120"))
                g = _ask("性别 m/f（默认 m）: ", "m")
                print()
                print(do_bazi(dt, lng, 8.0, g, rules=rules))
            elif c == "2":
                print("六次摇卦，每次输入「背」的个数 0-3，逗号分隔（自初爻起）")
                backs = [int(x) for x in _ask("背数: ").replace("，", ",").split(",")]
                dt = _ask_dt()
                ask = _ask("所问何事（财/官/父/子/兄，可空）: ", "") or None
                print()
                print(do_liuyao_coins(backs, dt, ask=ask, rules=rules))
            elif c == "3":
                name = _ask("卦名（如 天火同人）: ")
                moves = _ask("动爻位置（如 1,4，无则 0）: ", "0")
                ml = [] if moves == "0" else [int(x) for x in moves.split(",")]
                dt = _ask_dt()
                ask = _ask("所问何事（可空）: ", "") or None
                print()
                print(do_liuyao_named(name, ml, dt, ask=ask, rules=rules))
            elif c == "4":
                a, b = _ask("两个数字（如 37,82）: ").replace("，", ",").split(",")[:2]
                dt = _ask_dt("以其时为断（回车取当前）: ")
                print()
                print(do_meihua_nums(int(a), int(b), month_zhi_of(dt), rules))
            elif c == "5":
                dt = _ask_dt()
                print()
                print(do_meihua_time(dt, rules=rules))
            elif c == "6":
                dt = _ask_dt()
                lng = float(_ask("经度（默认 120）: ", "120"))
                print()
                print(do_qimen(dt, lng, 8.0, rules))
            elif c == "7":
                y = int(_ask("年份: ", str(datetime.now().year)))
                print()
                print(do_jieqi(y))
            elif c == "8":
                dt = _ask_dt()
                print()
                print(do_lunar(dt))
            elif c == "10":
                dt = _ask_dt()
                lng = float(_ask("经度（默认 120）: ", "120"))
                print()
                print(do_liuren(dt, lng, 8.0, rules))
            elif c == "11":
                eng = _ask("引擎 liuyao/meihua/qimen/liuren/ziwei: ", "liuyao")
                dt = _ask_dt()
                out = _ask("输出路径: ", "output/slider.html")
                kw = {}
                if eng == "liuyao":
                    name = _ask("卦名: ")
                    mv = _ask("动爻（如 1,4；无则 0）: ", "0")
                    mk = [] if mv == "0" else [int(x) for x in mv.split(",")]
                    ask = _ask("用神（财/官/父/子/兄）: ")
                    kw = {"chart": liuyao_mod.cast_from_hexagram(name, mk, *_daymonth(dt), rules),
                          "ask": ask}
                elif eng == "meihua":
                    a, b = _ask("两个数字: ").replace("，", ",").split(",")[:2]
                    kw = {"chart": meihua_mod.cast_by_numbers(int(a), int(b), rules=rules),
                          "month_zhi": month_zhi_of(dt)}
                elif eng == "qimen":
                    kw = {"chart": qimen_mod.build(dt, 120.0, 8.0, rules)}
                elif eng == "liuren":
                    kw = {"chart": liuren_mod.build(dt, 120.0, 8.0, rules)}
                else:
                    g = _ask("性别 m/f（默认 m）: ", "m")
                    kw = {"chart": ziwei_mod.build(dt, 120.0, 8.0, g, rules)}
                web_mod.write(out, do_slider(eng, rules, **kw))
                print(f"已生成 {out}")
            elif c == "12":
                dt = _ask_dt()
                lng = float(_ask("经度（默认 120）: ", "120"))
                g = _ask("性别 m/f（默认 m）: ", "m")
                print()
                print(do_ziwei(dt, lng, 8.0, g, rules))
            elif c == "13":
                db = _ask("记录库路径（默认 output/cases.json）: ", "output/cases.json")
                eng = _ask("引擎 liuyao/meihua/qimen/liuren/ziwei: ", "liuyao")
                note = _ask("问的具体是什么事（备注）: ")
                print("  接着按该引擎的参数录入（回车用当前时间）")
                class _NS:
                    pass
                ns = _NS()
                ns.db, ns.engine, ns.note = db, eng, note
                ns.lng, ns.tz, ns.gender = 120.0, 8.0, "m"
                dt = _ask_dt()
                ns.date = dt
                ns.coins = ns.hexagram = ns.moves = ns.nums = None
                ns.day = ns.month = ns.ask = None
                ns.preset = ns.set = ns.rules_file = None
                if eng == "liuyao":
                    ns.ask = _ask("用神（财/官/父/子/兄）: ")
                    mode = _ask("按摇卦(c) 还是卦名(h)：", "c")
                    if mode == "c":
                        ns.coins = _ask("六次背数（如 1,2,3,1,0,2）: ")
                    else:
                        ns.hexagram = _ask("卦名: ")
                        ns.moves = _ask("动爻（如 1,4；无则 0）: ", "0")
                elif eng == "meihua":
                    ns.nums = _ask("两个数字（如 37,82）: ")
                print()
                print(do_log(ns))
            elif c == "14":
                db = _ask("记录库路径（默认 output/cases.json）: ", "output/cases.json")
                print()
                lo = caselog_mod.CaseLog(db)
                print(caselog_mod.render_stats(lo))
                ok, errs = lo.verify()
                print()
                print("哈希链：" + ("完整" if ok else "校验失败 — " + "；".join(errs)))
            elif c == "9":
                print("  1 查看全部参数   2 套用预设   3 改单个参数   4 存为 JSON   5 重置")
                sub = _ask("  > ")
                if sub == "1":
                    print()
                    print(do_rules(rules))
                elif sub == "2":
                    print(f"  可选：{', '.join(PRESETS)}")
                    n = _ask("  预设名: ")
                    rules.apply_preset(n)
                    print(f"  已套用 {n}")
                elif sub == "3":
                    k = _ask("  参数路径（如 liuyao.month.po）: ")
                    v = _ask("  值: ")
                    rules.apply_overrides([f"{k}={v}"])
                    print(f"  {k} = {v}")
                elif sub == "4":
                    path = _ask("  保存到: ", "rules.json")
                    rules.save(path)
                    print(f"  已保存 {path}")
                elif sub == "5":
                    rules = Rules()
                    print("  已重置为默认")
            else:
                print("没有这个选项。")
        except Exception as e:
            print(f"出错：{e}")


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not getattr(a, "cmd", None):
        interactive()
        return
    a.func(a)


if __name__ == "__main__":
    main()

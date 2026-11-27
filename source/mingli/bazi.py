"""子平八字引擎。

排四柱 -> 定十神 -> 藏干 -> 五行力量计分 -> 日主旺衰 -> 取用提示 -> 排大运。
说明：旺衰采用「加权计分」的简化模型（月令权重最大），只为给出可复核的数量结果，
     不等于传统命书「得令得地得生得助」的定性判断，两者常需并看。
"""
from datetime import datetime

from .jiazi import (GAN, ZHI, GAN_WUXING, ZHI_WUXING, CANG_GAN, WUXING_SHENG, WUXING_KE,
                    SHENG_WO, shishen, yinyang, changsheng, nayin, jiazi, jiazi_index,
                    zhi_relations, season_state, wuxing_relation)
from .calendar import four_pillars, solar_term_events, jd_from_datetime, ymd_from_jd, JIE_TO_ZHI

WUXING_LIST = "木火土金水"


def kongwang(day_gz: str) -> tuple[str, str]:
    idx = jiazi_index(day_gz)
    head = (idx // 10) * 10
    return ZHI[(head % 12 + 10) % 12], ZHI[(head % 12 + 11) % 12]


class BaZi:
    def __init__(self, pillars, gender: str = "m", rules=None):
        from .rules import Rules
        self.rules = rules or Rules()
        self.p = pillars
        self.gender = gender
        self.day_gan = pillars.day[0]
        self.day_wx = GAN_WUXING[self.day_gan]
        self.kong = kongwang(pillars.day)
        self.scores = self._score()

    # ---------- 十神 ----------
    def shishen_of(self, gan: str) -> str:
        return shishen(self.day_gan, gan)

    def pillar_detail(self):
        rows = []
        labels = ["年柱", "月柱", "日柱", "时柱"]
        for lab, gz in zip(labels, self.p.as_list()):
            g, z = gz[0], gz[1]
            ss = "日主" if lab == "日柱" else self.shishen_of(g)
            cang = [(cg, w, self.shishen_of(cg)) for cg, w in CANG_GAN[z]]
            rows.append({
                "label": lab, "gz": gz, "gan": g, "zhi": z,
                "gan_wx": GAN_WUXING[g], "zhi_wx": ZHI_WUXING[z],
                "gan_ss": ss, "cang": cang,
                "nayin": nayin(gz), "changsheng": changsheng(self.day_gan, z),
                "is_kong": z in self.kong,
            })
        return rows

    # ---------- 五行计分 ----------
    def _score(self):
        r = self.rules
        w_month = r.get("bazi.weight.month_zhi", 3.0)
        w_other = r.get("bazi.weight.other_zhi", 1.5)
        w_gan = r.get("bazi.weight.gan", 1.0)
        w_self = r.get("bazi.weight.self", 1.0)
        cang_w = [r.get("bazi.cang.benqi", 0.6), r.get("bazi.cang.zhongqi", 0.3),
                  r.get("bazi.cang.yuqi", 0.1)]
        s = {w: 0.0 for w in WUXING_LIST}
        # 天干：年月时各计 w_gan；日干是参照系，不计
        for i, gz in enumerate(self.p.as_list()):
            if i == 2:
                continue
            s[GAN_WUXING[gz[0]]] += w_gan
        # 地支：月支 w_month，其余 w_other；藏干按本气/中气/余气分配
        for i, gz in enumerate(self.p.as_list()):
            weight = w_month if i == 1 else w_other
            cand = CANG_GAN[gz[1]]
            # 按实际藏干个数归一：1个=1.0，2个=0.7/0.3，3个=0.6/0.3/0.1
            if len(cand) == 1:
                ws = [1.0]
            elif len(cand) == 2:
                ws = [cang_w[0] + cang_w[2], cang_w[1]]
            else:
                ws = cang_w
            for k, (cg, _) in enumerate(cand):
                s[GAN_WUXING[cg]] += weight * ws[k]
        # 日干自身计入同类
        s[self.day_wx] += w_self
        return s

    def strength(self):
        total = sum(self.scores.values())
        same = self.scores[self.day_wx] + self.scores[SHENG_WO[self.day_wx]]
        ratio = same / total if total else 0
        hi = self.rules.get("bazi.strength.strong", 0.55)
        lo = self.rules.get("bazi.strength.weak", 0.45)
        if ratio >= hi:
            level = "身强"
        elif ratio >= lo:
            level = "中和"
        else:
            level = "身弱"
        return {"same": same, "total": total, "ratio": ratio, "level": level}

    def yongshen_hint(self):
        st = self.strength()
        wx = self.day_wx
        ke_me = KE_WO_SELF[wx]        # 克我的五行（官杀）
        sheng_me = SHENG_WO[wx]       # 生我的五行（印）
        i_sheng = WUXING_SHENG[wx]    # 我生（食伤）
        i_ke = WUXING_KE[wx]          # 我克（财）
        if st["level"] == "身强":
            return ("身强，喜克泄耗",
                    [f"官杀（{ke_me}克{wx}）", f"食伤（{wx}生{i_sheng}）", f"财（{wx}克{i_ke}）"],
                    "不宜再补印比，宜用官杀制身、食伤泄秀、财星耗身以求平衡")
        if st["level"] == "身弱":
            return ("身弱，喜生扶",
                    [f"印（{sheng_me}生{wx}）", f"比劫（同为{wx}）"],
                    "不宜再受克泄，宜用印星生身、比劫帮身")
        return ("中和，随大运流年取用", [], "格局平稳，重点看岁运引动")

    # ---------- 大运 ----------
    def dayun(self, count: int = 8):
        p = self.p
        birth = jd_from_datetime(datetime.strptime(p.meta["input"], "%Y-%m-%d %H:%M:%S"))
        tz = p.meta["tz"]
        jd_birth = birth - tz / 24.0      # UT
        events = solar_term_events(jd_birth - 400, jd_birth + 400)
        jie = [e for e in events if e[2] in JIE_TO_ZHI]

        yang_year = yinyang(p.year[0]) == "阳"
        forward = (yang_year and self.gender == "m") or ((not yang_year) and self.gender == "f")

        if forward:
            nxt = [e for e in jie if e[0] > jd_birth]
            target = nxt[0]
            days = target[0] - jd_birth
        else:
            prev = [e for e in jie if e[0] <= jd_birth]
            target = prev[-1]
            days = jd_birth - target[0]

        years_f = days / 3.0
        start_age = round(years_f, 2)
        start_year = int(ymd_from_jd(jd_birth + tz / 24)[0]) + int(start_age)

        base = jiazi_index(p.month)
        out = []
        for i in range(1, count + 1):
            idx = base + i if forward else base - i
            gz = jiazi(idx)
            age0 = start_age + 10 * (i - 1)
            out.append({
                "gz": gz,
                "start_age": round(age0, 1),
                "end_age": round(age0 + 10, 1),
                "start_year": int(start_year + 10 * (i - 1)),
                "gan_ss": self.shishen_of(gz[0]),
                "zhi_wx": ZHI_WUXING[gz[1]],
            })
        return {"forward": forward, "start_age": start_age,
                "start_year": start_year, "target_jie": target[1], "list": out}


KE_WO_SELF = {v: k for k, v in WUXING_KE.items()}
WUXING_KE_INV = KE_WO_SELF


def build(dt: datetime, longitude: float = 120.0, tz: float = 8.0,
          gender: str = "m", day_boundary_23: bool = False, rules=None) -> BaZi:
    p = four_pillars(dt, longitude, tz, day_boundary_23)
    return BaZi(p, gender, rules)


def render(b: BaZi, show_dayun: bool = True) -> str:
    from .utils import pad

    out = []
    meta = b.p.meta
    eot = 0.0 if abs(meta["eot_min"]) < 0.05 else meta["eot_min"]
    out.append(f"输入时间：{meta['input']}　时区 UTC{meta['tz']:+g}　经度 {meta['longitude']}°E")
    out.append(f"真太阳时：{meta['true_solar_time']}　均时差 {eot:+.1f} 分钟")
    out.append(f"节气：月柱以「{meta['month_jie']}」为界　年柱以立春为界")
    for w in meta["warnings"]:
        out.append(f"⚠ {w}")
    out.append("")

    rows = b.pillar_detail()
    W = 22

    def line(name, cells):
        return pad(name, 6) + "".join(pad(c, W) for c in cells)

    out.append(line("", [r["label"] for r in rows]))
    out.append(line("天干", [f"{r['gan']}({r['gan_wx']}){'·日主' if r['label'] == '日柱' else ''}"
                            for r in rows]))
    out.append(line("十神", [r["gan_ss"] for r in rows]))
    out.append(line("地支", [f"{r['zhi']}({r['zhi_wx']})" for r in rows]))
    out.append(line("藏干", [",".join(f"{cg}{ss}" for cg, w, ss in r["cang"]) for r in rows]))
    out.append(line("纳音", [r["nayin"] for r in rows]))
    out.append(line("长生", [r["changsheng"] for r in rows]))
    out.append(f"旬空：{b.kong[0]}{b.kong[1]}　"
               f"命中：{', '.join(r['label'] for r in rows if r['is_kong']) or '无'}")
    out.append("─" * 62)

    st = b.strength()
    out.append("五行力量（加权计分，月令 ×3）：")
    mx = max(b.scores.values()) or 1
    for w in WUXING_LIST:
        bar = "█" * int(round(b.scores[w] / mx * 24))
        out.append(f"  {w}　{b.scores[w]:5.2f}　{bar}")
    out.append(f"日主：{b.day_gan}{b.day_wx}（{yinyang(b.day_gan)}）　"
               f"同类 {st['same']:.2f} / 总 {st['total']:.2f} = {st['ratio']:.0%}　→ {st['level']}")
    out.append(f"月令：{b.day_wx}在{b.p.month[1]}月为「{season_state(b.day_wx, b.p.month[1])}」")
    lvl, xi, note = b.yongshen_hint()
    out.append(f"取用：{lvl}" + (f"　喜 {'、'.join(xi)}" if xi else ""))
    out.append(f"　{note}")
    out.append("─" * 62)

    zhis = [r["zhi"] for r in rows]
    rels = []
    for i in range(4):
        for j in range(i + 1, 4):
            for r in zhi_relations(zhis[i], zhis[j]):
                rels.append(f"{rows[i]['label']}{zhis[i]}–{rows[j]['label']}{zhis[j]} {r}")
    out.append("地支关系：" + ("　".join(rels) if rels else "四柱地支无刑冲合害"))

    if show_dayun:
        d = b.dayun()
        out.append("─" * 62)
        out.append(f"大运：{'顺行' if d['forward'] else '逆行'}　起运约 {d['start_age']:.1f} 岁"
                   f"（{d['start_year']} 年，起运节「{d['target_jie']}」）")
        out.append("规则：阳男阴女顺行、阴男阳女逆行；出生日到节气之日，三日折一年")
        for u in d["list"]:
            out.append(f"  {u['start_age']:>5.1f}–{u['end_age']:<4.1f}岁　{u['gz']}　"
                       f"{u['start_year']} 年起　{u['gan_ss']}·{u['zhi_wx']}")
    return "\n".join(out)

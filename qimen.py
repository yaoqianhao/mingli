"""奇门遁甲（时家·转盘）起局引擎。

口径说明（重要）
----------------
本实现采用「时家转盘 + 拆补定局」：
  · 阴阳遁：冬至→芒种用阳遁，夏至→大雪用阴遁
  · 定元：找不晚于当日的最近一个甲日或己日（符头），
          符头地支子午卯酉=上元、寅申巳亥=中元、辰戌丑未=下元
  · 节气：按实际交节时刻切换（拆补法，不置闰）
  · 值符：时柱旬首所遁六仪在地盘之宫的地盘星
  · 值使：该宫的地盘门
  · 天盘：值符星移到「时干在地盘之宫」，其余星按宫序跟随
  · 人盘：值使门从原宫起，按阳顺阴逆数时支落宫，其余门跟随
  · 神盘：值符神落值符星宫，阳顺阴逆排八神

排列序（star/gate/god 三项可在 rules 里切换）：
  num   = 1→2→3→4→5→6→7→8→9（洛书数序）
  bagua = 1→8→3→4→9→2→7→6（后天八卦顺时针，中五不列）

不同流派（飞盘、置闰、阴盘）结果会不同，此处不声称唯一正确。
"""
from datetime import datetime

from .calendar import four_pillars, solar_term_events, jd_from_datetime
from .jiazi import GAN, ZHI, jiazi_index, ke

# ---------- 常量 ----------
PALACE_WUXING = {1: "水", 2: "土", 3: "木", 4: "木", 5: "土",
                 6: "金", 7: "金", 8: "土", 9: "火"}
PALACE_GUA = {1: "坎", 2: "坤", 3: "震", 4: "巽", 5: "中",
              6: "乾", 7: "兑", 8: "艮", 9: "离"}
PALACE_DIR = {1: "北", 2: "西南", 3: "东", 4: "东南", 5: "中",
              6: "西北", 7: "西", 8: "东北", 9: "南"}

STAR_OF_PALACE = {1: "天蓬", 2: "天芮", 3: "天冲", 4: "天辅", 5: "天禽",
                  6: "天心", 7: "天柱", 8: "天任", 9: "天英"}
STAR_WUXING = {"天蓬": "水", "天芮": "土", "天冲": "木", "天辅": "木", "天禽": "土",
               "天心": "金", "天柱": "金", "天任": "土", "天英": "火"}
GATE_OF_PALACE = {1: "休门", 2: "死门", 3: "伤门", 4: "杜门",
                  6: "开门", 7: "惊门", 8: "生门", 9: "景门"}
GATE_WUXING = {"休门": "水", "死门": "土", "伤门": "木", "杜门": "木",
               "开门": "金", "惊门": "金", "生门": "土", "景门": "火"}
GATE_ORDER = ["休门", "生门", "伤门", "杜门", "景门", "死门", "惊门", "开门"]
GOD_ORDER = ["值符", "螣蛇", "太阴", "六合", "白虎", "玄武", "九地", "九天"]
GOD_MEANING = {"值符": "诸神之首，百事可托", "螣蛇": "虚惊怪异、缠绕",
               "太阴": "阴私庇护、暗中相助", "六合": "和合、婚姻、交易",
               "白虎": "刚猛、伤损、道路", "玄武": "暗昧、盗失、欺骗",
               "九地": "厚重、守成、宜静", "九天": "高远、扬名、宜动"}

XUNSHOU_YI = {"甲子": "戊", "甲戌": "己", "甲申": "庚",
              "甲午": "辛", "甲辰": "壬", "甲寅": "癸"}

SEQ = "戊己庚辛壬癸丁丙乙"      # 地盘排布序列：六仪顺、三奇逆

JU_TABLE = {
    "冬至": (1, 7, 4), "小寒": (2, 8, 5), "大寒": (3, 9, 6),
    "立春": (8, 5, 2), "雨水": (9, 6, 3), "惊蛰": (1, 7, 4),
    "春分": (3, 9, 6), "清明": (4, 1, 7), "谷雨": (5, 2, 8),
    "立夏": (4, 1, 7), "小满": (5, 2, 8), "芒种": (6, 3, 9),
    "夏至": (9, 3, 6), "小暑": (8, 2, 5), "大暑": (7, 1, 4),
    "立秋": (2, 5, 8), "处暑": (1, 4, 7), "白露": (9, 3, 6),
    "秋分": (7, 1, 4), "寒露": (6, 9, 3), "霜降": (5, 8, 2),
    "立冬": (6, 9, 3), "小雪": (5, 8, 2), "大雪": (4, 7, 1),
}
YANG_TERMS = ["冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
              "春分", "清明", "谷雨", "立夏", "小满", "芒种"]

YUAN_NAME = ["上元", "中元", "下元"]
YUAN_OF_ZHI = {"子": 0, "午": 0, "卯": 0, "酉": 0,
               "寅": 1, "申": 1, "巳": 1, "亥": 1,
               "辰": 2, "戌": 2, "丑": 2, "未": 2}

# 中五不列宫，天禽及中宫之干寄坤二，故排列序一律 8 位
ORDER_NUM = [1, 2, 3, 4, 6, 7, 8, 9]
ORDER_BAGUA = [1, 8, 3, 4, 9, 2, 7, 6]
ORDER_MAP = {"num": ORDER_NUM, "bagua": ORDER_BAGUA}


def _order(name: str):
    if name not in ORDER_MAP:
        raise ValueError(f"未知排列序：{name}（num / bagua）")
    return ORDER_MAP[name]


def current_term(dt: datetime, tz: float = 8.0):
    """返回所在节气名、交节时刻（本地时）、起局瞬间的 UT 儒略日。"""
    jd_ut = jd_from_datetime(dt) - tz / 24.0
    events = solar_term_events(jd_ut - 400, jd_ut + 5)
    past = [e for e in events if e[0] <= jd_ut]
    if not past:
        raise RuntimeError("节气窗口不足")
    jd, name, deg = past[-1]
    return name, jd + tz / 24.0, jd_ut


def futou_of(day_gz: str):
    """找不晚于当日的最近符头（甲日或己日），返回 (符头干支, 距今天数, 元序号)。"""
    idx = jiazi_index(day_gz)
    for back in range(0, 10):
        j = (idx - back) % 60
        if GAN[j % 10] in ("甲", "己"):
            gz = GAN[j % 10] + ZHI[j % 12]
            return gz, back, YUAN_OF_ZHI[ZHI[j % 12]]
    raise RuntimeError("符头计算失败")


class QiMenChart:
    def __init__(self, dt: datetime, longitude: float = 120.0, tz: float = 8.0,
                 rules=None):
        from .rules import Rules
        self.rules = rules or Rules()
        self.dt = dt
        self.pillars = four_pillars(dt, longitude, tz)
        p = self.pillars

        term, term_jd, jd_ut = current_term(dt, tz)
        self.term = term
        self.term_time = term_jd
        self.dun = "阳" if term in YANG_TERMS else "阴"

        self.futou, self.futou_back, self.yuan = futou_of(p.day)
        self.yuan_name = YUAN_NAME[self.yuan]
        self.ju = JU_TABLE[term][self.yuan]

        self.earth = self._earth_plate()

        hidx = jiazi_index(p.hour)
        head = (hidx // 10) * 10
        self.xunshou = GAN[head % 10] + ZHI[head % 12]
        self.xun_yi = XUNSHOU_YI[self.xunshou]
        self.fu_palace = self.palace_of_gan(self.xun_yi)
        self.zhifu_star = STAR_OF_PALACE[self.fu_palace]
        base = self._zhong_to(self.fu_palace)
        self.zhishi_gate = GATE_OF_PALACE[base]

        hour_gan = p.hour[0]
        self.hour_gan_used = self.xun_yi if hour_gan == "甲" else hour_gan
        self.hour_palace = self.palace_of_gan(self.hour_gan_used)

        self._gate_landing = None
        self.sky_star, self.sky_gan = self._sky_plate()
        self.gates = self._gate_plate()
        self.gods = self._god_plate()

    # ---- 地盘 ----
    def _earth_plate(self) -> dict:
        plate = {}
        step = 1 if self.dun == "阳" else -1
        for i, gan in enumerate(SEQ):
            p = (self.ju - 1 + step * i) % 9 + 1
            plate[p] = gan
        return plate

    def _zhong_to(self, palace: int) -> int:
        if palace != 5:
            return palace
        host = self.rules.get("qimen.zhong_gong", "kun")
        return {"kun": 2, "gen": 8}.get(str(host).lower(), 2)

    def palace_of_gan(self, gan: str) -> int:
        for p, g in self.earth.items():
            if g == gan:
                return p
        raise ValueError(f"地盘上找不到 {gan}")

    # ---- 天盘 ----
    def _sky_plate(self):
        order = _order(self.rules.get("qimen.order.star", "num"))
        g0 = self._zhong_to(self.fu_palace)
        g1 = self._zhong_to(self.hour_palace)
        shift = order.index(g1) - order.index(g0)
        star_at, gan_at = {}, {}
        for sp in [1, 2, 3, 4, 6, 7, 8, 9]:
            src = sp                      # 天禽固定随天芮，故从天芮位置上平移
            new_p = order[(order.index(src) + shift) % len(order)]
            star_at.setdefault(new_p, []).append(STAR_OF_PALACE[sp])
            gan_at.setdefault(new_p, []).append(self.earth[sp])
        # 天禽随天芮，并把中宫之干一并寄去
        rui_p = order[(order.index(2) + shift) % len(order)]
        star_at[rui_p].insert(1, STAR_OF_PALACE[5])
        gan_at[rui_p].insert(1, self.earth[5])
        return star_at, gan_at

    # ---- 八门 ----
    def _gate_plate(self):
        order = _order(self.rules.get("qimen.order.gate", "bagua"))
        base = self._zhong_to(self.fu_palace)
        n = ZHI.index(self.pillars.hour[1]) + 1
        step = 1 if self.dun == "阳" else -1
        i0 = order.index(base)
        i1 = (i0 + step * (n - 1)) % len(order)
        self._gate_landing = order[i1]

        gates = {}
        gi = GATE_ORDER.index(self.zhishi_gate)
        for k in range(8):
            gates[order[(i1 + k) % len(order)]] = GATE_ORDER[(gi + k) % 8]
        return gates

    # ---- 八神 ----
    def _god_plate(self):
        order = _order(self.rules.get("qimen.order.god", "bagua"))
        start = order.index(self._zhong_to(self.hour_palace))
        step = 1 if self.dun == "阳" else -1
        return {order[(start + step * k) % len(order)]: god
                for k, god in enumerate(GOD_ORDER)}

    # ---- 查询 ----
    def palace_info(self, p: int) -> dict:
        pw = PALACE_WUXING[p]
        gate = self.gates.get(p)
        stars = self.sky_star.get(p) or []
        gans = self.sky_gan.get(p) or []
        star = stars[0] if stars else None
        earth_gan = self.earth.get(p)
        # 中宫之干寄坤二
        if p == self._zhong_to(5) and self._zhong_to(5) != 5:
            extra = self.earth.get(5)
            if extra and extra != earth_gan:
                earth_gan = f"{earth_gan}({extra})" if earth_gan else extra
        return {
            "palace": p, "gua": PALACE_GUA[p], "dir": PALACE_DIR[p], "wuxing": pw,
            "god": self.gods.get(p), "star": star, "stars": stars,
            "star_wx": STAR_WUXING.get(star) if star else None,
            "gate": gate, "gate_wx": GATE_WUXING.get(gate) if gate else None,
            "sky_gan": "/".join(gans) if gans else None,
            "earth_gan": earth_gan,
        }

    def factors(self) -> list[dict]:
        """把八宫吉凶要素汇总成可加权的线性因子（供滑块界面）。"""
        sc = self.rules.get("qimen.score")
        labels = {"ji_men": "吉门（开休生）", "xiong_men": "凶门（死惊伤）",
                  "men_po": "门迫（门克宫）", "ji_xing": "吉星（心任辅禽）",
                  "xiong_xing": "凶星（蓬芮柱英）", "san_qi": "三奇临宫"}
        cnt = {k: 0 for k in labels}
        for pi in [4, 9, 2, 3, 7, 8, 1, 6]:
            info = self.palace_info(pi)
            fl = self.flags(pi)
            if info["gate"] in ("开门", "休门", "生门"):
                cnt["ji_men"] += 1
            if info["gate"] in ("死门", "惊门", "伤门"):
                cnt["xiong_men"] += 1
            if "门迫" in fl:
                cnt["men_po"] += 1
            if info["star"] in ("天心", "天任", "天辅", "天禽"):
                cnt["ji_xing"] += 1
            if info["star"] in ("天蓬", "天芮", "天柱", "天英"):
                cnt["xiong_xing"] += 1
            if "三奇" in fl:
                cnt["san_qi"] += 1
        return [{"key": f"qimen.score.{k}", "label": labels[k],
                 "mul": v, "w": sc[k]} for k, v in cnt.items() if v]

    def flags(self, p: int) -> list[str]:
        info = self.palace_info(p)
        out = []
        g, gw = info["gate"], info["gate_wx"]
        if g and gw and ke(gw, info["wuxing"]):
            out.append("门迫")
        gans = (info["sky_gan"] or "") + (info["earth_gan"] or "")
        if any(ch in "乙丙丁" for ch in gans if ch in SEQ):
            out.append("三奇")
        if info["star"] == STAR_OF_PALACE.get(p):
            out.append("星伏吟")
        if info["gate"] == GATE_OF_PALACE.get(p):
            out.append("门伏吟")
        return out


def _fmt_jd(jd_local: float) -> str:
    from .calendar import ymd_from_jd
    y, m, d, h, mi, _ = ymd_from_jd(jd_local)
    return f"{y:04d}-{m:02d}-{d:02d} {h:02d}:{mi:02d}"


def render(c: QiMenChart, with_score: bool = True) -> str:
    from .utils import pad
    from .rules import bar, grade

    p = c.pillars
    out = []
    out.append(f"起局时间：{c.dt:%Y-%m-%d %H:%M}　四柱 {p.year} {p.month} {p.day} {p.hour}")
    out.append(f"节气：{c.term}　→　{c.dun}遁 {c.ju} 局")
    out.append(f"定局依据：符头 {c.futou}（距当日 {c.futou_back} 日）· {c.yuan_name}"
               f"　交节于 {_fmt_jd(c.term_time)}")
    out.append(f"旬首：{c.xunshou}（遁{c.xun_yi}）　值符：{c.zhifu_star}（{c.fu_palace}宫）"
               f"　值使：{c.zhishi_gate}（落{c._gate_landing}宫）")
    out.append(f"时干：{c.hour_gan_used}（{c.hour_palace}宫）　排列序："
               f"星={c.rules.get('qimen.order.star')} 门={c.rules.get('qimen.order.gate')} "
               f"神={c.rules.get('qimen.order.god')}")
    out.append("")

    layout = [[4, 9, 2], [3, 5, 7], [8, 1, 6]]
    W = 24
    top = "┌" + "─" * W + "┬" + "─" * W + "┬" + "─" * W + "┐"
    mid = "├" + "─" * W + "┼" + "─" * W + "┼" + "─" * W + "┤"
    bot = "└" + "─" * W + "┴" + "─" * W + "┴" + "─" * W + "┘"
    out.append(top)
    for ri, row in enumerate(layout):
        cells = []
        for pi in row:
            info = c.palace_info(pi)
            f = c.flags(pi)
            head = f"{info['gua']}{pi}宫·{info['dir']}·{info['wuxing']}"
            if pi == 5:
                lines = [head, "中五（寄坤二）", f"地 {info['earth_gan'] or '—'}", "", "", ""]
            else:
                lines = [
                    head,
                    f"{info['god'] or '—'}　{'·'.join(info['stars']) or '—'}",
                    f"{info['gate'] or '—'}",
                    f"天{info['sky_gan'] or '—'}　地{info['earth_gan'] or '—'}",
                    "·".join(f),
                    "",
                ]
            cells.append([pad(x, W) for x in lines])
        for li in range(6):
            out.append("│" + "│".join(cc[li] for cc in cells) + "│")
        out.append(mid if ri < 2 else bot)

    if not with_score:
        return "\n".join(out)
    out.append("")
    fac = c.factors()
    total = sum(f["mul"] * f["w"] for f in fac)
    out.append(f"宫位评分（按 rules 加权，{len(fac)} 项有值）：")
    for f in fac:
        v = f["mul"] * f["w"]
        out.append(f"  {f['label']} ×{f['mul']}　{v:+.1f} {bar(v, 3.0, 8)}")
    th = c.rules.get("qimen.thresholds")
    out.append(f"  合计 {total:+.1f}　→　{grade(total, th)}")
    out.append("")
    out.append("注：奇门断事以「用神落宫」为主，上列评分只是把各宫吉凶要素机械相加，")
    out.append("　　单看总分不能定事。真正断卦须先定所问之事的用神宫。")
    return "\n".join(out)


def build(dt: datetime, longitude: float = 120.0, tz: float = 8.0, rules=None) -> QiMenChart:
    return QiMenChart(dt, longitude, tz, rules)

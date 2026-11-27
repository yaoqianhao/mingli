"""六爻（纳甲筮法）引擎。

规则来源：京房纳甲 → 《火珠林》 → 《卜筮正宗》。
实现范围：起卦、定卦宫、纳甲装支、安世应、配六亲、配六神、藏伏、旬空、
         动爻化变、以用神为中心的旺衰生克初判。
不做的事：不编造吉凶断语，只输出可复核的盘面与机械推理结果。
"""
from .jiazi import (GAN, ZHI, GUA_BITS, BITS_GUA, GUA_WUXING, LIUSHI_SI_GUA,
                    ZHI_WUXING, gan_index, zhi_index,
                    wuxing_relation, sheng, ke, yinyang)

PALACES = ["乾", "坎", "艮", "震", "巽", "离", "坤", "兑"]
SHI_POS = [6, 1, 2, 3, 4, 5, 4, 3]      # 八宫第 1..8 卦的世爻位置

# 纳甲天干：内卦 / 外卦
NAJIA_GAN = {"乾": ("甲", "壬"), "坤": ("乙", "癸"), "震": ("庚", "庚"),
             "巽": ("辛", "辛"), "坎": ("戊", "戊"), "离": ("己", "己"),
             "艮": ("丙", "丙"), "兑": ("丁", "丁")}
# 纳甲地支：自初爻起 6 位
NAJIA_ZHI = {
    "乾": ["子", "寅", "辰", "午", "申", "戌"],
    "坎": ["寅", "辰", "午", "申", "戌", "子"],
    "艮": ["辰", "午", "申", "戌", "子", "寅"],
    "震": ["子", "寅", "辰", "午", "申", "戌"],
    "巽": ["丑", "亥", "酉", "未", "巳", "卯"],
    "离": ["卯", "丑", "亥", "酉", "未", "巳"],
    "坤": ["未", "巳", "卯", "丑", "亥", "酉"],
    "兑": ["巳", "卯", "丑", "亥", "酉", "未"],
}
LIUSHEN = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]
LIUSHEN_START = {"甲": 0, "乙": 0, "丙": 1, "丁": 1, "戊": 2,
                 "己": 3, "庚": 4, "辛": 4, "壬": 5, "癸": 5}


def bits_to_gua(bits: list[int]) -> str:
    val = bits[0] | (bits[1] << 1) | (bits[2] << 2)
    return BITS_GUA[val]


def hexagram_name(bits: list[int]) -> str:
    lower = bits_to_gua(bits[0:3])
    upper = bits_to_gua(bits[3:6])
    return LIUSHI_SI_GUA[upper][lower]


def palace_of(bits: list[int]):
    """返回 (宫, 宫内序号 1..8, 卦名)。由八宫生成表反查。"""
    for palace in PALACES:
        for i, gen in enumerate(palace_hexagrams(palace), start=1):
            if gen == list(bits):
                return palace, i, hexagram_name(bits)
    raise ValueError("卦象非法")


def palace_hexagrams(palace: str) -> list[list[int]]:
    """京房八宫生成法：本宫卦 → 依次变初至五爻 → 游魂 → 归魂。
    返回六个长度为 6 的列表，每项为 [初,二,三,四,五,上] 的阴阳（1阳0阴）。"""
    b = GUA_BITS[palace]
    tri = [(b >> i) & 1 for i in range(3)]
    base = tri + tri
    out = [base[:]]
    cur = base[:]
    for i in range(5):
        cur = cur[:]
        cur[i] ^= 1
        out.append(cur)
    youhun = out[5][:]
    youhun[3] ^= 1
    out.append(youhun)
    guihun = youhun[:]
    guihun[0], guihun[1], guihun[2] = base[0], base[1], base[2]
    out.append(guihun)
    return out


class Line:
    def __init__(self, pos, yang, moving, gan, zhi, liuqin, liushen, shiying, kong):
        self.pos = pos
        self.yang = yang
        self.moving = moving
        self.gan = gan
        self.zhi = zhi
        self.liuqin = liuqin
        self.liushen = liushen
        self.shiying = shiying
        self.kong = kong

    @property
    def wuxing(self):
        return ZHI_WUXING[self.zhi]

    @property
    def label(self) -> str:
        """爻题：初九/九二/六三/上六……"""
        num = "九" if self.yang else "六"
        if self.pos == 1:
            return "初" + num
        if self.pos == 6:
            return "上" + num
        return num + "二三四五"[self.pos - 2]

    def __repr__(self):
        return (f"{self.label} {self.liuqin} {self.gan}{self.zhi}({self.wuxing}) "
                f"{self.liushen}{' 空' if self.kong else ''}")


def liuqin_of(palace_wx: str, line_wx: str) -> str:
    rel = wuxing_relation(palace_wx, line_wx)  # 从宫（我）的视角
    return {"比和": "兄弟", "我生": "子孙", "我克": "妻财",
            "生我": "父母", "克我": "官鬼"}[rel]


def xunkong(day_gz: str) -> tuple[str, str]:
    """旬空：日干支所在旬的两个空亡地支。"""
    idx = None
    for i in range(60):
        if GAN[i % 10] == day_gz[0] and ZHI[i % 12] == day_gz[1]:
            idx = i
            break
    if idx is None:
        raise ValueError("非法日干支")
    head = (idx // 10) * 10
    return ZHI[(head % 12 + 10) % 12], ZHI[(head % 12 + 11) % 12]


class LiuYaoChart:
    def __init__(self, lines: list[list[int]], moving: list[bool], day_gz: str,
                 month_zhi: str, rules=None):
        from .rules import Rules
        self.rules = rules or Rules()
        self.raw = lines
        self.moving = moving
        self.day_gz = day_gz
        self.month_zhi = month_zhi

        self.palace, self.palace_seq, self.name = palace_of(lines)
        self.palace_wx = GUA_WUXING[self.palace]
        self.shi_pos = SHI_POS[self.palace_seq - 1]
        self.ying_pos = self.shi_pos + 3 if self.shi_pos <= 3 else self.shi_pos - 3
        self.kong1, self.kong2 = xunkong(day_gz)
        self.ls_start = LIUSHEN_START[day_gz[0]]

        lower, upper = bits_to_gua(lines[0:3]), bits_to_gua(lines[3:6])
        self.inner, self.outer = lower, upper
        self.rows: list[Line] = []
        for i in range(6):
            gua = lower if i < 3 else upper
            gan = NAJIA_GAN[gua][0 if i < 3 else 1]
            zhi = NAJIA_ZHI[gua][i]
            self.rows.append(Line(
                pos=i + 1, yang=lines[i], moving=moving[i],
                gan=gan, zhi=zhi,
                liuqin=liuqin_of(self.palace_wx, ZHI_WUXING[zhi]),
                liushen=LIUSHEN[(self.ls_start + i) % 6],
                shiying="世" if i + 1 == self.shi_pos else ("应" if i + 1 == self.ying_pos else None),
                kong=zhi in (self.kong1, self.kong2),
            ))

        # 变卦
        self.changed_bits = [b ^ 1 if m else b for b, m in zip(lines, moving)]
        self.changed_name = hexagram_name(self.changed_bits)
        self.has_change = any(moving)

    # ---- 变爻 ----
    def changed_line(self, pos: int):
        i = pos - 1
        if not self.moving[i]:
            return None
        new_bit = self.changed_bits[i]
        # 变爻仍按本卦外/内卦位置取纳支？主流：变爻按变卦对应经卦纳甲。
        new_lower = bits_to_gua(self.changed_bits[0:3])
        new_upper = bits_to_gua(self.changed_bits[3:6])
        gua = new_lower if i < 3 else new_upper
        gan = NAJIA_GAN[gua][0 if i < 3 else 1]
        zhi = NAJIA_ZHI[gua][i]
        return {"yang": new_bit, "gan": gan, "zhi": zhi,
                "wuxing": ZHI_WUXING[zhi],
                "liuqin": liuqin_of(self.palace_wx, ZHI_WUXING[zhi])}

    # ---- 用神 ----
    def find_yongshen(self, kind: str) -> list[Line]:
        return [r for r in self.rows if r.liuqin == kind]

    # ---- 用神评分（权重全部来自 rules） ----
    @staticmethod
    def _jin_tui(a: str, b: str):
        """同五行地支之间：前进为化进，后退为化退。"""
        if ZHI_WUXING[a] != ZHI_WUXING[b] or a == b:
            return None
        d = (zhi_index(b) - zhi_index(a)) % 12
        return "进" if d <= 6 else "退"

    def _score_one(self, y: "Line", w, is_chong) -> list[dict]:
        items = []
        wx = y.wuxing
        mwx = ZHI_WUXING[self.month_zhi]
        day_zhi = self.day_gz[1]
        dwx = ZHI_WUXING[day_zhi]

        if is_chong(self.month_zhi, y.zhi):
            items.append({"desc": "月破（月建冲之）", "delta": w("month.po"), "key": "month.po"})
        elif mwx == wx:
            items.append({"desc": "临月建", "delta": w("month.lin"), "key": "month.lin"})
        elif sheng(mwx, wx):
            items.append({"desc": "月建生之", "delta": w("month.sheng"), "key": "month.sheng"})
        elif ke(mwx, wx):
            items.append({"desc": "月建克之", "delta": w("month.ke"), "key": "month.ke"})

        if is_chong(day_zhi, y.zhi):
            strong = (mwx == wx) or sheng(mwx, wx)
            d = w("day.chong_wang") if strong else w("day.chong_shuai")
            items.append({"desc": "日辰冲之" + ("（旺→暗动）" if strong else "（衰→日破）"),
                          "delta": d,
                          "key": "day.chong_wang" if strong else "day.chong_shuai"})
        elif dwx == wx:
            items.append({"desc": "临日辰", "delta": w("day.lin"), "key": "day.lin"})
        elif sheng(dwx, wx):
            items.append({"desc": "日辰生之", "delta": w("day.sheng"), "key": "day.sheng"})
        elif ke(dwx, wx):
            items.append({"desc": "日辰克之", "delta": w("day.ke"), "key": "day.ke"})

        if y.kong:
            items.append({"desc": "旬空", "delta": w("kong"), "key": "kong"})

        if y.moving:
            items.append({"desc": "用神自身发动", "delta": w("moving.yong_moves"), "key": "moving.yong_moves"})
            ch = self.changed_line(y.pos)
            if ch:
                rel = wuxing_relation(wx, ch["wuxing"])
                if rel == "生我":
                    items.append({"desc": f"化回头生（变{ch['zhi']}{ch['wuxing']}）",
                                  "delta": w("hua.huisheng"), "key": "hua.huisheng"})
                elif rel == "克我":
                    items.append({"desc": f"化回头克（变{ch['zhi']}{ch['wuxing']}）",
                                  "delta": w("hua.huike"), "key": "hua.huike"})
                elif rel == "比和":
                    trend = self._jin_tui(y.zhi, ch["zhi"])
                    if trend == "进":
                        items.append({"desc": f"化进神（{y.zhi}→{ch['zhi']}）",
                                      "delta": w("hua.jin"), "key": "hua.jin"})
                    elif trend == "退":
                        items.append({"desc": f"化退神（{y.zhi}→{ch['zhi']}）",
                                      "delta": w("hua.tui"), "key": "hua.tui"})

        if y.shiying == "世":
            items.append({"desc": "用神临世爻", "delta": w("shi.yong_on_shi"), "key": "shi.yong_on_shi"})
        return items

    def evaluate(self, kind: str, rules=None) -> dict:
        """返回用神评分：{picked, items, score, grade, notes}"""
        from .jiazi import LIU_CHONG
        from .rules import grade

        rules = rules or self.rules

        def w(path):
            return rules.get(f"liuyao.{path}", 0.0)

        def is_chong(z1, z2):
            return any({a, b} == {z1, z2} for a, b in LIU_CHONG)

        ys = self.find_yongshen(kind)
        out = {"kind": kind, "count": len(ys), "items": [], "score": 0.0,
               "grade": "", "notes": [], "picked": None}
        if not ys:
            out["grade"] = "无法判"
            out["notes"].append(f"卦中无{kind}，需查伏神（本程序未展开伏神表）")
            return out

        scored = []
        for y in ys:
            items = self._score_one(y, w, is_chong)
            scored.append((y, sum(i["delta"] for i in items), items))
        scored.sort(key=lambda t: t[1], reverse=True)
        y, total, items = scored[0]
        if len(ys) > 1:
            out["notes"].append(f"{kind}两现（{len(ys)}个），取评分最高者：第{y.pos}爻")

        for a in [r for r in self.rows if r.moving and r is not y]:
            rel = wuxing_relation(a.wuxing, y.wuxing)
            if rel == "我生":
                d = w("moving.sheng_yong")
                items.append({"desc": f"动爻{a.liuqin}{a.gan}{a.zhi}生用神（原神得力）",
                              "delta": d, "key": "moving.sheng_yong"})
                total += d
            elif rel == "克我":
                d = w("moving.ke_yong")
                items.append({"desc": f"动爻{a.liuqin}{a.gan}{a.zhi}克用神（忌神当权）",
                              "delta": d, "key": "moving.ke_yong"})
                total += d

        if y.shiying != "世":
            shi = [r for r in self.rows if r.shiying == "世"][0]
            rel = wuxing_relation(shi.wuxing, y.wuxing)
            if rel == "我生":
                d = w("shi.shi_sheng")
                items.append({"desc": "世爻生用神", "delta": d, "key": "shi.shi_sheng"})
                total += d
            elif rel == "克我":
                d = w("shi.shi_ke")
                items.append({"desc": "世爻克用神", "delta": d, "key": "shi.shi_ke"})
                total += d

        out.update({"picked": y, "items": items, "score": total,
                    "grade": grade(total, rules.get("liuyao.thresholds"))})
        return out

    def yongshen_reading(self, kind: str, rules=None) -> list[str]:
        """兼容旧接口：返回文字行。"""
        ev = self.evaluate(kind, rules)
        lines = list(ev["notes"])
        for it in ev["items"]:
            lines.append(f"{it['desc']}　{it['delta']:+.1f}")
        lines.append(f"合计 {ev['score']:+.1f} → {ev['grade']}")
        return lines


def cast_from_coins(backs: list[int], day_gz: str, month_zhi: str,
                    rules=None) -> LiuYaoChart:
    """backs: 六个 0-3 的整数，每个表示该次摇出的「背」数（自初爻起）。
    1 背 = 少阳；2 背 = 少阴；0 背（三面）= 老阴（动）；3 背 = 老阳（动）。"""
    if len(backs) != 6:
        raise ValueError("必须是六次摇卦结果")
    lines, moving = [], []
    for b in backs:
        if b == 1:
            lines.append(1); moving.append(False)
        elif b == 2:
            lines.append(0); moving.append(False)
        elif b == 3:
            lines.append(1); moving.append(True)
        elif b == 0:
            lines.append(0); moving.append(True)
        else:
            raise ValueError("每次背数只能是 0-3")
    return LiuYaoChart(lines, moving, day_gz, month_zhi, rules)


def cast_from_hexagram(name: str, moving_positions: list[int],
                       day_gz: str, month_zhi: str, rules=None) -> LiuYaoChart:
    from .jiazi import GUA_NAMES
    if name not in GUA_NAMES:
        raise ValueError(f"未找到卦名：{name}")
    upper, lower = GUA_NAMES[name]
    bits = [0] * 6
    for i in range(3):
        bits[i] = (GUA_BITS[lower] >> i) & 1
        bits[i + 3] = (GUA_BITS[upper] >> i) & 1
    moving = [(i + 1) in moving_positions for i in range(6)]
    return LiuYaoChart(bits, moving, day_gz, month_zhi, rules)


def render(chart: LiuYaoChart, ask: str | None = None, with_score: bool = True) -> str:
    seq_name = ['本宫', '一世', '二世', '三世', '四世', '五世', '游魂', '归魂'][chart.palace_seq - 1]
    out = []
    out.append(f"本卦：{chart.name}　（{chart.palace}宫·{seq_name}，宫五行属{chart.palace_wx}）")
    if chart.has_change:
        out.append(f"变卦：{chart.changed_name}")
    out.append(f"月建 {chart.month_zhi}　日辰 {chart.day_gz}　旬空 {chart.kong1}{chart.kong2}"
               f"　六神起{LIUSHEN[chart.ls_start]}")
    out.append("─" * 60)
    head = f"{'':4}{'六神':4}{'六亲':4}{'纳甲':6}{'五行':4}{'世应':4}{'爻象':10}{'标记':6}"
    out.append(head)
    for row in reversed(chart.rows):
        sig = "▅▅▅▅▅▅" if row.yang else "▅▅　▅▅"
        mark = ""
        if row.moving:
            mark = "○动" if row.yang else "×动"
        if row.kong:
            mark += " 空"
        line = (f"{row.label:4}{row.liushen:5}{row.liuqin:4}"
                f"{row.gan + row.zhi:4}{row.wuxing:4}{(row.shiying or ''):4}{sig}　{mark}")
        ch = chart.changed_line(row.pos)
        if ch:
            line += f"　→ {ch['gan']}{ch['zhi']}{ch['wuxing']} {ch['liuqin']}"
        out.append(line)
    out.append("─" * 60)
    if ask and with_score:
        from .rules import bar
        from .utils import pad
        ev = chart.evaluate(ask)
        y = ev["picked"]
        if y is None:
            out.append(f"【用神：{ask}】")
            for note in ev["notes"]:
                out.append("  · " + note)
        else:
            out.append(f"【用神：{ask}】取第{y.pos}爻 {y.label} {y.gan}{y.zhi}"
                       f"（{y.wuxing}）{y.liuqin}{'·世' if y.shiying == '世' else ''}")
            for note in ev["notes"]:
                out.append("  · " + note)
            scale = max((abs(i["delta"]) for i in ev["items"]), default=1)
            for it in ev["items"]:
                out.append(f"  {pad(it['desc'], 32)}{it['delta']:+5.1f}  "
                           f"{bar(it['delta'], scale, 8)}")
            out.append("  " + "─" * 50)
            out.append(f"  {pad('合计', 32)}{ev['score']:+5.1f}　→　{ev['grade']}")
    return "\n".join(out)

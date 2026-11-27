"""梅花易数引擎。

规则来源：《梅花易数》（旧题邵雍）——「体用总诀」「互卦」「变卦」三篇。
核心口径：动爻所在之卦为用，不动者为体；体为主（我），用为事（彼）；
         用生体、比和、体克用 为吉；体生用、用克体 为凶。
"""
from datetime import datetime

from .jiazi import (GUA_BITS, BITS_GUA, GUA_WUXING, NUM_XIANTIAN, XIANTIAN_NUM,
                    LIUSHI_SI_GUA, GUA_XIANG, wuxing_relation, WUXING_SHENG, WUXING_KE)
from .lunar import lunar_date
from .calendar import four_pillars


def num_to_gua(n: int) -> str:
    """先天数 1-8 -> 卦。n=0 或 8 视为坤。"""
    r = n % 8
    return NUM_XIANTIAN[8 if r == 0 else r]


def bits_of(gua: str) -> list[int]:
    b = GUA_BITS[gua]
    return [(b >> i) & 1 for i in range(3)]


def gua_of_bits(bits: list[int]) -> str:
    return BITS_GUA[bits[0] | (bits[1] << 1) | (bits[2] << 2)]


REL_LABEL = {"生我": "用生体", "比和": "比和", "我克": "体克用",
             "我生": "体生用", "克我": "用克体"}
WX_SEASON = {"寅": "木", "卯": "木", "辰": "土", "巳": "火", "午": "火", "未": "土",
             "申": "金", "酉": "金", "戌": "土", "亥": "水", "子": "水", "丑": "土"}


class MeiHuaChart:
    def __init__(self, upper: str, lower: str, moving_pos: int, basis: str, rules=None):
        from .rules import Rules
        self.rules = rules or Rules()
        self.upper = upper
        self.lower = lower
        self.moving_pos = moving_pos          # 1..6，自下而上
        self.basis = basis
        self.name = LIUSHI_SI_GUA[upper][lower]

        # 体用：动爻在下卦(1-3) -> 下卦为用、上卦为体
        if moving_pos <= 3:
            self.ti, self.yong = upper, lower
            self.ti_pos, self.yong_pos = "上", "下"
        else:
            self.ti, self.yong = lower, upper
            self.ti_pos, self.yong_pos = "下", "上"

        bits = bits_of(lower) + bits_of(upper)   # 初..上
        self.bits = bits
        # 互卦：二三四为下互，三四五为上互
        hu_lower = gua_of_bits(bits[1:4])
        hu_upper = gua_of_bits(bits[2:5])
        self.hu = (hu_upper, hu_lower)
        self.hu_name = LIUSHI_SI_GUA[hu_upper][hu_lower]
        # 变卦
        changed = bits[:]
        changed[moving_pos - 1] ^= 1
        self.changed_bits = changed
        self.bian_lower = gua_of_bits(changed[0:3])
        self.bian_upper = gua_of_bits(changed[3:6])
        self.bian_name = LIUSHI_SI_GUA[self.bian_upper][self.bian_lower]
        # 变卦中体、用所在位置
        self.bian_ti = self.bian_upper if self.ti_pos == "上" else self.bian_lower
        self.bian_yong = self.bian_lower if self.yong_pos == "下" else self.bian_upper

    # ---- 判断 ----
    def verdict_ti_yong(self):
        ti_wx, yong_wx = GUA_WUXING[self.ti], GUA_WUXING[self.yong]
        rel = wuxing_relation(ti_wx, yong_wx)   # 从体的视角看用
        table = {
            "生我": ("吉", "用生体，有进益之喜", "外来之力扶我，事有助"),
            "比和": ("吉", "体用比和，百事顺遂", "同气相求，顺遂"),
            "我克": ("小吉", "体克用，诸事吉", "我能制彼，费力而可成"),
            "我生": ("凶", "体生用，有耗失之患", "我反耗于彼，泄气劳损"),
            "克我": ("凶", "用克体，诸事凶", "外力伤我，事多阻败"),
        }[rel]
        return rel, table

    def verdict_changed(self):
        ti_wx, yong_wx = GUA_WUXING[self.bian_ti], GUA_WUXING[self.bian_yong]
        rel = wuxing_relation(ti_wx, yong_wx)
        text = {
            "生我": "变卦用生体——末后有进益",
            "比和": "变卦体用比和——末后顺遂",
            "我克": "变卦体克用——末后费心得成",
            "我生": "变卦体生用——末后耗损",
            "克我": "变卦用克体——末后不利",
        }[rel]
        return rel, text

    def trend(self):
        _, tv = self.verdict_ti_yong()
        _, cv = self.verdict_changed()
        good_t = tv[0] in ("吉", "小吉")
        good_c = "不利" not in cv and "耗损" not in cv
        if good_t and good_c:
            return "先吉后吉，事可成"
        if good_t and not good_c:
            return "先吉后凶，起头顺而收尾难，宜见好就收"
        if not good_t and good_c:
            return "先凶后吉，起初受阻而终有转机"
        return "先凶后凶，此事不宜强求"

    def shu(self):
        return XIANTIAN_NUM[self.ti], XIANTIAN_NUM[self.yong]

    # ---- 加权评分 ----
    def score(self, month_zhi: str | None = None):
        from .rules import grade
        from .jiazi import season_state
        r = self.rules
        rel_t = r.get("meihua.relation")
        st = r.get("meihua.stage")
        items = []

        rel_ben = wuxing_relation(GUA_WUXING[self.ti], GUA_WUXING[self.yong])
        items.append({"desc": f"本卦体用（{REL_LABEL[rel_ben]}）",
                      "delta": rel_t[REL_LABEL[rel_ben]] * st["ben"],
                      "key": f"meihua.relation.{REL_LABEL[rel_ben]}", "mul": st["ben"]})

        hu_up = self.hu[0]
        rel_hu = wuxing_relation(GUA_WUXING[self.ti], GUA_WUXING[hu_up])
        items.append({"desc": f"互卦（{hu_up}·{REL_LABEL[rel_hu]}）",
                      "delta": rel_t[REL_LABEL[rel_hu]] * st["hu"],
                      "key": f"meihua.relation.{REL_LABEL[rel_hu]}", "mul": st["hu"]})

        rel_bian = wuxing_relation(GUA_WUXING[self.bian_ti], GUA_WUXING[self.bian_yong])
        items.append({"desc": f"变卦体用（{REL_LABEL[rel_bian]}）",
                      "delta": rel_t[REL_LABEL[rel_bian]] * st["bian"],
                      "key": f"meihua.relation.{REL_LABEL[rel_bian]}", "mul": st["bian"]})

        if month_zhi:
            state = season_state(GUA_WUXING[self.ti], month_zhi)
            d = r.get(f"meihua.wangshuai.{state}", 0.0)
            items.append({"desc": f"体卦在{month_zhi}月为「{state}」", "delta": d,
                          "key": f"meihua.wangshuai.{state}", "mul": 1})

        total = sum(i["delta"] for i in items)
        return {"items": items, "score": total,
                "grade": grade(total, r.get("meihua.thresholds"))}


def cast_by_numbers(a: int, b: int, basis: str = "", rules=None) -> MeiHuaChart:
    upper = num_to_gua(a)
    lower = num_to_gua(b)
    moving = (a + b) % 6
    moving = 6 if moving == 0 else moving
    return MeiHuaChart(upper, lower, moving, basis or f"报数 {a}、{b}", rules)


def cast_by_time(dt: datetime, longitude: float = 120.0, tz: float = 8.0,
                 use_lunar: bool = True, rules=None) -> MeiHuaChart:
    """时间起卦：年支数 + 月 + 日 定上卦；再加时支数定下卦；总合定动爻。
    传统用农历月日；use_lunar=False 时直接用公历数（现代通行简便法）。"""
    ld = lunar_date(dt, tz) if use_lunar else None
    p = four_pillars(dt, longitude, tz)
    year_zhi_num = "子丑寅卯辰巳午未申酉戌亥".index(p.year[1]) + 1
    month_num = ld["month"] if ld else dt.month
    day_num = ld["day"] if ld else dt.day
    hour_zhi_num = "子丑寅卯辰巳午未申酉戌亥".index(p.hour[1]) + 1

    s1 = year_zhi_num + month_num + day_num
    s2 = s1 + hour_zhi_num
    upper = num_to_gua(s1)
    lower = num_to_gua(s2)
    moving = s2 % 6
    moving = 6 if moving == 0 else moving
    day_txt = ld["day_cn"] if ld else str(day_num)
    basis = (f"{'农历' if use_lunar else '公历'} "
             f"{(ld['month_name'] if ld else str(dt.month) + '月')}{day_txt}日 "
             f"{p.hour[1]}时（年支{year_zhi_num}+月{month_num}+日{day_num}={s1}，"
             f"+时{hour_zhi_num}={s2}）")
    c = MeiHuaChart(upper, lower, moving, basis, rules)
    return c


def render(c: MeiHuaChart, month_zhi: str | None = None, with_score: bool = True) -> str:
    out = []
    out.append(f"起卦依据：{c.basis}")
    out.append(f"本卦：{c.name}　（上{c.upper}·{GUA_WUXING[c.upper]}　下{c.lower}·{GUA_WUXING[c.lower]}）")
    out.append(f"动爻：第{c.moving_pos}爻")
    out.append(f"体卦：{c.ti}（{c.ti_pos}卦，{GUA_WUXING[c.ti]}）　"
               f"用卦：{c.yong}（{c.yong_pos}卦，{GUA_WUXING[c.yong]}）")
    out.append(f"互卦：{c.hu_name}　（上{c.hu[0]}　下{c.hu[1]}）—— 事情的中段")
    out.append(f"变卦：{c.bian_name}　（末后之期，变中体{c.bian_ti}　用{c.bian_yong}）")
    out.append("─" * 56)
    rel, (grade, classic, plain) = c.verdict_ti_yong()
    out.append(f"体用关系：{rel}　→　{grade}")
    out.append(f"　原文：{classic}")
    out.append(f"　白话：{plain}")
    _, ct = c.verdict_changed()
    out.append(f"　变卦：{ct}")
    out.append(f"　总势：{c.trend()}")
    out.append(f"　卦数应期参考：体{XIANTIAN_NUM[c.ti]} + 用{XIANTIAN_NUM[c.yong]} "
               f"= {sum(c.shu())}（可作日、月数参考）")
    if not with_score:
        return "\n".join(out)
    from .rules import bar
    from .utils import pad
    sc = c.score(month_zhi)
    out.append("─" * 56)
    out.append("加权评分（权重见 rules.meihua）：")
    scale = max((abs(i["delta"]) for i in sc["items"]), default=1)
    for it in sc["items"]:
        out.append(f"  {pad(it['desc'], 28)}{it['delta']:+5.2f}  {bar(it['delta'], scale, 8)}")
    out.append(f"  {pad('合计', 28)}{sc['score']:+5.2f}　→　{sc['grade']}")
    return "\n".join(out)

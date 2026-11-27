"""紫微斗数（北派·十四主星）排盘引擎。

口径说明
--------
· 生年干支以**农历春节**为界（不是立春），月份用农历月，日数用农历日
· 命宫：寅起正月顺数至生月，再自该宫起子时逆数至生时
· 身宫：同上，但顺数至生时
· 宫干：五虎遁，甲己起丙寅、乙庚起戊寅、丙辛起庚寅、丁壬起壬寅、戊癸起甲寅
· 五行局：命宫干支纳音 → 水二 / 木三 / 金四 / 土五 / 火六
· 紫微：日数补足为局数倍数，商从寅顺数，补数为偶则再顺行、为奇则逆退
· 天府：与紫微以寅申为轴（天府 = 16 − 紫微）
· 闰月：本程序按「闰月作本月」处理，部分流派以下半月按下月，属正常分歧

已知边界：本实现只排十四主星与主要辅星，不排杂曜（红鸾天喜、天刑天姚等）；
亮度（庙旺利陷）与飞星四化未做，这两项各家差异大，留待按所习补充。
"""
from datetime import datetime

from .jiazi import GAN, ZHI, jiazi, nayin, yinyang
from .lunar import lunar_date
from .calendar import four_pillars

PALACE_NAMES = ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
                "迁移", "交友", "官禄", "田宅", "福德", "父母"]

# 紫微系（逆行）：名称, 相对紫微的位移
ZIWEI_SERIES = [("紫微", 0), ("天机", -1), ("太阳", -3), ("武曲", -4),
                ("天同", -5), ("廉贞", -8)]
# 天府系（顺行）
TIANFU_SERIES = [("天府", 0), ("太阴", 1), ("贪狼", 2), ("巨门", 3),
                 ("天相", 4), ("天梁", 5), ("七杀", 6), ("破军", 10)]

WUXING_JU = {"水": ("水二局", 2), "木": ("木三局", 3), "金": ("金四局", 4),
             "土": ("土五局", 5), "火": ("火六局", 6)}

# 生年四化
SIHUA = {
    "甲": {"禄": "廉贞", "权": "破军", "科": "武曲", "忌": "太阳"},
    "乙": {"禄": "天机", "权": "天梁", "科": "紫微", "忌": "太阴"},
    "丙": {"禄": "天同", "权": "天机", "科": "文昌", "忌": "廉贞"},
    "丁": {"禄": "太阴", "权": "天同", "科": "天机", "忌": "巨门"},
    "戊": {"禄": "贪狼", "权": "太阴", "科": "右弼", "忌": "天机"},
    "己": {"禄": "武曲", "权": "贪狼", "科": "天梁", "忌": "文曲"},
    "庚": {"禄": "太阳", "权": "武曲", "科": "太阴", "忌": "天同"},
    "辛": {"禄": "巨门", "权": "太阳", "科": "文曲", "忌": "文昌"},
    "壬": {"禄": "天梁", "权": "紫微", "科": "左辅", "忌": "武曲"},
    "癸": {"禄": "破军", "权": "巨门", "科": "太阴", "忌": "贪狼"},
}

# 天魁天钺（按年干）
KUIOUYUE = {"甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
            "乙": ("子", "申"), "己": ("子", "申"),
            "丙": ("亥", "酉"), "丁": ("亥", "酉"),
            "辛": ("午", "寅"), "壬": ("卯", "巳"), "癸": ("卯", "巳")}

# 禄存（按年干）
LUCUN = {"甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳",
         "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}

# 火星铃星起点（按年支三合）
HUOLING = {"寅": ("丑", "卯"), "午": ("丑", "卯"), "戌": ("丑", "卯"),
           "申": ("寅", "戌"), "子": ("寅", "戌"), "辰": ("寅", "戌"),
           "巳": ("卯", "戌"), "酉": ("卯", "戌"), "丑": ("卯", "戌"),
           "亥": ("酉", "戌"), "卯": ("酉", "戌"), "未": ("酉", "戌")}

YIMA = {"寅": "申", "午": "申", "戌": "申", "申": "寅", "子": "寅", "辰": "寅",
        "巳": "亥", "酉": "亥", "丑": "亥", "亥": "巳", "卯": "巳", "未": "巳"}

JI_STARS = {"左辅", "右弼", "文昌", "文曲", "天魁", "天钺", "禄存", "天马"}
SHA_STARS = {"擎羊", "陀罗", "火星", "铃星", "地空", "地劫"}


def _i(z: str) -> int:
    return ZHI.index(z)


def _z(i: int) -> str:
    return ZHI[i % 12]


class ZiWeiChart:
    def __init__(self, dt: datetime, longitude: float = 120.0, tz: float = 8.0,
                 gender: str = "m", rules=None):
        from .rules import Rules
        self.rules = rules or Rules()
        self.dt = dt
        self.gender = gender

        ld = lunar_date(dt, tz)
        self.lunar = ld
        p = four_pillars(dt, longitude, tz)
        self.pillars = p
        self.hour_zhi = p.hour[1]
        # 生年干支以农历年为准（春节换年）
        self.year_gz = jiazi((ld["year"] - 4) % 60)
        self.month = ld["month"]
        self.day = ld["day"]

        self.ming = self._ming_gong()
        self.shen = self._shen_gong()
        self.gong_gan = self._palace_gan()
        self.palaces = self._palace_names()

        ming_gz = self.gong_gan[self.ming] + _z(self.ming)
        wy = nayin(ming_gz)[-1]
        self.ju_name, self.ju_num = WUXING_JU[wy]
        self.ming_gz = ming_gz

        self.ziwei = self._ziwei_pos()
        self.tianfu = (16 - self.ziwei) % 12
        self.stars = self._main_stars()
        self._aux_stars()
        self.sihua = SIHUA[self.year_gz[0]]
        self.dayun = self._dayun()

    # ---------- 命身宫 ----------
    def _ming_gong(self) -> int:
        m = _i("寅") + (self.month - 1)          # 寅起正月顺数至生月
        return (m - _i(self.hour_zhi)) % 12      # 再逆数至生时

    def _shen_gong(self) -> int:
        m = _i("寅") + (self.month - 1)
        return (m + _i(self.hour_zhi)) % 12

    # ---------- 宫干 ----------
    def _palace_gan(self) -> dict:
        start = (GAN.index(self.year_gz[0]) % 5 * 2 + 2) % 10   # 五虎遁：寅宫天干
        out = {}
        for k in range(12):
            z = _i("寅") + k
            out[z % 12] = GAN[(start + k) % 10]
        return out

    def _palace_names(self) -> dict:
        out = {}
        for k in range(12):
            out[(self.ming - k) % 12] = PALACE_NAMES[k]   # 自命宫逆布
        return out

    # ---------- 紫微定位 ----------
    def _ziwei_pos(self) -> int:
        m, d = self.ju_num, self.day
        c = (-d) % m                       # 补数：使其成为 m 的倍数
        q = (d + c) // m
        pos = (_i("寅") + (q - 1)) % 12    # 商数自寅顺数
        pos = (pos + c) % 12 if c % 2 == 0 else (pos - c) % 12
        return pos

    # ---------- 十四主星 ----------
    def _main_stars(self) -> dict:
        out = {i: [] for i in range(12)}
        for name, off in ZIWEI_SERIES:
            out[(self.ziwei + off) % 12].append(name)
        for name, off in TIANFU_SERIES:
            out[(self.tianfu + off) % 12].append(name)
        return out

    # ---------- 辅星 ----------
    def _aux_stars(self):
        st = self.stars
        m_idx = self.month - 1
        h_idx = _i(self.hour_zhi)

        st[(_i("辰") + m_idx) % 12].append("左辅")      # 辰起正月顺
        st[(_i("戌") - m_idx) % 12].append("右弼")      # 戌起正月逆
        st[(_i("戌") - h_idx) % 12].append("文昌")      # 戌起子时逆
        st[(_i("辰") + h_idx) % 12].append("文曲")      # 辰起子时顺
        st[(_i("亥") + h_idx) % 12].append("地劫")      # 亥起子时顺
        st[(_i("亥") - h_idx) % 12].append("地空")      # 亥起子时逆

        kui, yue = KUIOUYUE[self.year_gz[0]]
        st[_i(kui) % 12].append("天魁")
        st[_i(yue) % 12].append("天钺")

        lc = _i(LUCUN[self.year_gz[0]])
        st[lc].append("禄存")
        st[(lc + 1) % 12].append("擎羊")
        st[(lc - 1) % 12].append("陀罗")

        huo, ling = HUOLING[self.year_gz[1]]
        st[(_i(huo) + h_idx) % 12].append("火星")
        st[(_i(ling) + h_idx) % 12].append("铃星")

        st[_i(YIMA[self.year_gz[1]]) % 12].append("天马")

    # ---------- 大限 ----------
    def _dayun(self):
        forward = (yinyang(self.year_gz[0]) == "阳") == (self.gender == "m")
        out = []
        for k in range(12):
            z = (self.ming + k) % 12 if forward else (self.ming - k) % 12
            a0 = self.ju_num + 10 * k
            out.append({"zhi": _z(z), "start": a0, "end": a0 + 9,
                        "palace": self.palaces[z]})
        return out

    # ---------- 查询 ----------
    def stars_at(self, z: int) -> list[str]:
        return self.stars[z % 12]

    def sihua_at(self, z: int) -> list[str]:
        out = []
        for hua, star in self.sihua.items():
            if star in self.stars[z % 12]:
                out.append(f"{star}化{hua}")
        return out

    def sanfang(self) -> tuple[int, int, int]:
        """三方四正：命宫 + 财帛 + 官禄 + 迁移"""
        return ((self.ming + 4) % 12, (self.ming + 8) % 12, (self.ming + 6) % 12)

    # ---------- 评分 ----------
    def factors(self) -> list[dict]:
        def w(k):
            return self.rules.get(f"ziwei.score.{k}", 0.0)

        out = []
        mstars = self.stars[self.ming]
        fa, guan, qian = self.sanfang()
        area = {self.ming, fa, guan, qian}

        ji = [s for z in area for s in self.stars[z] if s in JI_STARS]
        sha = [s for z in area for s in self.stars[z] if s in SHA_STARS]
        if ji:
            out.append({"key": "ziwei.score.ji_xing", "label": f"三方四正见吉星（{'、'.join(ji)}）",
                        "mul": len(ji), "w": w("ji_xing")})
        if sha:
            out.append({"key": "ziwei.score.sha_xing", "label": f"三方四正见煞星（{'、'.join(sha)}）",
                        "mul": len(sha), "w": w("sha_xing")})
        for hua in self.sihua_at(self.ming):
            key = "hua_lu" if "化禄" in hua else ("hua_ji" if "化忌" in hua else "hua_other")
            out.append({"key": f"ziwei.score.{key}", "label": f"命宫{hua}",
                        "mul": 1, "w": w(key)})
        if not mstars:
            out.append({"key": "ziwei.score.empty", "label": "命宫空宫（借对宫）",
                        "mul": 1, "w": w("empty")})
        return out


def render(c: ZiWeiChart) -> str:
    from .utils import pad
    ld = c.lunar
    out = []
    out.append(f"公历：{c.dt:%Y-%m-%d %H:%M}　→　农历 {ld['year']} 年 "
               f"{ld['month_name']}{ld['day_cn']}日 {c.hour_zhi}时")
    out.append(f"生年干支：{c.year_gz}（以春节为界）　"
               f"命宫：{_z(c.ming)}宫（{c.ming_gz}）　身宫：{_z(c.shen)}宫")
    out.append(f"五行局：{c.ju_name}　紫微在{_z(c.ziwei)}　天府在{_z(c.tianfu)}　"
               f"生年四化：{c.year_gz[0]}干 "
               + "、".join(f"{k}→{v}" for k, v in c.sihua.items()))
    out.append("")

    layout = [[5, 6, 7, 8], [4, -1, -1, 9], [3, -1, -1, 10], [2, 1, 0, 11]]
    W = 22
    top = "┌" + "┬".join("─" * W for _ in range(4)) + "┐"
    mid = "├" + "┼".join("─" * W for _ in range(4)) + "┤"
    bot = "└" + "┴".join("─" * W for _ in range(4)) + "┘"
    out.append(top)
    center = ["紫　微　斗　数", f"{c.year_gz}年　{c.ju_name}",
              f"命宫{_z(c.ming)}　身宫{_z(c.shen)}",
              "", "◆ 命宫　◇ 身宫", ""]
    for ri, row in enumerate(layout):
        if ri in (1, 2):
            left = self_cell(c, row[0], W)
            right = self_cell(c, row[3], W)
            for line in range(6):
                txt = ""
                if ri == 1 and line < 3:
                    txt = center[line]
                elif ri == 2 and line < 3:
                    txt = center[3 + line]
                out.append("│" + pad(left[line], W) + "│"
                           + pad("　" + txt, W * 2 + 1) + "│"
                           + pad(right[line], W) + "│")
        else:
            cells = [self_cell(c, zi, W) for zi in row]
            for line in range(6):
                out.append("│" + "│".join(pad(cc[line], W) for cc in cells) + "│")
        out.append(mid if ri < 3 else bot)
    return "\n".join(out)


def self_cell(c: ZiWeiChart, zi: int, W: int) -> list[str]:
    pname = c.palaces[zi]
    gan = c.gong_gan[zi]
    stars = c.stars[zi]
    main = [s for s in stars if s not in JI_STARS and s not in SHA_STARS]
    aux = [s for s in stars if s in JI_STARS]
    sha = [s for s in stars if s in SHA_STARS]
    hua = c.sihua_at(zi)
    dy = next((d for d in c.dayun if d["zhi"] == _z(zi)), None)
    mark = "◆" if zi == c.ming else ("◇" if zi == c.shen else "")
    lines = [
        f"{pname}{mark}　{gan}{_z(zi)}",
        " ".join(main) if main else "（空宫）",
        " ".join(hua),
        " ".join(aux),
        " ".join(sha),
        f"大限 {dy['start']}-{dy['end']}" if dy else "",
    ]
    return lines


def build(dt: datetime, longitude: float = 120.0, tz: float = 8.0,
          gender: str = "m", rules=None) -> ZiWeiChart:
    return ZiWeiChart(dt, longitude, tz, gender, rules)

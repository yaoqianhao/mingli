"""大六壬（四课三传）引擎。

口径说明
--------
· 月将：太阳过宫，以中气换将（雨水后亥将登明 … 大寒后子将神后）
· 天地盘：月将加占时，顺布十二支
· 十干寄宫：甲寅 乙辰 丙巳 丁未 戊巳 己未 庚申 辛戌 壬亥 癸丑
· 四课：日干寄宫起一课，上神再作下起二课；日支起三课，上神再作下起四课
· 三传：初传＝发用，中传＝初传上神，末传＝中传上神
· 发用取法：伏吟/返吟 → 贼克（元首·重审）→ 比用（知一）→ 涉害 → 遥克 → 昴星

已知边界：别责、八专两门本程序只作标识与简化取传，涉害的「归途深浅」按
顺数经过之克数计，属通行简法。遇到这些课体时输出会标 [简]，
需以你所习的传本核对。
"""
from datetime import datetime

from .calendar import four_pillars, solar_term_events, jd_from_datetime
from .jiazi import ZHI, ZHI_WUXING, ke, sheng, yinyang, jiazi_index

# 十干寄宫
JI_GONG = {"甲": "寅", "乙": "辰", "丙": "巳", "丁": "未", "戊": "巳",
           "己": "未", "庚": "申", "辛": "戌", "壬": "亥", "癸": "丑"}

# 中气黄经 -> 月将
JIANG_BY_TERM = {330: "亥", 0: "戌", 30: "酉", 60: "申", 90: "未", 120: "午",
                 150: "巳", 180: "辰", 210: "卯", 240: "寅", 270: "丑", 300: "子"}
JIANG_NAME = {"亥": "登明", "戌": "河魁", "酉": "从魁", "申": "传送", "未": "小吉",
              "午": "胜光", "巳": "太乙", "辰": "天罡", "卯": "太冲", "寅": "功曹",
              "丑": "大吉", "子": "神后"}

# 十二天将（顺序固定）
JIANG12 = ["贵人", "螣蛇", "朱雀", "六合", "勾陈", "青龙",
           "天空", "白虎", "太常", "玄武", "太阴", "天后"]
JI_JIANG = {"贵人", "青龙", "六合", "太常", "太阴", "天后"}
XIONG_JIANG = {"螣蛇", "白虎", "玄武", "天空", "勾陈"}

# 阳贵 / 阴贵
GUI_REN = {"甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
           "乙": ("子", "申"), "己": ("子", "申"),
           "丙": ("亥", "酉"), "丁": ("亥", "酉"),
           "辛": ("午", "寅"),
           "壬": ("巳", "卯"), "癸": ("巳", "卯")}
SHUN_ZHI = set("亥子丑寅卯辰")      # 贵人临此六支顺行

# 驿马
YIMA = {"申": "寅", "子": "寅", "辰": "寅", "寅": "申", "午": "申", "戌": "申",
        "巳": "亥", "酉": "亥", "丑": "亥", "亥": "巳", "卯": "巳", "未": "巳"}


def _idx(z: str) -> int:
    return ZHI.index(z)


def _add(z: str, n: int) -> str:
    return ZHI[(_idx(z) + n) % 12]


def _chong(z: str) -> str:
    return _add(z, 6)


def _ke(a: str, b: str) -> bool:
    """a（地支）克 b（地支）"""
    return ke(ZHI_WUXING[a], ZHI_WUXING[b])


def yuejiang_of(dt: datetime, tz: float = 8.0):
    """返回 (月将地支, 中气名, 中气时刻)。"""
    jd_ut = jd_from_datetime(dt) - tz / 24.0
    events = solar_term_events(jd_ut - 400, jd_ut + 5)
    past = [e for e in events if e[0] <= jd_ut]
    if not past:
        raise RuntimeError("节气窗口不足")
    jd, name, deg = past[-1]
    # 只需最近的中气：往回找最近的 30 倍黄经节气
    zhongqi = [e for e in past if e[2] % 30 == 0]
    jd2, name2, deg2 = zhongqi[-1]
    return JIANG_BY_TERM[deg2], name2, jd2 + tz / 24.0


class LiuRenChart:
    def __init__(self, dt: datetime, longitude: float = 120.0, tz: float = 8.0,
                 rules=None):
        from .rules import Rules
        self.rules = rules or Rules()
        self.dt = dt
        self.pillars = four_pillars(dt, longitude, tz, )
        p = self.pillars
        self.day_gan, self.day_zhi = p.day[0], p.day[1]
        self.hour_zhi = p.hour[1]

        self.jiang, self.zhongqi, self.zhongqi_jd = yuejiang_of(dt, tz)

        # 天地盘：月将加占时
        self.tianpan = {}
        for i in range(12):
            ground = _add(self.hour_zhi, i)
            sky = _add(self.jiang, i)
            self.tianpan[ground] = sky

        self.sike = self._four_lessons()
        self.chuan, self.keti, self.keti_note = self._three_transmissions()
        self.tianjiang = self._twelve_generals(dt)

    # ---------- 四课 ----------
    def _four_lessons(self):
        g = JI_GONG[self.day_gan]
        k1 = (g, self.tianpan[g])
        k2 = (k1[1], self.tianpan[k1[1]])
        k3 = (self.day_zhi, self.tianpan[self.day_zhi])
        k4 = (k3[1], self.tianpan[k3[1]])
        return [k1, k2, k3, k4]

    # ---------- 三传 ----------
    def _three_transmissions(self):
        tp = self.tianpan
        sike = self.sike

        # 伏吟 / 返吟
        if all(tp[z] == z for z in ZHI):
            return self._fuyin(), "伏吟课", "天盘与地盘全同。主静守、旧事重提。"
        if all(tp[z] == _chong(z) for z in ZHI):
            return self._fanyin(), "返吟课", "天地盘全冲。主反复、去而复来。"

        zei, ke_list = [], []          # 下贼上 / 上克下
        for i, (xia, shang) in enumerate(sike):
            if _ke(xia, shang):
                zei.append((i, shang))
            elif _ke(shang, xia):
                ke_list.append((i, shang))

        cand, tu = None, None
        if zei:
            cand, tu = zei, "贼"
        elif ke_list:
            cand, tu = ke_list, "克"

        if cand:
            if len(cand) == 1:
                name = "重审课" if tu == "贼" else "元首课"
                note = ("下贼上，事前屈后伸，宜后动。" if tu == "贼"
                        else "上克下，事顺势而下，宜先动。")
                return self._fill(cand[0][1]), name, note
            # 比用
            same = [c for c in cand if yinyang(self.day_gan) ==
                    ("阳" if _idx(c[1]) % 2 == 0 else "阴")]
            if len(same) == 1:
                return self._fill(same[0][1]), "知一课", "多克取比，择其与日干同性者发用。"
            # 涉害
            pool = same if same else cand
            depth = [(self._shehai(c[1]), c[1]) for c in pool]
            depth.sort(key=lambda t: -t[0])
            if len(depth) > 1 and depth[0][0] == depth[1][0]:
                return (self._fill(depth[0][1]), "涉害课[简]",
                        "涉害深浅相等，复数并存，本程序取其一，需人工复核。")
            return self._fill(depth[0][1]), "涉害课", "多克而比用不成，取涉害最深者发用。"

        # 遥克：四课上神与日干相克
        gan_wx = ZHI_WUXING[JI_GONG[self.day_gan]]
        yao = [s for (_x, s) in sike if ke(ZHI_WUXING[s], gan_wx)
               or ke(gan_wx, ZHI_WUXING[s])]
        if yao:
            return self._fill(yao[0]), "遥克课", "课中无克，取上神与日干遥相克者发用。"

        # 昴星
        if yinyang(self.day_gan) == "阳":
            first = tp["酉"]
        else:
            first = [z for z in ZHI if tp[z] == "酉"][0]
        return self._fill(first), "昴星课", "无克无遥克，阳日取酉上神，阴日取酉下神。"

    def _fill(self, first: str):
        mid = self.tianpan[first]
        last = self.tianpan[mid]
        return (first, mid, last)

    def _fuyin(self):
        g = JI_GONG[self.day_gan]
        first = self.tianpan[g]
        # 有克取克
        for xia, shang in self.sike:
            if _ke(xia, shang) or _ke(shang, xia):
                first = shang
                break
        mid = self._xing(first)
        last = self._xing(mid)
        return (first, mid, last)

    def _fanyin(self):
        for xia, shang in self.sike:
            if _ke(xia, shang) or _ke(shang, xia):
                return self._fill(shang)
        return self._fill(YIMA[self.day_zhi])

    @staticmethod
    def _xing(z: str) -> str:
        """刑：用于伏吟课中末传。自刑则取冲。"""
        xing_map = {"子": "卯", "卯": "子", "寅": "巳", "巳": "申", "申": "寅",
                    "丑": "戌", "戌": "未", "未": "丑", "辰": "辰", "午": "午",
                    "酉": "酉", "亥": "亥"}
        t = xing_map[z]
        return _chong(z) if t == z else t

    def _shehai(self, shang: str) -> int:
        """涉害深浅：上神自所临地盘，顺数归本位，途中受克之数。"""
        pos = [z for z in ZHI if self.tianpan[z] == shang][0]
        depth, cur = 0, pos
        for _ in range(12):
            cur = _add(cur, 1)
            if _ke(cur, shang) or _ke(shang, cur):
                depth += 1
            if cur == shang:
                break
        return depth

    # ---------- 十二天将 ----------
    def _twelve_generals(self, dt: datetime):
        is_day = 6 <= dt.hour < 18
        gui = GUI_REN[self.day_gan][0 if is_day else 1]
        shun = gui in SHUN_ZHI
        out = {}
        for i, name in enumerate(JIANG12):
            z = _add(gui, i) if shun else _add(gui, -i)
            out[z] = name
        self.gui_ren, self.gui_shun, self.is_day = gui, shun, is_day
        return out

    # ---------- 评分 ----------
    def evaluate(self, rules=None) -> dict:
        from .rules import grade
        rules = rules or self.rules

        def w(k):
            return rules.get(f"liuren.{k}", 0.0)

        gan_wx = ZHI_WUXING[JI_GONG[self.day_gan]]
        items = []
        for label, z in zip(["初传", "中传", "末传"], self.chuan):
            wx = ZHI_WUXING[z]
            if wx == gan_wx:
                d, desc = w("chuan.bihe"), f"{label}{z}（{wx}）与日干比和"
            elif sheng(wx, gan_wx):
                d, desc = w("chuan.sheng_wo"), f"{label}{z}（{wx}）生日干"
            elif sheng(gan_wx, wx):
                d, desc = w("chuan.wo_sheng"), f"{label}{z}（{wx}）为日干所生"
            elif ke(wx, gan_wx):
                d, desc = w("chuan.ke_wo"), f"{label}{z}（{wx}）克日干"
            else:
                d, desc = w("chuan.wo_ke"), f"{label}{z}（{wx}）为日干所克"
            items.append({"desc": desc, "delta": d, "key": f"chuan.{label}"})

        for label, z in zip(["初传", "中传", "末传"], self.chuan):
            j = self.tianjiang.get(z)
            if j in JI_JIANG:
                items.append({"desc": f"{label}乘{j}（吉将）",
                              "delta": w("jiang.ji"), "key": "jiang.ji"})
            elif j in XIONG_JIANG:
                items.append({"desc": f"{label}乘{j}（凶将）",
                              "delta": w("jiang.xiong"), "key": "jiang.xiong"})

        total = sum(i["delta"] for i in items)
        return {"items": items, "score": total,
                "grade": grade(total, rules.get("liuren.thresholds"))}


def render_and_eval(c: LiuRenChart) -> tuple[str, dict]:
    return render(c), c.evaluate()


def render(c: LiuRenChart) -> str:
    from .utils import pad
    p = c.pillars
    out = []
    out.append(f"占时：{c.dt:%Y-%m-%d %H:%M}　四柱 {p.year} {p.month} {p.day} {p.hour}")
    out.append(f"月将：{c.jiang}将{JIANG_NAME[c.jiang]}（{c.zhongqi}后过宫）　"
               f"占时：{c.hour_zhi}时　贵人：{c.gui_ren}（{'昼' if c.is_day else '夜'}贵，"
               f"{'顺' if c.gui_shun else '逆'}行）")
    out.append(f"课体：{c.keti}　—　{c.keti_note}")
    out.append("")

    # 天地盘十二宫（自左向右：巳午未申 / 辰酉 / 卯戌 / 寅丑子亥）
    layout = [["巳", "午", "未", "申"], ["辰", "", "", "酉"],
              ["卯", "", "", "戌"], ["寅", "丑", "子", "亥"]]
    W = 16
    out.append("天地盘（上为天盘，下为地盘；括号内为天将）")
    for row in layout:
        cells = []
        for g in row:
            if not g:
                cells.append(pad("", W))
                continue
            sky = c.tianpan[g]
            j = c.tianjiang.get(sky, "")
            cells.append(pad(f"{sky}{j}", W))
        out.append("│" + "│".join(cells) + "│")
        cells2 = [pad(g if g else "", W) for g in row]
        out.append("│" + "│".join(cells2) + "│")
        out.append(("├" if row is not layout[-1] else "└")
                   + ("┼" if row is not layout[-1] else "┴").join("─" * W for _ in row)
                   + ("┤" if row is not layout[-1] else "┘"))
    out.append("")

    # 四课
    out.append("四课（下为地盘/日干寄宫，上为天盘）")
    names = ["一课", "二课", "三课", "四课"]
    ups = [f"{s}({c.tianjiang.get(s,'')})" for _x, s in c.sike]
    downs = [x for x, _s in c.sike]
    out.append("　" + "".join(pad(n, 14) for n in names))
    out.append("上" + "".join(pad(u, 14) for u in ups))
    out.append("下" + "".join(pad(d, 14) for d in downs))
    out.append("")

    # 三传
    out.append("三传")
    for label, z in zip(["初传", "中传", "末传"], c.chuan):
        out.append(f"  {label}　{z}（{ZHI_WUXING[z]}）　乘{c.tianjiang.get(z, '—')}")
    return "\n".join(out)


def build(dt: datetime, longitude: float = 120.0, tz: float = 8.0, rules=None):
    return LiuRenChart(dt, longitude, tz, rules)

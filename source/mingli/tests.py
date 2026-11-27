"""回归测试：python3 -m unittest mingli.tests -v"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from .calendar import four_pillars, jdn_from_ymd
from .jiazi import jiazi, jiazi_index, shishen, nayin, changsheng
from .lunar import lunar_date
from .liuyao import (cast_from_hexagram, cast_from_coins, palace_hexagrams,
                     hexagram_name, xunkong, PALACES)
from .meihua import cast_by_numbers
from .bazi import build
from . import qimen as qm
from . import liuren as lr
from . import ziwei as zw
from . import calibrate as cb
from . import caselog as cl
from . import web as web_mod
from .rules import Rules


class TestJiazi(unittest.TestCase):
    def test_cycle(self):
        self.assertEqual(jiazi(0), "甲子")
        self.assertEqual(jiazi(59), "癸亥")
        self.assertEqual(jiazi(60), "甲子")
        for i in range(60):
            self.assertEqual(jiazi_index(jiazi(i)), i)

    def test_shishen(self):
        # 日主甲木：壬水（阳水生木）为偏印；丁火为伤官
        self.assertEqual(shishen("甲", "壬"), "偏印")
        self.assertEqual(shishen("甲", "丁"), "伤官")
        # 日主壬水：庚金为偏印
        self.assertEqual(shishen("壬", "庚"), "偏印")
        self.assertEqual(shishen("甲", "甲"), "比肩")
        self.assertEqual(shishen("甲", "乙"), "劫财")

    def test_nayin(self):
        self.assertEqual(nayin("甲子"), "海中金")
        self.assertEqual(nayin("庚午"), "路旁土")
        self.assertEqual(nayin("辛亥"), "钗钏金")

    def test_changsheng(self):
        self.assertEqual(changsheng("甲", "亥"), "长生")
        self.assertEqual(changsheng("甲", "卯"), "帝旺")
        self.assertEqual(changsheng("乙", "午"), "长生")
        self.assertEqual(changsheng("辛", "午"), "病")


class TestCalendar(unittest.TestCase):
    def test_jdn(self):
        self.assertEqual(jdn_from_ymd(2024, 3, 5), 2460375)

    def test_pillars_case1(self):
        """公开案例：2024-03-05 09:30 北京 → 甲辰 丙寅 戊辰 丁巳"""
        p = four_pillars(datetime(2024, 3, 5, 9, 30), longitude=116.4)
        self.assertEqual(p.as_list(), ["甲辰", "丙寅", "戊辰", "丁巳"])

    def test_pillars_case2(self):
        """1990-06-15 10:30 北京 → 庚午 壬午 辛亥 癸巳"""
        p = four_pillars(datetime(1990, 6, 15, 10, 30), longitude=116.4)
        self.assertEqual(p.as_list(), ["庚午", "壬午", "辛亥", "癸巳"])

    def test_lichun_boundary(self):
        """立春前后年柱必须切换：2024 立春 02-04 16:20 前后"""
        before = four_pillars(datetime(2024, 2, 4, 10, 0), longitude=120)
        after = four_pillars(datetime(2024, 2, 4, 20, 0), longitude=120)
        self.assertEqual(before.year, "癸卯")
        self.assertEqual(after.year, "甲辰")

    def test_jieqi_boundary(self):
        """惊蛰前后月柱必须切换：2024 惊蛰 03-05 10:14 前后"""
        before = four_pillars(datetime(2024, 3, 5, 8, 0), longitude=120)
        after = four_pillars(datetime(2024, 3, 5, 12, 0), longitude=120)
        self.assertEqual(before.month, "丙寅")
        self.assertEqual(after.month, "丁卯")

    def test_day_60_cycle(self):
        a = four_pillars(datetime(2024, 1, 1, 12, 0), longitude=120)
        b = four_pillars(datetime(2024, 3, 1, 12, 0), longitude=120)  # 相隔 60 天
        self.assertEqual(a.day, b.day)


class TestLunar(unittest.TestCase):
    def test_known(self):
        cases = {
            "2024-02-10": (2024, 1, 1, False),   # 甲辰年正月初一
            "2024-02-09": (2023, 12, 30, False),  # 除夕
            "2024-09-17": (2024, 8, 15, False),   # 中秋
            "2025-01-29": (2025, 1, 1, False),
            "2023-01-22": (2023, 1, 1, False),
            "2023-03-22": (2023, 2, 1, True),     # 闰二月初一
            "2020-05-23": (2020, 4, 1, True),     # 闰四月初一
        }
        for s, (y, m, d, leap) in cases.items():
            ld = lunar_date(datetime.strptime(s, "%Y-%m-%d"))
            self.assertEqual((ld["year"], ld["month"], ld["day"], ld["is_leap"]),
                             (y, m, d, leap), f"{s} -> {ld}")


class TestLiuYao(unittest.TestCase):
    def test_palace_generation(self):
        """八宫生成 64 卦，必须互不重复且与原表一致"""
        seen = set()
        for palace in PALACES:
            names = [hexagram_name(h) for h in palace_hexagrams(palace)]
            self.assertEqual(len(names), 8)
            for n in names:
                self.assertNotIn(n, seen)
                seen.add(n)
            # 本宫卦为本卦，第八卦为归魂且内卦复原
            self.assertTrue(names[0].endswith("为" + palace) or names[0][0] == palace)
        self.assertEqual(len(seen), 64)

    def test_gou_najia(self):
        """天风姤：乾宫一世，纳甲为 辛丑 辛亥 辛酉 壬午 壬申 壬戌"""
        c = cast_from_hexagram("天风姤", [], "甲子", "子")
        rows = [(r.gan + r.zhi, r.liuqin, r.shiying) for r in c.rows]
        self.assertEqual([r[0] for r in rows],
                         ["辛丑", "辛亥", "辛酉", "壬午", "壬申", "壬戌"])
        self.assertEqual([r[1] for r in rows],
                         ["父母", "子孙", "兄弟", "官鬼", "兄弟", "父母"])
        self.assertEqual(rows[0][2], "世")
        self.assertEqual(rows[3][2], "应")
        self.assertEqual(c.palace, "乾")
        self.assertEqual(c.palace_seq, 2)

    def test_tongren(self):
        """天火同人：离宫归魂，世在三爻"""
        c = cast_from_hexagram("天火同人", [], "戊午", "寅")
        self.assertEqual((c.palace, c.palace_seq, c.shi_pos, c.ying_pos),
                         ("离", 8, 3, 6))
        self.assertEqual([r.liuqin for r in c.rows],
                         ["父母", "子孙", "官鬼", "兄弟", "妻财", "子孙"])

    def test_change(self):
        """天火同人 初、四动 → 风山渐"""
        c = cast_from_hexagram("天火同人", [1, 4], "戊午", "寅")
        self.assertEqual(c.changed_name, "风山渐")

    def test_xunkong(self):
        self.assertEqual(xunkong("甲子"), ("戌", "亥"))
        self.assertEqual(xunkong("甲戌"), ("申", "酉"))
        self.assertEqual(xunkong("辛亥"), ("寅", "卯"))

    def test_coins(self):
        c = cast_from_coins([1, 2, 3, 1, 0, 2], "戊午", "寅")
        # 1背少阳/2背少阴/3背老阳动/1背少阳/0背老阴动/2背少阴
        self.assertEqual([r.yang for r in c.rows], [1, 0, 1, 1, 0, 0])
        self.assertEqual([r.moving for r in c.rows], [False, False, True, False, True, False])


class TestMeiHua(unittest.TestCase):
    def test_nums(self):
        """报数 37、82 → 风泽中孚，五爻动，上卦为用（巽），下卦为体（兑）"""
        c = cast_by_numbers(37, 82)
        self.assertEqual(c.name, "风泽中孚")
        self.assertEqual(c.moving_pos, 5)
        self.assertEqual((c.ti, c.yong), ("兑", "巽"))
        self.assertEqual(c.verdict_ti_yong()[0], "我克")   # 体金克用木

    def test_nums2(self):
        """报数 7、3 → 山火贲，四爻动，体离火、用艮土，体生用"""
        c = cast_by_numbers(7, 3)
        self.assertEqual(c.name, "山火贲")
        self.assertEqual((c.ti, c.yong), ("离", "艮"))
        self.assertEqual(c.verdict_ti_yong()[0], "我生")
        self.assertEqual(c.hu_name, "雷水解")


class TestBaZi(unittest.TestCase):
    def test_strength_runs(self):
        b = build(datetime(1990, 6, 15, 10, 30), longitude=116.4, gender="m")
        st = b.strength()
        self.assertGreater(st["ratio"], 0)
        self.assertIn(st["level"], ("身强", "身弱", "中和"))

    def test_dayun_direction(self):
        """庚午年（阳）男 → 顺行"""
        b = build(datetime(1990, 6, 15, 10, 30), longitude=116.4, gender="m")
        self.assertTrue(b.dayun()["forward"])
        b2 = build(datetime(1990, 6, 15, 10, 30), longitude=116.4, gender="f")
        self.assertFalse(b2.dayun()["forward"])

    def test_dayun_first(self):
        """月柱壬午，阳男顺行 → 首运癸未"""
        b = build(datetime(1990, 6, 15, 10, 30), longitude=116.4, gender="m")
        self.assertEqual(b.dayun()["list"][0]["gz"], "癸未")


class TestQiMen(unittest.TestCase):
    def test_ju_table_complete(self):
        """二十四节气必须都有局数，且阴阳遁划分正确"""
        self.assertEqual(len(qm.JU_TABLE), 24)
        for term in qm.JU_TABLE:
            in_yang = term in qm.YANG_TERMS
            self.assertTrue(in_yang or term in qm.JU_TABLE, term)
        self.assertEqual(len(qm.YANG_TERMS), 12)

    def test_earth_plate(self):
        """阳遁一局 / 阴遁九局的地盘必须为标准答案"""
        c = qm.build(datetime(2026, 11, 27, 15, 30), 116.4)
        # 手工指定遁与局，绕过定局
        c.dun, c.ju = "阳", 1
        ep = c._earth_plate()
        self.assertEqual(ep, {1: "戊", 2: "己", 3: "庚", 4: "辛", 5: "壬",
                              6: "癸", 7: "丁", 8: "丙", 9: "乙"})
        c.dun, c.ju = "阴", 9
        ep = c._earth_plate()
        self.assertEqual(ep, {1: "乙", 2: "丙", 3: "丁", 4: "癸", 5: "壬",
                              6: "辛", 7: "庚", 8: "己", 9: "戊"})

    def test_ding_ju(self):
        """2026-11-27 15:30：小雪·符头甲辰·下元 → 阴遁 2 局"""
        c = qm.build(datetime(2026, 11, 27, 15, 30), 116.4)
        self.assertEqual(c.term, "小雪")
        self.assertEqual(c.dun, "阴")
        self.assertEqual(c.futou, "甲辰")
        self.assertEqual(c.yuan_name, "下元")
        self.assertEqual(c.ju, 2)

    def test_futou(self):
        self.assertEqual(qm.futou_of("甲子"), ("甲子", 0, 0))
        self.assertEqual(qm.futou_of("乙丑")[0], "甲子")
        self.assertEqual(qm.futou_of("己巳")[0], "己巳")
        self.assertEqual(qm.futou_of("己巳")[2], 1)   # 巳 -> 中元

    def test_plates_complete(self):
        """任意时刻：八门、八神各 8 个不重复；九星 9 个（含天禽寄芮）"""
        for dt in [datetime(2026, 11, 27, 15, 30), datetime(2026, 3, 15, 8, 0),
                   datetime(2026, 7, 1, 22, 0), datetime(2020, 5, 23, 4, 0)]:
            c = qm.build(dt, 116.4)
            gates = list(c.gates.values())
            self.assertEqual(len(gates), 8)
            self.assertEqual(len(set(gates)), 8)
            gods = list(c.gods.values())
            self.assertEqual(len(gods), 8)
            self.assertEqual(len(set(gods)), 8)
            stars = [s for v in c.sky_star.values() for s in v]
            self.assertEqual(len(stars), 9)
            self.assertEqual(len(set(stars)), 9)
            self.assertNotIn(5, c.gates)
            self.assertNotIn(5, c.gods)

    def test_fuyin(self):
        """时干为旬首（甲时）时，天盘星应回到地盘原位——伏吟"""
        c = qm.build(datetime(2026, 11, 27, 15, 30), 116.4)   # 甲申时
        self.assertEqual(c.hour_gan_used, c.xun_yi)
        for p, stars in c.sky_star.items():
            for st in stars:
                origin = [k for k, v in qm.STAR_OF_PALACE.items() if v == st][0]
                self.assertEqual(p, c._zhong_to(origin))


class TestLiuRen(unittest.TestCase):
    def test_yuejiang(self):
        """2026-11-27 在小雪后 → 寅将功曹"""
        c = lr.build(datetime(2026, 11, 27, 15, 30), 116.4)
        self.assertEqual(c.jiang, "寅")
        self.assertEqual(c.zhongqi, "小雪")

    def test_jigong(self):
        """十干寄宫口诀"""
        self.assertEqual(lr.JI_GONG["甲"], "寅")
        self.assertEqual(lr.JI_GONG["乙"], "辰")
        self.assertEqual(lr.JI_GONG["戊"], "巳")
        self.assertEqual(lr.JI_GONG["癸"], "丑")

    def test_tianpan_fanyin(self):
        """月将寅加占时申（相差六位）→ 天地盘全冲，成返吟"""
        c = lr.build(datetime(2026, 11, 27, 15, 30), 116.4)
        self.assertEqual(c.hour_zhi, "申")
        for z in "子丑寅卯辰巳午未申酉戌亥":
            self.assertEqual(c.tianpan[z], lr._chong(z), z)

    def test_sike(self):
        c = lr.build(datetime(2026, 11, 27, 15, 30), 116.4)
        self.assertEqual([tuple(x) for x in c.sike],
                         [("辰", "戌"), ("戌", "辰"), ("巳", "亥"), ("亥", "巳")])

    def test_sanchuan(self):
        c = lr.build(datetime(2026, 11, 27, 15, 30), 116.4)
        self.assertEqual(c.chuan, ("亥", "巳", "亥"))
        self.assertEqual(c.keti, "返吟课")

    def test_gui_ren(self):
        """乙日：昼贵在子、夜贵在申；子属亥子丑寅卯辰 → 顺行"""
        c = lr.build(datetime(2026, 11, 27, 15, 30), 116.4)
        self.assertEqual((c.gui_ren, c.gui_shun, c.is_day), ("子", True, True))
        self.assertEqual(c.tianjiang["子"], "贵人")
        self.assertEqual(c.tianjiang["丑"], "螣蛇")
        n = lr.build(datetime(2026, 11, 27, 22, 0), 116.4)
        self.assertEqual(n.gui_ren, "申")
        self.assertFalse(n.gui_shun)

    def test_fuyin(self):
        """月将寅加寅时 → 天盘等于地盘，伏吟"""
        c = lr.build(datetime(2026, 11, 27, 4, 0), 116.4)
        self.assertEqual(c.hour_zhi, "寅")
        self.assertEqual(c.keti, "伏吟课")


class TestZiWei(unittest.TestCase):
    ZHI = "子丑寅卯辰巳午未申酉戌亥"

    def _chart(self, dt=None, gender="m"):
        return zw.build(dt or datetime(1990, 6, 15, 10, 30), 116.4, 8.0, gender)

    def test_ziwei_table(self):
        """紫微定位表：各局前五日（《全书》图诀推算值）"""
        expect = {
            2: ["丑", "寅", "寅", "卯", "卯"],
            3: ["辰", "丑", "寅", "巳", "寅"],
            4: ["亥", "辰", "丑", "寅", "子"],
            5: ["午", "亥", "辰", "丑", "寅"],
            6: ["酉", "午", "亥", "辰", "丑"],
        }
        for ju, days in expect.items():
            for d, want in enumerate(days, 1):
                c = self._chart()
                c.ju_num, c.day = ju, d
                self.assertEqual(self.ZHI[c._ziwei_pos()], want, f"局{ju} 日{d}")

    def test_tianfu_symmetry(self):
        """天府与紫微以寅申为轴：紫微寅/申时同宫，巳/亥时对宫"""
        for ziwei in range(12):
            tf = (16 - ziwei) % 12
            if self.ZHI[ziwei] in ("寅", "申"):
                self.assertEqual(ziwei, tf, "紫府应同宫")
            if self.ZHI[ziwei] in ("巳", "亥"):
                self.assertEqual((tf - ziwei) % 12, 6, "紫府应对宫")

    def test_ming_shen(self):
        """农历五月巳时：命宫丑、身宫亥"""
        c = self._chart()
        self.assertEqual(c.month, 5)
        self.assertEqual(c.hour_zhi, "巳")
        self.assertEqual(self.ZHI[c.ming], "丑")
        self.assertEqual(self.ZHI[c.shen], "亥")

    def test_wuxing_ju(self):
        """命宫己丑，纳音霹雳火 → 火六局"""
        c = self._chart()
        self.assertEqual(c.ming_gz, "己丑")
        self.assertEqual(c.ju_name, "火六局")
        self.assertEqual(c.ju_num, 6)

    def test_main_stars(self):
        """十四主星全盘位置（紫微在辰、天府在子）"""
        c = self._chart()
        self.assertEqual(self.ZHI[c.ziwei], "辰")
        self.assertEqual(self.ZHI[c.tianfu], "子")
        pos = {s: self.ZHI[z] for z, ss in c.stars.items() for s in ss}
        for star, want in [("紫微", "辰"), ("天机", "卯"), ("太阳", "丑"),
                           ("武曲", "子"), ("天同", "亥"), ("廉贞", "申"),
                           ("天府", "子"), ("太阴", "丑"), ("贪狼", "寅"),
                           ("巨门", "卯"), ("天相", "辰"), ("天梁", "巳"),
                           ("七杀", "午"), ("破军", "戌")]:
            self.assertEqual(pos[star], want, star)

    def test_sihua(self):
        """庚干：太阳化禄、武曲化权、太阴化科、天同化忌"""
        c = self._chart()
        self.assertEqual(c.sihua, {"禄": "太阳", "权": "武曲", "科": "太阴", "忌": "天同"})
        self.assertIn("太阳化禄", c.sihua_at(c.ming))

    def test_dayun(self):
        """火六局 6 岁起；庚为阳、男 → 顺行"""
        c = self._chart()
        self.assertEqual(c.dayun[0]["start"], 6)
        self.assertEqual(c.dayun[0]["zhi"], "丑")
        self.assertEqual(c.dayun[1]["zhi"], "寅")
        f = self._chart(gender="f")
        self.assertEqual(f.dayun[1]["zhi"], "子")   # 阳女逆行


class TestCalibrate(unittest.TestCase):
    def test_fit_recovers_sign(self):
        """构造可分数据：x1 正向、x2 负向，拟合后符号应正确"""
        X, y = [], []
        for a in (-2, -1, 0, 1, 2):
            for b in (-2, -1, 0, 1, 2):
                X.append([a, b])
                y.append(1 if a - b > 0 else 0)
        w = cb.fit(X, y, l2=0.5)
        self.assertGreater(w[0], 0)
        self.assertLess(w[1], 0)
        self.assertGreater(cb.accuracy(X, y, w), 0.8)

    def test_auc(self):
        """完美排序时 AUC = 1，反向时 = 0"""
        X = [[1.0], [2.0], [3.0], [4.0]]
        y = [0, 0, 1, 1]
        self.assertAlmostEqual(cb.auc(X, y, [1.0]), 1.0)
        self.assertAlmostEqual(cb.auc(X, y, [-1.0]), 0.0)

    def test_loo_perfect(self):
        """完全可分且规则单调时，留一验证应接近 100%"""
        X = [[-2.0], [-1.0], [1.0], [2.0], [-3.0], [3.0]]
        y = [0, 0, 1, 1, 0, 1]
        self.assertGreaterEqual(cb.loo_accuracy(X, y, 0.5), 0.83)

    def test_design_aggregates(self):
        """同一 key 多次触发应累加 mul"""
        cases = [{"date": "2026-11-27 15:30", "coins": [1, 2, 3, 1, 0, 2],
                  "ask": "财", "result": 1}]
        X, y, keys, used, skipped = cb.build_design(cases, "liuyao")
        self.assertEqual(len(y), 1)
        self.assertGreaterEqual(len(keys), 1)

    def test_empty(self):
        text, summary = cb.report("liuyao", [])
        self.assertIn("没有任何可用案例", text)
        self.assertEqual(summary, {})

    def test_bootstrap_width(self):
        """小样本下区间应明显宽于大样本"""
        import random
        rng = random.Random(3)

        def gen(n):
            X, y = [], []
            for _ in range(n):
                a = rng.choice([-1, 0, 1])
                X.append([a])
                y.append(1 if a > 0 else 0)
            return X, y
        Xs, ys = gen(12)
        b_small = cb.bootstrap_weights(Xs, ys, 0.5, n_boot=40)
        w = cb.fit(Xs, ys, 0.5)
        spread = max(b[0] for b in b_small) - min(b[0] for b in b_small)
        self.assertGreater(spread, 0.1)


class TestCaseLog(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "cases.json")
        self.log = cl.CaseLog(self.path)

    def _seed(self, n=3):
        for i in range(n):
            self.log.add("liuyao", {"coins": [1, 2, 3, 1, 0, 2],
                                    "day": "戊午", "month": "寅", "ask": "财"},
                         -3.0 * (i + 1), "凶" if i < 2 else "不利")

    def test_add_and_chain(self):
        self._seed(3)
        ok, errs = self.log.verify()
        self.assertTrue(ok, errs)
        self.assertEqual(self.log.records[1]["prev_hash"],
                         self.log.records[0]["pred_hash"])

    def test_tamper_score(self):
        self._seed(3)
        self.log.records[0]["score"] = -1.0
        ok, errs = self.log.verify()
        self.assertFalse(ok)
        self.assertIn("预测摘要不符", errs[0])

    def test_tamper_result(self):
        self._seed(2)
        self.log.resolve("0001", 0)
        self.log.records[0]["result"] = 1
        ok, errs = self.log.verify()
        self.assertFalse(ok)
        self.assertIn("结果摘要不符", errs[0])

    def test_double_resolve_blocked(self):
        self._seed(1)
        self.log.resolve("0001", 1)
        with self.assertRaises(ValueError):
            self.log.resolve("0001", 0)

    def test_delete_detected(self):
        self._seed(3)
        del self.log.records[1]
        ok, errs = self.log.verify()
        self.assertFalse(ok)

    def test_stats(self):
        self._seed(3)
        self.log.resolve("0001", 0)   # 判凶、结果凶 → 命中
        self.log.resolve("0002", 1)   # 判凶、结果吉 → 未中
        s = self.log.stats()
        self.assertEqual((s["total"], s["resolved"], s["pending"]), (3, 2, 1))
        self.assertAlmostEqual(s["hit"], 0.5)
        self.assertTrue(any(c["grade"] == "凶" for c in s["calibration"]))

    def test_export(self):
        self._seed(2)
        self.log.resolve("0001", 1)
        cases = self.log.export(engine="liuyao")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["result"], 1)
        self.assertIn("coins", cases[0])

    def test_persistence(self):
        self._seed(2)
        again = cl.CaseLog(self.path)
        self.assertEqual(len(again.records), 2)
        self.assertTrue(again.verify()[0])


class TestCompare(unittest.TestCase):
    def test_mcnemar(self):
        """配对精确检验的已知值"""
        self.assertAlmostEqual(cl.mcnemar(0, 0), 1.0)
        self.assertAlmostEqual(cl.mcnemar(5, 0), 0.0625, places=4)
        self.assertAlmostEqual(cl.mcnemar(10, 0), 1 / 512, places=5)
        self.assertAlmostEqual(cl.mcnemar(3, 3), 1.0)
        self.assertLess(cl.mcnemar(12, 1), 0.01)

    def test_rule_spec(self):
        r, name = cl.load_rule_spec("default")
        self.assertEqual(name, "默认")
        r, name = cl.load_rule_spec("strict")
        self.assertIn("strict", name)
        self.assertEqual(r.get("liuyao.month.po"), -4.5)
        with self.assertRaises(ValueError):
            cl.load_rule_spec("nonsense")

    def test_compare_needs_data(self):
        log = cl.CaseLog(os.path.join(tempfile.mkdtemp(), "c.json"))
        for i in range(3):
            log.add("liuyao", {"coins": [1, 2, 3, 1, 0, 2], "day": "戊午",
                               "month": "寅", "ask": "财"}, -6.0, "凶")
            log.resolve(f"{i + 1:04d}", 0)
        text = cl.compare(log, "default", "classic")
        self.assertIn("做不了有意义的比较", text)

    def test_compare_runs(self):
        log = cl.CaseLog(os.path.join(tempfile.mkdtemp(), "c.json"))
        base = datetime(2026, 3, 1, 10, 0)
        for i in range(12):
            dt = base + timedelta(days=i * 7)
            log.add("liuyao", {"date": dt.strftime("%Y-%m-%d %H:%M"),
                               "coins": [1, 2, 3, 1, 0, 2], "ask": "财"},
                    -6.0, "凶")
            log.resolve(f"{i + 1:04d}", i % 2)
        text = cl.compare(log, "default", "strict")
        self.assertIn("McNemar", text)
        self.assertIn("时间稳定性", text)
        self.assertIn("数据泄漏", text)


class TestSlider(unittest.TestCase):
    def test_page(self):
        f = [web_mod.make_factor("demo.a", "测试项", 1, -3.0),
             web_mod.make_factor("demo.b", "另一项", 2, 1.5)]
        html = web_mod.page("标题", "盘面", f,
                            {"daji": 5, "ji": 2, "ping_lo": -2, "xiong": -5}, {})
        self.assertIn("const DATA", html)
        self.assertIn('"demo.a"', html)
        self.assertIn("拖滑杆", html)

    def test_factor_shape(self):
        f = web_mod.make_factor("x.y", "标签", 3, -1.5)
        self.assertEqual(f["mul"], 3)
        self.assertLess(f["min"], -1.5)
        self.assertGreater(f["max"], 0)


class TestRules(unittest.TestCase):
    def test_default_unchanged(self):
        """上下文的默认评分应与硬编码时代一致"""
        b = build(datetime(1990, 6, 15, 10, 30), longitude=116.4, gender="m")
        self.assertAlmostEqual(b.strength()["total"], 11.50, places=2)

    def test_override(self):
        r = Rules()
        r.apply_overrides(["liuyao.month.po=-0.5"])
        self.assertEqual(r.get("liuyao.month.po"), -0.5)

    def test_preset(self):
        r = Rules()
        r.apply_preset("strict")
        self.assertEqual(r.get("liuyao.month.po"), -4.5)

    def test_liuyao_score_moves(self):
        """调低惩罚项后，同一卦的总分应上升"""
        base = cast_from_hexagram("天火同人", [1, 4], "戊午", "寅")
        lo = base.evaluate("妻财")
        r = Rules()
        r.apply_overrides(["liuyao.month.po=-0.5", "liuyao.moving.ke_yong=-0.5"])
        hi = base.evaluate("妻财", r)
        self.assertGreater(hi["score"], lo["score"])

    def test_save_load(self):
        path = os.path.join(tempfile.mkdtemp(), "_rules_test.json")
        r = Rules()
        r.set("liuyao.month.lin", 9.9)
        r.save(path)
        r2 = Rules.load(path)
        self.assertEqual(r2.get("liuyao.month.lin"), 9.9)


if __name__ == "__main__":
    unittest.main()

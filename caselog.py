"""案例录入工具：先锁定预测，后回填结果。

为什么这样设计
--------------
命理最容易犯的错不是算错，是**事后归因**——事情发生了，回头找一个卦来套，
怎么说都对。要检验这套系统，唯一干净的办法是「预注册」：

  1. 录入盘面 → 程序自己算分、给判词 → 立即写盘并加哈希（此时结果未知）
  2. 事件发生
  3. 回填结果 → 再算第二段哈希
  4. 任何事后改动预测的行为，都会让哈希链对不上

哈希链
------
每条记录含两个摘要：
  pred_hash  = H(id, engine, input, score, grade, predicted_at, prev_hash)
  final_hash = H(pred_hash, result, result_at)
改预测 → pred_hash 变 → 与后继记录的 prev_hash 断链；
改结果 → final_hash 变。
verify() 会重算全链，指出第一条出问题的记录。

边界
----
· 这是本地自证，不是第三方公证。改数据库的人可以重算整条链。
  它的作用对象是「三个月后的你自己」，不是法庭。
· 记录只存你录入的东西。舍弃的案例不会自动留痕，所以 stats 会显示
  「待决案例」的占比——长期只解决顺手的那部分，这个比例会露馅。
"""
import hashlib
import json
import os
from datetime import datetime

SCHEMA = 1
GRADE_ORDER = ["凶", "不利", "平／待定", "吉", "大吉"]


def _digest(payload: dict) -> str:
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class CaseLog:
    def __init__(self, path: str = "output/cases.json"):
        self.path = path
        self.records: list[dict] = []
        if os.path.exists(path):
            self.load()

    # ---------- 存取 ----------
    def load(self):
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            self.records = data
        else:
            self.records = data.get("records", [])

    def save(self):
        d = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(d, exist_ok=True)
        payload = {"schema": SCHEMA, "saved_at": _now(), "records": self.records}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)          # 原子写入，避免写一半损坏

    # ---------- 哈希 ----------
    def _pred_digest(self, rec: dict, prev_hash: str) -> str:
        return _digest({
            "id": rec["id"], "engine": rec["engine"], "input": rec["input"],
            "score": round(float(rec["score"]), 6), "grade": rec["grade"],
            "predicted_at": rec["predicted_at"], "prev": prev_hash,
        })

    @staticmethod
    def _final_digest(rec: dict) -> str:
        return _digest({"pred": rec["pred_hash"], "result": rec["result"],
                        "result_at": rec["result_at"]})

    # ---------- 写入 ----------
    def add(self, engine: str, input_data: dict, score: float, grade: str,
            ask: str = "", note: str = "") -> dict:
        """锁入一次预测。score/grade 必须由程序算出，不接受人工指定。"""
        rid = f"{len(self.records) + 1:04d}"
        prev = self.records[-1]["pred_hash"] if self.records else "GENESIS"
        rec = {
            "id": rid, "engine": engine, "input": input_data, "ask": ask,
            "score": round(float(score), 6), "grade": grade,
            "predicted_at": _now(), "prev_hash": prev,
            "note": note, "result": None, "result_at": None,
            "result_note": "",
        }
        rec["pred_hash"] = self._pred_digest(rec, prev)
        self.records.append(rec)
        self.save()
        return rec

    def resolve(self, rid: str, result: int, note: str = "") -> dict:
        rec = self._find(rid)
        if rec["result"] is not None:
            raise ValueError(f"记录 {rid} 已有结果，不允许覆盖（这正是防作弊的意义）")
        rec["result"] = 1 if result else 0
        rec["result_at"] = _now()
        rec["result_note"] = note
        rec["final_hash"] = self._final_digest(rec)
        self.save()
        return rec

    def _find(self, rid: str) -> dict:
        for r in self.records:
            if r["id"] == rid:
                return r
        raise KeyError(f"找不到记录 {rid}")

    # ---------- 校验 ----------
    def verify(self) -> tuple[bool, list[str]]:
        errs = []
        prev = "GENESIS"
        for i, r in enumerate(self.records):
            expect = self._pred_digest(r, prev)
            if r.get("pred_hash") != expect:
                errs.append(f"{r['id']}：预测摘要不符（内容被改过，或哈希链断裂）")
            if r.get("prev_hash") != prev:
                errs.append(f"{r['id']}：前驱哈希不符（中间有记录被删或重排）")
            if r.get("result") is not None:
                if r.get("final_hash") != self._final_digest(r):
                    errs.append(f"{r['id']}：结果摘要不符（结果被改过）")
            prev = r.get("pred_hash", "")
        return (not errs), errs

    # ---------- 查询 ----------
    def listing(self, pending: bool | None = None, engine: str | None = None):
        out = self.records
        if pending is True:
            out = [r for r in out if r["result"] is None]
        elif pending is False:
            out = [r for r in out if r["result"] is not None]
        if engine:
            out = [r for r in out if r["engine"] == engine]
        return out

    # ---------- 统计 ----------
    def stats(self) -> dict:
        total = len(self.records)
        done = [r for r in self.records if r["result"] is not None]
        pend = total - len(done)
        res = {"total": total, "resolved": len(done), "pending": pend,
               "by_engine": {}, "calibration": [], "hit": 0.0, "base": 0.0}
        if not done:
            return res

        # 判词方向：吉类判为 1，凶类判为 0
        def dirn(g):
            return 1 if g in ("吉", "大吉") else (0 if g in ("凶", "不利") else None)

        hit = sum(1 for r in done if dirn(r["grade"]) == r["result"])
        res["hit"] = hit / len(done)
        pos = sum(r["result"] for r in done)
        res["base"] = max(pos, len(done) - pos) / len(done)

        for r in done:
            e = res["by_engine"].setdefault(r["engine"], {"n": 0, "hit": 0})
            e["n"] += 1
            if dirn(r["grade"]) == r["result"]:
                e["hit"] += 1

        # 校准曲线：同一判词下的实际吉率
        for g in GRADE_ORDER:
            grp = [r for r in done if r["grade"] == g]
            if grp:
                rate = sum(r["result"] for r in grp) / len(grp)
                res["calibration"].append({"grade": g, "n": len(grp), "rate": rate})
        return res

    # ---------- 导出 ----------
    def export(self, engine: str | None = None, only_resolved: bool = True):
        recs = self.listing(pending=False if only_resolved else None, engine=engine)
        cases = []
        for r in recs:
            c = dict(r["input"])
            c["result"] = r["result"]
            if r.get("ask"):
                c["ask"] = r["ask"]
            cases.append(c)
        return cases


# ---------------- 报告 ----------------
def render_stats(log: CaseLog) -> str:
    from .utils import pad
    s = log.stats()
    out = []
    out.append(f"记录库：{log.path}　共 {s['total']} 条"
               f"（已决 {s['resolved']}／待决 {s['pending']}）")
    if s["total"] >= 5 and s["pending"] / s["total"] >= 0.3:
        out.append(f"  ⚠ 待决占 {s['pending'] / s['total']:.0%}——"
                   f"若长期只回填顺手的那部分，下面的准确率就是挑出来的，不是真的。")
    out.append("")
    if not s["resolved"]:
        out.append("还没有已决案例。等事件落定后用：log resolve <id> --result 1|0")
        return "\n".join(out)

    out.append(f"方向命中率　{s['hit']:.0%}　（只看判「吉/大吉」与「凶/不利」的记录）")
    out.append(f"基线（全猜多数类）{s['base']:.0%}")
    import math
    n = s["resolved"]
    se = math.sqrt(max(s["hit"] * (1 - s["hit"]), 1e-9) / n)
    lo, hi = s["hit"] - 1.96 * se, s["hit"] + 1.96 * se
    out.append(f"95% 区间　　[{lo:.0%}, {hi:.0%}]"
               + ("　← 跨过基线，尚不能说明有效" if lo <= s["base"] else "　← 高于基线"))
    out.append("")

    out.append("分引擎：")
    out.append("  " + pad("引擎", 12) + pad("案例", 8) + "命中率")
    for e, v in sorted(s["by_engine"].items()):
        out.append("  " + pad(e, 12) + pad(v["n"], 8) + f"{v['hit'] / v['n']:.0%}")
    out.append("")

    out.append("校准曲线（同一判词下的实际吉率，越单调越说明分数有意义）：")
    out.append("  " + pad("判词", 12) + pad("案例", 8) + pad("实际吉率", 10) + "图示")
    for row in s["calibration"]:
        bar = "█" * int(round(row["rate"] * 20))
        out.append("  " + pad(row["grade"], 12) + pad(row["n"], 8)
                   + pad(f"{row['rate']:.0%}", 10) + bar)
    mono = [r["rate"] for r in s["calibration"]]
    if len(mono) >= 3 and any(mono[i] > mono[i + 1] for i in range(len(mono) - 1)):
        out.append("  ⚠ 单调性被打破——某个「更凶」的判词，实际吉率反而更高。")
    out.append("")
    out.append("下一步：")
    out.append(f"  log export --engine {list(s['by_engine'])[0] if s['by_engine'] else 'liuyao'}"
               f" --out cases.json　导出给校准工具")
    out.append("  log compare --b classic　在同一批案例上比较两套权重")
    return "\n".join(out)


def render_list(log: CaseLog, rows: list[dict]) -> str:
    from .utils import pad
    if not rows:
        return "（没有记录）"
    out = [pad("ID", 6) + pad("时间", 20) + pad("引擎", 9) + pad("事由", 6)
           + pad("分数", 8) + pad("判词", 10) + "结果"]
    for r in rows:
        res = "待决" if r["result"] is None else ("吉" if r["result"] else "凶")
        out.append(pad(r["id"], 6) + pad(r["predicted_at"], 20)
                   + pad(r["engine"], 9) + pad(r.get("ask", ""), 6)
                   + pad(f"{r['score']:+.1f}", 8) + pad(r["grade"], 10) + res)
    return "\n".join(out)


# ---------------- 规则集比较 ----------------
def load_rule_spec(spec: str):
    """把 'default' / 预设名 / '@文件.json' 解析成 Rules。"""
    from .rules import Rules, PRESETS
    if spec in (None, "", "default"):
        return Rules(), "默认"
    if spec in PRESETS:
        r = Rules()
        r.apply_preset(spec)
        return r, f"预设 {spec}"
    if spec.startswith("@"):
        path = spec[1:]
        return Rules.load(path), f"文件 {os.path.basename(path)}"
    raise ValueError(f"无法识别的规则集：{spec}（可用 default / "
                     f"{'/'.join(PRESETS)} / @rules.json）")


def score_case(engine: str, case: dict, rules, lng=120.0, tz=8.0):
    """用给定规则重算一个案例的分数与判词。"""
    from .calibrate import factors_of
    from .rules import grade as _grade
    fac = factors_of(engine, case, lng, tz)
    total = sum(mul * rules.get(key, 0.0) for key, mul in fac.items())
    th = rules.get(f"{engine}.thresholds")
    if not th:
        th = rules.get("liuyao.thresholds")
    return total, _grade(total, th)


def _dirn(g: str):
    return 1 if g in ("吉", "大吉") else (0 if g in ("凶", "不利") else None)


def _hit(grade_str: str, result: int):
    d = _dirn(grade_str)
    return None if d is None else int(d == result)


def mcnemar(b: int, c: int) -> float:
    """配对二项精确检验：b、c 为两套规则判断不一致的两个方向的计数。"""
    from math import comb
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(comb(n, i) for i in range(k + 1)) / (2 ** n) * 2
    return min(p, 1.0)


def compare(log: "CaseLog", spec_a: str, spec_b: str, lng=120.0, tz=8.0,
            segments: int = 2) -> str:
    import math
    from .utils import pad

    ra, name_a = load_rule_spec(spec_a)
    rb, name_b = load_rule_spec(spec_b)

    done = [r for r in log.records if r["result"] is not None]
    if len(done) < 6:
        return (f"已决案例只有 {len(done)} 条，做不了有意义的比较（至少 6 条，"
                f"最好 30 条以上）。")

    rows, skipped = [], 0
    for r in done:
        case = dict(r["input"])
        if r.get("ask"):
            case["ask"] = r["ask"]
        try:
            sa, ga = score_case(r["engine"], case, ra, lng, tz)
            sb, gb = score_case(r["engine"], case, rb, lng, tz)
        except Exception:
            skipped += 1
            continue
        ha, hb = _hit(ga, r["result"]), _hit(gb, r["result"])
        rows.append({"r": r, "ga": ga, "gb": gb, "ha": ha, "hb": hb})

    if not rows:
        return "没有任何案例能被两套规则同时重放（检查引擎与 input 字段是否匹配）。"

    out = []
    out.append(f"记录库：{log.path}")
    out.append(f"已决案例 {len(done)} 条，可重放 {len(rows)} 条"
               + (f"，跳过 {skipped} 条" if skipped else ""))
    out.append("")

    def summarize(key_g, key_h, label):
        hs = [x[key_h] for x in rows if x[key_h] is not None]
        n = len(hs)
        acc = sum(hs) / n if n else 0.0
        se = math.sqrt(max(acc * (1 - acc), 1e-9) / n) if n else 0.0
        return {"label": label, "n": n, "acc": acc,
                "lo": max(0.0, acc - 1.96 * se), "hi": min(1.0, acc + 1.96 * se)}

    A = summarize("ga", "ha", name_a)
    B = summarize("gb", "hb", name_b)
    out.append("  " + pad("规则集", 26) + pad("可判案例", 10) + pad("命中率", 9) + "95% 区间")
    for s_ in (A, B):
        label = s_["label"] if len(s_["label"]) <= 24 else s_["label"][:23] + "…"
        out.append("  " + pad(label, 26) + pad(s_["n"], 10)
                   + pad(f"{s_['acc']:.0%}", 9) + f"[{s_['lo']:.0%}, {s_['hi']:.0%}]")
    out.append("  （判「平／待定」的不计入命中率，所以两套规则的可判条数可能不同）")
    out.append("")

    both = [x for x in rows if x["ha"] is not None and x["hb"] is not None]
    b = sum(1 for x in both if x["ha"] == 1 and x["hb"] == 0)
    c = sum(1 for x in both if x["ha"] == 0 and x["hb"] == 1)
    out.append(f"配对比较（{len(both)} 条两套规则都能判的案例）：")
    out.append(f"  只有 A 对：{b} 条　　只有 B 对：{c} 条　　两边都对："
               f"{sum(1 for x in both if x['ha'] == 1 and x['hb'] == 1)} 条　　"
               f"两边都错：{sum(1 for x in both if x['ha'] == 0 and x['hb'] == 0)} 条")
    p = mcnemar(b, c)
    verdict = ("差异显著" if p < 0.05 else "差异不显著")
    out.append(f"  McNemar 精确检验 p = {p:.3f}　→　{verdict}")
    if p >= 0.05:
        out.append("  换句话说：这批数据分辨不出哪套权重更好。要裁判，得加样本。")
    out.append("")

    # 时间分段稳定性
    if segments >= 2 and len(rows) >= 2 * segments:
        out.append("时间稳定性（按录入时间排序后等分，看命中率是否漂移）：")
        size = len(rows) // segments
        for s_i in range(segments):
            chunk = rows[s_i * size:(s_i + 1) * size] if s_i < segments - 1 \
                else rows[s_i * size:]
            for tag, kh in (("A", "ha"), ("B", "hb")):
                hs = [x[kh] for x in chunk if x[kh] is not None]
                if hs:
                    rng = (f"{chunk[0]['r']['predicted_at'][:10]} ~ "
                           f"{chunk[-1]['r']['predicted_at'][:10]}")
                    out.append(f"  第{s_i + 1}段 {rng}　{tag} 命中 {sum(hs) / len(hs):.0%}"
                               f"（n={len(hs)}）")
        out.append("  若前后段差距很大，说明结论被某一段的运气带着走。")
        out.append("")

    out.append("⚠ 公平比较的前提：两套规则都不能是从这批案例校准出来的。")
    out.append("  用同一批数据调参再比较，等于让考生自己出题——那叫数据泄漏，不叫验证。")
    return "\n".join(out)

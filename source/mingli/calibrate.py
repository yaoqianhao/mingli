"""权重校准工具。

它做一件传统术数自己做不到的事：把「权重」当成待估参数，用一批已知结果的
案例反推它们的值，并且**如实报告这些估计有多不可靠**。

模型
----
    score_i = Σ_j x_ij · w_j         x_ij = 第 i 案第 j 个因子被触发的次数/份额
    P(吉)   = sigmoid(score_i)        预测：score > 0 判吉

用带 L2 正则的逻辑回归（IRLS / 牛顿法）求解。正则项压住小样本下的过拟合。

为什么必须报告不确定性
----------------------
N 个案例、k 个权重，若 N < 5k，估计出的 w 基本是噪声的拟合结果。
任何只给一张「校准后权重表」而不给区间与交叉验证的工具，都在骗人。
本模块的输出里，交叉验证准确率、基线、bootstrap 区间、样本/特征比
是必出的四项，缺一不可。
"""
import json
import math
import random
from datetime import datetime

from .jiazi import GAN, ZHI

# ---------------- 案例格式 ----------------
# {
#   "engine": "liuyao",
#   "cases": [
#     {"date": "2026-01-01 10:00", "coins": [1,2,3,1,0,2], "ask": "财", "result": 1},
#     {"hexagram": "天火同人", "moves": [1,4], "day": "戊午", "month": "寅",
#      "ask": "财", "result": 0}
#   ]
# }
# result: 1 = 吉 / 0 = 凶（或 true/false）。引擎内其余参数同命令行。

# 问事简称 -> 六亲
ASK_MAP = {"财": "妻财", "求财": "妻财", "官": "官鬼", "工作": "官鬼",
           "父": "父母", "文书": "父母", "子": "子孙", "子女": "子孙",
           "兄": "兄弟", "朋友": "兄弟"}


def _parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"时间格式无法识别：{s}")


def _agg(pairs) -> dict:
    """把 [(key, mul)] 聚合成 {key: 累计mul}。"""
    out = {}
    for k, m in pairs:
        out[k] = out.get(k, 0.0) + m
    return out


def factors_of(engine: str, case: dict, lng: float = 120.0, tz: float = 8.0) -> dict:
    """跑一次排盘，返回该案例的因子向量 {完整key: mul}。"""
    from . import liuyao, meihua, qimen, liuren, ziwei
    from .calendar import four_pillars

    if engine == "liuyao":
        if "date" in case:
            p = four_pillars(_parse_dt(case["date"]), lng, tz)
            day, month = p.day, p.month[1]
        else:
            day, month = case["day"], case["month"]
        if "coins" in case:
            chart = liuyao.cast_from_coins(case["coins"], day, month)
        else:
            chart = liuyao.cast_from_hexagram(case["hexagram"], case.get("moves", []),
                                              day, month)
        ev = chart.evaluate(ASK_MAP.get(case["ask"], case["ask"]))
        return _agg((f"liuyao.{it['key']}", it.get("mul", 1)) for it in ev["items"])

    if engine == "meihua":
        if "nums" in case:
            c = meihua.cast_by_numbers(case["nums"][0], case["nums"][1])
        else:
            c = meihua.cast_by_time(_parse_dt(case["date"]), lng, tz)
        mz = case.get("month") or four_pillars(_parse_dt(case["date"]), lng, tz).month[1]
        sc = c.score(mz)
        return _agg((f"meihua.{it['key'].split('.', 1)[1]}", it.get("mul", 1))
                    for it in sc["items"])

    if engine == "qimen":
        c = qimen.build(_parse_dt(case["date"]), lng, tz)
        return _agg((f["key"], f["mul"]) for f in c.factors())

    if engine == "liuren":
        c = liuren.build(_parse_dt(case["date"]), lng, tz)
        ev = c.evaluate()
        return _agg((f"liuren.{it['key'].split('.', 1)[1]}", it.get("mul", 1))
                    for it in ev["items"])

    if engine == "ziwei":
        c = ziwei.build(_parse_dt(case["date"]), lng, tz, case.get("gender", "m"))
        return _agg((f["key"], f["mul"]) for f in c.factors())

    raise ValueError(f"未知引擎：{engine}")


# ---------------- 设计矩阵 ----------------
def build_design(cases: list[dict], engine: str, lng=120.0, tz=8.0):
    rows, ys, used, skipped = [], [], [], []
    allkeys = []
    for idx, case in enumerate(cases):
        try:
            vec = factors_of(engine, case, lng, tz)
        except Exception as e:                      # 单条案例出错不应中断整体
            skipped.append((idx, str(e)))
            continue
        # 注意：vec 为空（全零）是合法案例——表示没有任何因子被触发，
        # 此时 score=0、判凶。不能当错误跳过，否则会筛掉大量「无事发生」的样本。
        y = case["result"]
        y = 1 if y in (1, True, "吉", "yes") else 0
        rows.append(vec)
        ys.append(y)
        used.append(idx)
        allkeys.extend(vec.keys())

    keys = sorted(set(allkeys))
    X = [[row.get(k, 0.0) for k in keys] for row in rows]
    return X, ys, keys, used, skipped


# ---------------- 逻辑回归（IRLS） ----------------
def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _solve(A, b):
    """高斯-约当消元解 A x = b（A 对称正定，加小量防奇异）。"""
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for i in range(n):
        M[i][i] += 1e-9
        piv = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[piv][i]) < 1e-12:
            continue
        M[i], M[piv] = M[piv], M[i]
        d = M[i][i]
        for j in range(i, n + 1):
            M[i][j] /= d
        for r in range(n):
            if r != i and M[r][i] != 0:
                f = M[r][i]
                for j in range(i, n + 1):
                    M[r][j] -= f * M[i][j]
    return [M[i][n] for i in range(n)]


def fit(X, y, l2: float = 1.0, iters: int = 25, w0=None):
    """带 L2 的逻辑回归，无截距（阈值即 0）。"""
    n, k = len(X), len(X[0]) if X else 0
    w = list(w0) if w0 else [0.0] * k
    for _ in range(iters):
        p = [_sigmoid(sum(X[i][j] * w[j] for j in range(k))) for i in range(n)]
        g = [sum((p[i] - y[i]) * X[i][j] for i in range(n)) + l2 * w[j]
             for j in range(k)]
        H = [[sum(p[i] * (1 - p[i]) * X[i][a] * X[i][b] for i in range(n))
              + (l2 if a == b else 0.0) for b in range(k)] for a in range(k)]
        step = _solve(H, g)
        w = [w[j] - step[j] for j in range(k)]
        if max((abs(s) for s in step), default=0) < 1e-8:
            break
    return w


def scores(X, w):
    return [sum(X[i][j] * w[j] for j in range(len(w))) for i in range(len(X))]


def accuracy(X, y, w):
    s = scores(X, w)
    hit = sum(1 for i in range(len(y)) if (s[i] > 0) == (y[i] == 1))
    return hit / len(y) if y else 0.0


def auc(X, y, w):
    s = scores(X, w)
    pos = [s[i] for i in range(len(y)) if y[i] == 1]
    neg = [s[i] for i in range(len(y)) if y[i] == 0]
    if not pos or not neg:
        return 0.5
    tot = 0.0
    for a in pos:
        for b in neg:
            tot += 1.0 if a > b else (0.5 if a == b else 0.0)
    return tot / (len(pos) * len(neg))


def loo_accuracy(X, y, l2: float = 1.0):
    """留一交叉验证：每次留出一个样本训练，预测它。"""
    n = len(y)
    if n < 4:
        return None
    correct = 0
    for i in range(n):
        Xi = [X[j] for j in range(n) if j != i]
        yi = [y[j] for j in range(n) if j != i]
        if len(set(yi)) < 2:          # 训练集只剩一类，无法学
            pred = yi[0]
        else:
            w = fit(Xi, yi, l2)
            pred = 1 if sum(X[i][k] * w[k] for k in range(len(w))) > 0 else 0
        correct += int(pred == y[i])
    return correct / n


def bootstrap_weights(X, y, l2: float = 1.0, n_boot: int = 120, seed: int = 7):
    rng = random.Random(seed)
    n, k = len(y), len(X[0]) if X else 0
    out = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        Xi = [X[i] for i in idx]
        yi = [y[i] for i in idx]
        if len(set(yi)) < 2:
            continue
        out.append(fit(Xi, yi, l2))
    return out


def quantile(vals, q):
    if not vals:
        return 0.0
    s = sorted(vals)
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


# ---------------- 报告 ----------------
def report(engine: str, cases: list[dict], l2: float = 1.0, n_boot: int = 120,
           lng: float = 120.0, tz: float = 8.0, default_rules=None) -> tuple[str, dict]:
    from .rules import Rules
    from .utils import pad

    rules = default_rules or Rules()
    X, y, keys, used, skipped = build_design(cases, engine, lng, tz)
    n, k = len(y), len(keys)
    if n == 0:
        return "没有任何可用案例。检查 case 格式与引擎是否匹配。", {}

    pos = sum(y)
    out = []
    out.append(f"引擎：{engine}　案例：{n} 条（吉 {pos}／凶 {n - pos}）"
               f"　因子：{k} 个" + (f"　跳过 {len(skipped)} 条" if skipped else ""))
    if skipped:
        for idx, why in skipped[:5]:
            out.append(f"  · 第 {idx} 条跳过：{why}")

    ratio = n / k if k else 0
    flag = "偏低，估计会不稳定" if ratio < 5 else ("尚可" if ratio < 10 else "充足")
    out.append(f"样本/特征比：{ratio:.1f}（{flag}；经验上 <5 时权重基本是噪声的拟合）")
    out.append("")

    w = fit(X, y, l2)
    acc = accuracy(X, y, w)
    loo = loo_accuracy(X, y, l2)
    a = auc(X, y, w)
    base = max(pos, n - pos) / n
    boots = bootstrap_weights(X, y, l2, n_boot)

    out.append("权重估计（bootstrap 95% 区间；符号 ✗ 表示与默认值方向相反）：")
    out.append("  " + pad("因子", 34) + pad("默认", 8) + pad("拟合", 8)
               + pad("区间", 22) + "方向")
    for j, key in enumerate(keys):
        short = key.split(".", 1)[1] if "." in key else key
        dw = rules.get(key, 0.0)
        vals = [b[j] for b in boots if j < len(b)]
        lo = quantile(vals, 0.025)
        hi = quantile(vals, 0.975)
        same = "✓" if (w[j] * dw > 0 or abs(dw) < 1e-9) else "✗"
        out.append("  " + pad(short, 34) + pad(f"{dw:+.2f}", 8)
                   + pad(f"{w[j]:+.2f}", 8)
                   + pad(f"[{lo:+.2f}, {hi:+.2f}]", 22) + same)
    out.append("")

    # 默认权重在同一批数据上的表现：它不是训练出来的，所以准确率无偏
    w_def = [rules.get(key, 0.0) for key in keys]
    acc_def = accuracy(X, y, w_def) if any(abs(v) > 1e-9 for v in w_def) else None

    out.append("模型表现：")
    out.append(f"  训练准确率　　{acc:.0%}　（拟合出来的，虚高，别信）")
    if loo is not None:
        se = math.sqrt(max(loo * (1 - loo), 1e-9) / n)
        out.append(f"  留一交叉验证　{loo:.0%} ± {1.96 * se:.0%}　← 校准权重的真指标")
    if acc_def is not None:
        out.append(f"  默认权重　　　{acc_def:.0%}　← 同一批数据、不做任何拟合的成绩")
    out.append(f"  基线（全猜多数类）{base:.0%}")
    out.append(f"  AUC　　　　　 {a:.2f}　（0.5 = 与抛硬币无异）")
    out.append("")

    if acc_def is not None and loo is not None:
        gap = loo - acc_def
        se_g = math.sqrt(max(loo * (1 - loo) + acc_def * (1 - acc_def), 1e-9) / n)
        if gap >= 1.96 * se_g:
            out.append(f"  → 校准比默认权重高 {gap:+.0%}，超出抽样误差，"
                       f"这批数据支持「调整权重确实有用」。")
        elif gap <= -1.96 * se_g:
            out.append(f"  → 校准比默认权重**低** {-gap:.0%}，超出抽样误差。"
                       f"这不是说默认值对，而是说：这批数据撑不起一次校准，"
                       f"动不如不动。拟合把噪声当成了信号。")
        else:
            out.append(f"  → 校准与默认权重相差 {gap:+.0%}，在抽样误差之内——"
                       f"这批数据**分辨不出哪个更好**。")
        out.append("")

    # 结论
    out.append("结论：")
    if loo is None:
        out.append("  案例太少，无法做交叉验证。这套权重只是把现有数据背了下来，"
                   "对外部案例没有预测力。")
    else:
        gain = loo - base
        se_d = math.sqrt(max(loo * (1 - loo) + base * (1 - base), 1e-9) / n)
        lo_g = gain - 1.96 * se_d
        hi_g = gain + 1.96 * se_d
        if gain <= 0:
            out.append(f"  交叉验证 {loo:.0%} 不高于基线 {base:.0%}——"
                       f"在你给的这批案例上，这套权重没有表现出解释力。")
        elif lo_g <= 0:
            out.append(f"  交叉验证比基线高 {gain:+.0%}，但 95% 区间 "
                       f"[{lo_g:+.0%}, {hi_g:+.0%}] 跨过 0——"
                       f"即**尚不能排除「和瞎猜一样」**。要下结论，样本还太少。")
        else:
            out.append(f"  交叉验证比基线高 {gain:+.0%}，95% 区间 "
                       f"[{lo_g:+.0%}, {hi_g:+.0%}] 不含 0——"
                       f"在这批案例上，这套因子有可测的解释力。")
            out.append("  但这只说明「在这批案例上」，不代表对未来的预测力。")

    if ratio < 5:
        out.append(f"  ⚠ 样本/特征比只有 {ratio:.1f}，拟合出的权重极可能是过拟合。"
                   f"建议至少补到 {k * 10} 条案例再看。")
    bad = [keys[j] for j in range(k)
           if abs(rules.get(keys[j], 0.0)) > 1e-9 and w[j] * rules.get(keys[j], 0.0) < 0]
    if bad:
        out.append(f"  ⚠ {len(bad)} 个权重的拟合方向与默认值相反："
                   + "、".join(b.split('.', 1)[-1] for b in bad))
        out.append("    可能是样本不足，也可能意味着这条规则在你的数据里确实不成立。"
                   "两者都值得记下来，但都不能只凭这批数据断定。")

    out.append("")
    out.append("怎么用这组权重：")
    out.append("  score = Σ (因子次数 × 权重)，score > 0 判吉。")
    out.append("  想写进 rules，用 --emit 导出 JSON，再用 --rules-file 载入——")
    out.append("  但请先看上面的交叉验证：它没赢过基线之前，导出的只是一堆数字。")

    summary = {"n": n, "k": k, "ratio": ratio, "weights": dict(zip(keys, w)),
               "loo": loo, "base": base, "auc": a, "accuracy": acc,
               "skipped": len(skipped)}
    return "\n".join(out), summary


# ---------------- 合成数据（仅供演示流程） ----------------
def make_demo(path: str, n: int = 60, seed: int = 11):
    """按默认权重模拟一批六爻案例。**这些结果不是真实占验记录**，
    只用来演示校准工具的用法。"""
    from . import liuyao
    from .calendar import four_pillars
    from .rules import Rules

    rng = random.Random(seed)
    rules = Rules()
    from datetime import timedelta
    cases = []
    start = datetime(2025, 1, 1)
    while len(cases) < n:
        dt = start + timedelta(minutes=rng.randrange(0, 365 * 24 * 60))
        coins = [rng.randrange(0, 4) for _ in range(6)]
        ask = rng.choice(["财", "官", "父", "子", "兄"])
        p = four_pillars(dt, 116.4, 8.0)
        try:
            chart = liuyao.cast_from_coins(coins, p.day, p.month[1], rules)
            ev = chart.evaluate({"财": "妻财", "官": "官鬼", "父": "父母",
                                 "子": "子孙", "兄": "兄弟"}[ask])
            if ev["picked"] is None:
                continue
            score = ev["score"]
            # 真实权重下判吉凶，再按 15% 概率翻转（模拟噪声）
            result = 1 if score > 0 else 0
            if rng.random() < 0.15:
                result = 1 - result
        except Exception:
            continue
        cases.append({"date": dt.strftime("%Y-%m-%d %H:%M"), "coins": coins,
                      "ask": ask, "result": result})

    data = {
        "_note": "合成数据：按默认权重模拟 + 15% 噪声翻转，不是真实占验记录，"
                 "仅用于演示 calibrate 的用法。",
        "engine": "liuyao",
        "cases": cases,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path

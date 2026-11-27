"""规则权重配置中心。

设计要点
--------
古法只有定性规则（"用神旺相有生则成"），没有数值权重。本模块把它们
量化成可调参数——目的不是伪造"正确权重"，而是让你能看清：
**结论是被哪几个因子推着走的，改一个权重，结论会不会翻。**

所有默认值都是启发式设定值，不是古籍原数。参数分四组：
  liuyao 六爻   meihua 梅花   bazi 八字   qimen 奇门
"""
import json
import os

DEFAULTS = {
    "liuyao": {
        "month": {"lin": 3.0, "sheng": 2.0, "ke": -2.0, "po": -3.0},
        "day": {"lin": 2.0, "sheng": 1.5, "ke": -1.5,
                "chong_wang": 1.0, "chong_shuai": -2.0},
        "kong": -2.0,
        "moving": {"sheng_yong": 2.5, "ke_yong": -2.5, "yong_moves": 1.0},
        "hua": {"huisheng": 2.0, "huike": -2.0, "jin": 1.0, "tui": -1.0},
        "shi": {"yong_on_shi": 1.5, "shi_sheng": 0.5, "shi_ke": -0.5},
        "thresholds": {"daji": 5.0, "ji": 2.0, "ping_lo": -2.0, "xiong": -5.0},
    },
    "meihua": {
        "relation": {"用生体": 3.0, "比和": 2.0, "体克用": 1.0,
                     "体生用": -2.0, "用克体": -3.0},
        "stage": {"ben": 0.4, "hu": 0.3, "bian": 0.3},
        "wangshuai": {"旺": 0.6, "相": 0.3, "休": -0.3, "囚": -0.5, "死": -0.7},
        "thresholds": {"daji": 2.5, "ji": 1.0, "ping_lo": -1.0, "xiong": -2.5},
    },
    "bazi": {
        "weight": {"month_zhi": 3.0, "other_zhi": 1.5, "gan": 1.0, "self": 1.0},
        "cang": {"benqi": 0.6, "zhongqi": 0.3, "yuqi": 0.1},
        "strength": {"strong": 0.55, "weak": 0.45},
    },
    "liuren": {
        "chuan": {"sheng_wo": 1.5, "bihe": 0.5, "wo_sheng": -0.5,
                  "wo_ke": -1.0, "ke_wo": -2.0},
        "jiang": {"ji": 1.0, "xiong": -1.0},
        "thresholds": {"daji": 4.0, "ji": 1.5, "ping_lo": -1.5, "xiong": -4.0},
    },
    "ziwei": {
        "score": {"ji_xing": 1.0, "sha_xing": -1.2, "hua_lu": 2.0,
                  "hua_ji": -2.0, "hua_other": 0.8, "empty": -0.5},
        "thresholds": {"daji": 5.0, "ji": 2.0, "ping_lo": -2.0, "xiong": -5.0},
    },
    "qimen": {
        "order": {"star": "num", "gate": "bagua", "god": "bagua"},
        "zhong_gong": "kun",
        "thresholds": {"daji": 5.0, "ji": 2.0, "ping_lo": -2.0, "xiong": -5.0},
        "score": {"ji_men": 1.5, "xiong_men": -1.5,
                  "ji_xing": 1.0, "xiong_xing": -1.0,
                  "san_qi": 1.5, "men_po": -1.0, "ji_xing_ge": -1.5},
    },
}

PRESETS = {
    # 古法倾向：月建 > 日辰，动爻权重最大，忌神当权直接压倒
    "classic": {
        "liuyao": {
            "month": {"lin": 3.5, "sheng": 2.5, "ke": -2.5, "po": -4.0},
            "day": {"lin": 1.5, "sheng": 1.0, "ke": -1.0,
                    "chong_wang": 0.8, "chong_shuai": -1.5},
            "moving": {"sheng_yong": 3.5, "ke_yong": -3.5, "yong_moves": 1.5},
        },
        "meihua": {"stage": {"ben": 0.5, "hu": 0.2, "bian": 0.3}},
        "qimen": {"score": {"ji_men": 1.0, "xiong_men": -2.0, "san_qi": 1.0}},
        "liuren": {"jiang": {"ji": 0.6, "xiong": -1.5},
                   "thresholds": {"daji": 5.0, "ji": 2.0, "ping_lo": -1.0, "xiong": -3.0}},
    },
    # 保守：惩罚放大、吉的门槛抬高，宁可判"待定"
    "strict": {
        "liuyao": {"month": {"po": -4.5}, "kong": -3.0,
                   "moving": {"ke_yong": -3.5},
                   "thresholds": {"daji": 6.0, "ji": 3.0, "ping_lo": -1.0, "xiong": -4.0}},
        "meihua": {"thresholds": {"daji": 3.0, "ji": 1.5, "ping_lo": -0.5, "xiong": -2.0}},
        "qimen": {"thresholds": {"daji": 6.0, "ji": 3.0, "ping_lo": -1.0, "xiong": -4.0}},
        "liuren": {"jiang": {"xiong": -1.5},
                   "thresholds": {"daji": 5.5, "ji": 2.5, "ping_lo": -0.5, "xiong": -3.0}},
    },
    # 宽松：吉的判定门槛低，适合把卦当"倾向提示"而非裁决
    "loose": {
        "liuyao": {"month": {"po": -2.0}, "kong": -1.0,
                   "thresholds": {"daji": 4.0, "ji": 1.0, "ping_lo": -3.0, "xiong": -6.0}},
        "meihua": {"thresholds": {"daji": 2.0, "ji": 0.5, "ping_lo": -1.5, "xiong": -3.0}},
        "qimen": {"thresholds": {"daji": 4.0, "ji": 1.0, "ping_lo": -3.0, "xiong": -6.0}},
        "liuren": {"thresholds": {"daji": 3.0, "ji": 1.0, "ping_lo": -2.0, "xiong": -5.0}},
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Rules:
    """点号路径访问的配置对象，例：r.get('liuyao.month.lin')。"""

    def __init__(self, data: dict | None = None):
        self.data = _deep_merge(DEFAULTS, data or {})

    # ---- 读 ----
    def get(self, path: str, default=None):
        cur = self.data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    # ---- 写 ----
    def set(self, path: str, value):
        parts = path.split(".")
        cur = self.data
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value

    def apply_preset(self, name: str):
        if name not in PRESETS:
            raise KeyError(f"未知预设：{name}（可选：{', '.join(PRESETS)}）")
        self.data = _deep_merge(self.data, PRESETS[name])

    def apply_overrides(self, pairs: list[str]):
        """处理 --set key=value 形式的覆盖。"""
        for item in pairs:
            if "=" not in item:
                raise ValueError(f"--set 需要 key=value 形式：{item}")
            k, v = item.split("=", 1)
            k = k.strip()
            v = v.strip()
            if v.lower() in ("true", "false"):
                val = v.lower() == "true"
            else:
                try:
                    val = float(v) if ("." in v or "e" in v.lower()) else int(v)
                except ValueError:
                    val = v
            self.set(k, val)

    # ---- 存取 ----
    def save(self, path: str):
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "Rules":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def dump(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2)

    def flat(self, prefix: str = "", _data: dict | None = None) -> list[tuple[str, object]]:
        data = self.data if _data is None else _data
        out = []
        for k, v in data.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.extend(self.flat(key, v))
            else:
                out.append((key, v))
        return out


def grade(score: float, th: dict) -> str:
    """把总分映射为等级。keys: daji / ji / ping_lo / xiong"""
    if score >= th["daji"]:
        return "大吉"
    if score >= th["ji"]:
        return "吉"
    if score > th["ping_lo"]:
        return "平／待定"
    if score > th["xiong"]:
        return "不利"
    return "凶"


def bar(value: float, scale: float, width: int = 12) -> str:
    """分值可视化：正为 +，负为 −。"""
    if scale <= 0:
        return ""
    n = int(round(abs(value) / scale * width))
    n = max(n, 0) if value == 0 else max(n, 1)
    return ("＋" if value >= 0 else "－") + "█" * n

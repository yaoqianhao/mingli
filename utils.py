"""终端输出小工具：按显示宽度对齐（中文字符算 2 列）。"""
import unicodedata


def dwidth(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s: str, width: int, align: str = "left") -> str:
    s = str(s)
    gap = width - dwidth(s)
    if gap <= 0:
        return s
    if align == "right":
        return " " * gap + s
    if align == "center":
        l = gap // 2
        return " " * l + s + " " * (gap - l)
    return s + " " * gap


def table(rows: list[list[str]], widths: list[int], aligns: list[str] | None = None) -> str:
    aligns = aligns or ["left"] * len(widths)
    return "\n".join(
        "".join(pad(c, w, a) for c, w, a in zip(r, widths, aligns)) for r in rows
    )

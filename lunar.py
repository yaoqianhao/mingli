"""农历（阴阳合历）计算。

用途：梅花易数时间起卦需要农历月日；择日、节气对照也需要。
算法：Meeus《Astronomical Algorithms》第 49 章新月公式（精度约数秒），
     以「冬至所在月为十一月」「无中气之月为闰月」定月序。
"""
import math
from datetime import datetime

from .calendar import (jd_from_datetime, jdn_from_ymd, ymd_from_jd, delta_t_seconds,
                       solar_term_events, solar_longitude)

MONTH_NAMES = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
_CN = "零一二三四五六七八九"


def cn_num(n: int) -> str:
    """1-30 的中文写法（农历日用）。"""
    if n < 10:
        return _CN[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + _CN[n % 10]
    return _CN[n // 10] + "十" + (_CN[n % 10] if n % 10 else "")
TZ = 8.0


def new_moon_jde(k: int) -> float:
    """第 k 个朔的力学时儒略日（Meeus 49.1）。"""
    t = k / 1236.85
    jde = (2451550.09766 + 29.530588861 * k + 0.00015437 * t ** 2
           - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4)
    e = 1 - 0.002516 * t - 0.0000074 * t ** 2
    m = math.radians(2.5534 + 29.10535670 * k - 0.0000014 * t ** 2 - 0.00000011 * t ** 3)
    mp = math.radians(201.5643 + 385.81693528 * k + 0.0107582 * t ** 2
                      + 0.00001238 * t ** 3 - 0.000000058 * t ** 4)
    f = math.radians(160.7108 + 390.67050284 * k - 0.0016118 * t ** 2
                     - 0.00000227 * t ** 3 + 0.000000011 * t ** 4)
    om = math.radians(124.7746 - 1.56375588 * k + 0.0020672 * t ** 2 + 0.00000215 * t ** 3)
    corr = (-0.40720 * math.sin(mp)
            + 0.17241 * e * math.sin(m)
            + 0.01608 * math.sin(2 * mp)
            + 0.01039 * math.sin(2 * f)
            + 0.00739 * e * math.sin(mp - m)
            - 0.00514 * e * math.sin(mp + m)
            + 0.00208 * e * e * math.sin(2 * m)
            - 0.00111 * math.sin(mp - 2 * f)
            - 0.00057 * math.sin(mp + 2 * f)
            + 0.00056 * e * math.sin(2 * mp + m)
            - 0.00042 * math.sin(3 * mp)
            + 0.00042 * e * math.sin(m + 2 * f)
            + 0.00038 * e * math.sin(m - 2 * f)
            - 0.00024 * e * math.sin(2 * mp - m)
            - 0.00017 * math.sin(om)
            - 0.00007 * math.sin(mp + 2 * m))
    return jde + corr


def new_moon_jd_local(k: int, tz: float = TZ) -> float:
    """第 k 个朔，换算为本地时儒略日。"""
    jde = new_moon_jde(k)
    year = 2000 + k / 12.3685
    return jde - delta_t_seconds(year) / 86400.0 + tz / 24.0


def _nm_jdn(k: int, tz: float = TZ) -> int:
    """第 k 个朔所在的日期（儒略日数）。"""
    return math.floor(new_moon_jd_local(k, tz) + 0.5)


def _guess_k(jd: float) -> int:
    return int((jd - 2451550.09766) / 29.530588861)


def month_index_of(jd: float, tz: float = TZ) -> int:
    """jd 落在第几号朔望月（返回该月朔的 k）。"""
    jdn = math.floor(jd + 0.5)
    k = _guess_k(jd)
    while _nm_jdn(k + 1, tz) <= jdn:
        k += 1
    while _nm_jdn(k, tz) > jdn:
        k -= 1
    return k


def _solar_term_jd(deg: int, year: int, tz: float = TZ) -> float:
    """求某公历年附近、指定黄经的节气（本地时儒略日）。"""
    jd0 = jdn_from_ymd(year, 1, 1) - 0.5
    jd1 = jdn_from_ymd(year + 1, 1, 1) - 0.5
    for jd, name, d in solar_term_events(jd0, jd1):
        if d == deg:
            return jd + tz / 24.0
    # 冬至/小寒可能在年界外
    for jd, name, d in solar_term_events(jd0 - 40, jd1 + 40):
        if d == deg:
            return jd + tz / 24.0
    raise RuntimeError("未找到节气")


def _has_zhongqi(start_jdn: int, end_jdn: int, tz: float = TZ) -> bool:
    """[start_jdn, end_jdn) 之间是否含中气（黄经为 30 的整数倍的节气）。"""
    jd0 = start_jdn - 0.5
    jd1 = end_jdn - 0.5
    for jd, name, deg in solar_term_events(jd0 - 2, jd1 + 2):
        local_jdn = math.floor(jd + tz / 24.0 + 0.5)
        if start_jdn <= local_jdn < end_jdn and deg % 30 == 0:
            return True
    return False


def lunar_date(dt: datetime, tz: float = TZ) -> dict:
    """公历 datetime -> 农历 {year, month, day, is_leap, month_name}。"""
    jd = jd_from_datetime(dt)
    jdn = math.floor(jd + 0.5)
    k = month_index_of(jd, tz)
    day = jdn - _nm_jdn(k, tz) + 1

    # 冬至（所在公历年 12 月）
    ws_jd = _solar_term_jd(270, dt.year, tz)
    if math.floor(ws_jd + 0.5) > jdn:      # 今年冬至还没到，用去年冬至
        ws_jd = _solar_term_jd(270, dt.year - 1, tz)
    k11 = month_index_of(ws_jd, tz)

    # 下一个冬至所在月
    ws_year = ymd_from_jd(ws_jd - tz / 24)[0]
    next_ws_jd = _solar_term_jd(270, ws_year + 1, tz)
    k11_next = month_index_of(next_ws_jd, tz)

    leap_k = None
    if k11_next - k11 == 13:                # 十三个月 -> 有闰月
        for kk in range(k11, k11_next):
            if not _has_zhongqi(_nm_jdn(kk, tz), _nm_jdn(kk + 1, tz), tz):
                leap_k = kk
                break

    seq = k - k11
    if leap_k is not None and leap_k <= k:
        seq -= 1                            # 闰月不占月序，取前一月之名
    is_leap = (leap_k == k)
    month = (11 + seq) % 12
    month = 12 if month == 0 else month

    lunar_year = ws_year + 1 if seq >= 2 else ws_year

    return {
        "year": lunar_year,
        "month": month,
        "day": day,
        "is_leap": is_leap,
        "month_name": ("闰" if is_leap else "") + MONTH_NAMES[month - 1] + "月",
        "day_cn": cn_num(day),
    }

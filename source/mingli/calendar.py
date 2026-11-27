"""天文历法层：儒略日、太阳视黄经、二十四节气、真太阳时、四柱排盘。

全部自算，不依赖万年历接口。太阳黄经采用 Meeus《Astronomical Algorithms》
第 25 章低精度公式（精度约 0.01°，对应节气时刻误差约数分钟），
对判定年柱、月柱的节气分界足够；若出生时刻恰在节气前后 10 分钟内，
程序会给出提示，此时改用高精度星历复核。
"""
import math
from datetime import datetime, timedelta

from .jiazi import GAN, ZHI, gan_index, zhi_index, yinyang

# 二十四节气（按太阳视黄经，单位度）
SOLAR_TERMS = [
    ("春分", 0), ("清明", 15), ("谷雨", 30), ("立夏", 45), ("小满", 60), ("芒种", 75),
    ("夏至", 90), ("小暑", 105), ("大暑", 120), ("立秋", 135), ("处暑", 150), ("白露", 165),
    ("秋分", 180), ("寒露", 195), ("霜降", 210), ("立冬", 225), ("小雪", 240), ("大雪", 255),
    ("冬至", 270), ("小寒", 285), ("大寒", 300), ("立春", 315), ("雨水", 330), ("惊蛰", 345),
]
DEG_TO_NAME = {d: n for n, d in SOLAR_TERMS}

# 十二「节」（月建分界）与月支
JIE_TO_ZHI = {315: "寅", 345: "卯", 15: "辰", 45: "巳", 75: "午", 105: "未",
              135: "申", 165: "酉", 195: "戌", 225: "亥", 255: "子", 285: "丑"}


# ---------------- 儒略日 ----------------
def jdn_from_ymd(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def jd_from_datetime(dt: datetime) -> float:
    base = jdn_from_ymd(dt.year, dt.month, dt.day) - 0.5
    frac = (dt.hour + dt.minute / 60 + dt.second / 3600) / 24
    return base + frac


def ymd_from_jd(jd: float):
    jdn = math.floor(jd + 0.5)
    frac = jd + 0.5 - jdn
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d2 = (4 * c + 3) // 1461
    e = c - (1461 * d2) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d2 - 4800 + m // 10
    secs = frac * 86400
    return year, month, day, int(secs // 3600), int(secs % 3600 // 60), int(secs % 60)


def day_of_year(dt: datetime) -> int:
    return dt.timetuple().tm_yday


# ---------------- 太阳视黄经 ----------------
def delta_t_seconds(year: float) -> float:
    """TT - UT（秒），Espenak & Meeus 多项式。"""
    if 2005 <= year <= 2050:
        t = year - 2000
        return 62.92 + 0.32217 * t + 0.005589 * t * t
    if 1986 <= year < 2005:
        t = year - 2000
        return (63.86 + 0.3345 * t - 0.060374 * t ** 2 + 0.0017275 * t ** 3
                + 0.000651814 * t ** 4 + 0.00002373599 * t ** 5)
    if 1961 <= year < 1986:
        t = year - 1975
        return 45.45 + 1.067 * t - t ** 2 / 260 - t ** 3 / 718
    t = year - 2000
    return 62.92 + 0.32217 * t + 0.005589 * t * t


def solar_longitude(jd_ut: float) -> float:
    """太阳视黄经（度，0-360）。输入为 UT 儒略日。"""
    y, mo, d, h, mi, s = ymd_from_jd(jd_ut)
    year_frac = y + (mo - 0.5) / 12
    jd_tt = jd_ut + delta_t_seconds(year_frac) / 86400.0
    t = (jd_tt - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t
    mr = math.radians(m % 360)
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(mr)
         + (0.019993 - 0.000101 * t) * math.sin(2 * mr)
         + 0.000289 * math.sin(3 * mr))
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    apparent = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    return apparent % 360


def _unwrap(lam: float, ref: float) -> float:
    while lam < ref - 180:
        lam += 360
    while lam > ref + 180:
        lam -= 360
    return lam


def _bisect_term(jd_lo: float, jd_hi: float, target: float, ref: float) -> float:
    def f(x):
        return _unwrap(solar_longitude(x), ref) - target
    flo, fhi = f(jd_lo), f(jd_hi)
    if flo == 0:
        return jd_lo
    if flo * fhi > 0:
        return (jd_lo + jd_hi) / 2
    for _ in range(60):
        mid = (jd_lo + jd_hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            jd_hi, fhi = mid, fm
        else:
            jd_lo, flo = mid, fm
    return (jd_lo + jd_hi) / 2


def solar_term_events(jd_start: float, jd_end: float) -> list[tuple[float, str, int]]:
    """返回区间内全部节气事件 [(jd_ut, 名称, 黄经)]，按时间排序。"""
    events = []
    jd = jd_start
    prev = solar_longitude(jd)
    prev_u = prev
    while jd < jd_end:
        jd2 = min(jd + 2.0, jd_end)
        cur = solar_longitude(jd2)
        delta = (cur - prev) % 360
        lo, hi = prev_u, prev_u + delta
        k = math.floor(lo / 15.0) + 1
        while k * 15.0 <= hi + 1e-9:
            target = k * 15.0
            t = _bisect_term(jd, jd2, target, lo)
            deg = int(round(target)) % 360
            events.append((t, DEG_TO_NAME[deg], deg))
            k += 1
        prev, prev_u, jd = cur, hi, jd2
    return events


# ---------------- 真太阳时 ----------------
def equation_of_time_minutes(dt: datetime) -> float:
    """均时差（分钟），NOAA 近似式。"""
    n = day_of_year(dt)
    gamma = 2 * math.pi / 365.0 * (n - 1 + (dt.hour - 12) / 24.0)
    return 229.18 * (0.000075
                     + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                     - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))


def true_solar_time(dt_local: datetime, longitude: float, tz: float = 8.0) -> datetime:
    """由标准时求真太阳时。longitude 为东经正、西经负。"""
    offset_min = (longitude - tz * 15.0) * 4.0 + equation_of_time_minutes(dt_local)
    return dt_local + timedelta(minutes=offset_min)


# ---------------- 四柱 ----------------
class Pillars:
    def __init__(self, year_gz, month_gz, day_gz, hour_gz, meta):
        self.year, self.month, self.day, self.hour = year_gz, month_gz, day_gz, hour_gz
        self.meta = meta

    def as_list(self):
        return [self.year, self.month, self.day, self.hour]

    def __repr__(self):
        return f"{self.year} {self.month} {self.day} {self.hour}"


def four_pillars(dt_local: datetime, longitude: float = 120.0, tz: float = 8.0,
                 day_boundary_23: bool = False) -> Pillars:
    """排四柱。

    dt_local : 出生地法定标准时间（不是真太阳时）
    longitude: 出生地经度（东经正）
    day_boundary_23: True 表示 23:00 即换日（子时起算），False 表示 0:00 换日
    """
    warnings = []
    jd_ut = jd_from_datetime(dt_local) - tz / 24.0     # 出生瞬间的 UT
    tst = true_solar_time(dt_local, longitude, tz)      # 真太阳时（用于日、时柱）

    # 取足够长的节气窗口
    events = solar_term_events(jd_ut - 400, jd_ut + 10)

    # 年柱：以立春为界
    lichun_list = [e for e in events if e[2] == 315 and e[0] <= jd_ut]
    if not lichun_list:
        raise RuntimeError("节气窗口不足")
    lichun = lichun_list[-1]
    solar_year = ymd_from_jd(lichun[0] + tz / 24.0)[0]
    year_idx = (solar_year - 4) % 60
    year_gz = GAN[year_idx % 10] + ZHI[year_idx % 12]

    # 月柱：以「节」为界
    jie_list = [e for e in events if e[2] in JIE_TO_ZHI and e[0] <= jd_ut]
    jie = jie_list[-1]
    month_zhi = JIE_TO_ZHI[jie[2]]
    fire_month_gan = (gan_index(year_gz[0]) % 5 * 2 + 2) % 10   # 五虎遁，寅月天干
    offset = zhi_index(month_zhi) - zhi_index("寅")
    offset %= 12
    month_gan = GAN[(fire_month_gan + offset) % 10]
    month_gz = month_gan + month_zhi
    if abs(jd_ut - jie[0]) < 15.0 / 1440:
        warnings.append(f"出生时刻距「{jie[1]}」仅 {abs(jd_ut - jie[0]) * 1440:.0f} 分钟，"
                        f"月柱分界存疑，建议用高精度星历复核")

    # 日柱：真太阳时日期
    d = tst
    if day_boundary_23 and d.hour >= 23:
        d = d + timedelta(days=1)
    jdn = jdn_from_ymd(d.year, d.month, d.day)
    day_idx = (jdn + 49) % 60
    day_gz = GAN[day_idx % 10] + ZHI[day_idx % 12]

    # 时柱：五鼠遁
    h = tst.hour
    hour_zhi_idx = ((h + 1) // 2) % 12
    hour_zhi = ZHI[hour_zhi_idx]
    hour_gan_idx = (gan_index(day_gz[0]) % 5 * 2 + hour_zhi_idx) % 10
    hour_gz = GAN[hour_gan_idx] + hour_zhi

    meta = {
        "input": dt_local.strftime("%Y-%m-%d %H:%M:%S"),
        "true_solar_time": tst.strftime("%Y-%m-%d %H:%M:%S"),
        "tz": tz, "longitude": longitude,
        "solar_year": solar_year,
        "month_jie": jie[1],
        "jie_time_local": (ymd_from_jd(jie[0] + tz / 24.0)),
        "lichun_local": (ymd_from_jd(lichun[0] + tz / 24.0)),
        "eot_min": round(equation_of_time_minutes(dt_local), 2),
        "warnings": warnings,
        "day_boundary_23": day_boundary_23,
    }
    return Pillars(year_gz, month_gz, day_gz, hour_gz, meta)


def jieqi_of_year(year: int, tz: float = 8.0) -> list[tuple[str, str]]:
    """某公历年内的二十四节气及本地时间。"""
    jd0 = jdn_from_ymd(year, 1, 1) - 0.5
    jd1 = jdn_from_ymd(year + 1, 1, 1) - 0.5
    out = []
    for jd, name, deg in solar_term_events(jd0, jd1):
        y, mo, d, h, mi, _ = ymd_from_jd(jd + tz / 24.0)
        out.append((name, f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"))
    return out

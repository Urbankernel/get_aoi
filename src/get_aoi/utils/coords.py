# -*- coding: utf-8 -*-
"""坐标转换工具。

支持 GCJ-02（高德火星坐标）、BD09 / bd09mc（百度）与 WGS-84 互转。
算法对齐 coordTransform_py / geo_convert，已在 amap_aoi_parser.py、
baidu_aoi_parser.py 实测验证（同济大学校区边界）。

全部仅使用 Python 标准库。
"""
import math

A = 6378245.0
EE = 0.00669342162296594323
X_PI = math.pi * 3000.0 / 180.0


# ---------- GCJ-02 <-> WGS-84 ----------
def _transform_lat(x, y):
    ret = (-100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y
           + 0.1 * x * y + 0.2 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * math.pi)
            + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi)
            + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi)
            + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x, y):
    ret = (300.0 + x + 2.0 * y + 0.1 * x * x
           + 0.1 * x * y + 0.1 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * math.pi)
            + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi)
            + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi)
            + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def _delta(lng, lat):
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * math.pi)
    return dlng, dlat


def wgs84_to_gcj02(lng, lat):
    dlng, dlat = _delta(lng, lat)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng, lat):
    dlng, dlat = _delta(lng, lat)
    return lng - dlng, lat - dlat


# ---------- BD09 <-> GCJ-02 ----------
def bd09_to_gcj02(lng, lat):
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return z * math.cos(theta), z * math.sin(theta)


def gcj02_to_bd09(lng, lat):
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * X_PI)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * X_PI)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


# ---------- bd09mc（百度墨卡托）-> BD09 ----------
MCBAND = [12890594.86, 8362377.87, 5591021.0, 3481989.83, 1678043.12, 0.0]
MC2LL = [
    [1.410526172116255e-8, 0.00000898305509648872, -1.9939833816331,
     200.9824383106796, -187.2403703815547, 91.6087516669843,
     -23.38765649603339, 2.57121317296198, -0.03801003308653, 17337981.2],
    [-7.435856389565537e-9, 0.000008983055097726239, -0.78625201886289,
     96.32687599759846, -1.85204757529826, -59.36935905485877,
     47.40033549296737, -16.50741931063887, 2.28786674699375, 10260144.86],
    [-3.030883460898826e-8, 0.00000898305509983578, 0.30071316287616,
     59.74293618442277, 7.357984074871, -25.38371002664745,
     13.45380521110908, -3.29883767235584, 0.32710905363475, 6856817.37],
    [-1.981981304930552e-8, 0.000008983055099779535, 0.03278182852591,
     40.31678527705744, 0.65659298677277, -4.44255534477492,
     0.85341911805263, 0.12923347998204, -0.04625736007561, 4482777.06],
    [3.09191371068437e-9, 0.000008983055096812155, 0.00006995724062,
     23.10934304144901, -0.00023663490511, -0.6321817810242,
     -0.00663494467273, 0.03430082397953, -0.00466043876332, 2555164.4],
    [2.890871144776878e-9, 0.000008983055095805407, -3.068298e-8,
     7.47137025468032, -0.00000353937994, -0.02145144861037,
     -0.00001234426596, 0.00010322952773, -0.00000323890364, 826088.5],
]


def bd09mc_to_bd09(x, y):
    cF = MC2LL[-1]
    for i, band in enumerate(MCBAND):
        if abs(y) >= band:
            cF = MC2LL[i]
            break
    xa, ya = abs(x), abs(y)
    lng = cF[0] + cF[1] * xa
    c = ya / cF[9]
    lat = (cF[2] + cF[3] * c + cF[4] * c ** 2 + cF[5] * c ** 3
           + cF[6] * c ** 4 + cF[7] * c ** 5 + cF[8] * c ** 6)
    return lng * (1 if x >= 0 else -1), lat * (1 if y >= 0 else -1)


def bd09mc_to_wgs84(x, y):
    """百度墨卡托 -> WGS-84（三级：mc -> bd09 -> gcj02 -> wgs84）。"""
    bdlng, bdlat = bd09mc_to_bd09(x, y)
    glng, glat = bd09_to_gcj02(bdlng, bdlat)
    return gcj02_to_wgs84(glng, glat)


def bd09_to_wgs84(lng, lat):
    glng, glat = bd09_to_gcj02(lng, lat)
    return gcj02_to_wgs84(glng, glat)


# ---------- BD09 -> bd09mc（百度墨卡托） ----------
LLBAND = [75, 60, 45, 30, 15, 0]
LL2MC = [
    [-0.0015702102444, 111320.7020616939, 1704480524535203, -10338987376042340,
     26112667856603880, -35149669176653700, 26595700718403920,
     -10725012454188240, 1800819912950474, 82.5],
    [0.0008277824516172526, 111320.7020463578, 647795574.6671607,
     -4082003173.641316, 10774905663.51142, -15171875531.51559,
     12053065338.62167, -5124939663.577472, 913311935.9512032, 67.5],
    [0.00337398766765, 111320.7020202162, 4481351.045890365,
     -23393751.19931662, 79682215.47186455, -115964993.2797253,
     97236711.15602145, -43661946.33752821, 8477230.501135234, 52.5],
    [0.00220636496208, 111320.7020209128, 51751.86112841131, 3796837.749470245,
     992013.7397791013, -1221952.21711287, 1340652.697009075,
     -620943.6990984312, 144416.9293806241, 37.5],
    [-0.0003441963504368392, 111320.7020576856, 278.2353980772752,
     2485758.690035394, 6070.750963243378, 54821.18345352118,
     9540.606633304236, -2710.55326746645, 1405.483844121726, 22.5],
    [-0.0003218135878613132, 111320.7020701615, 0.00369383431289,
     823725.6402795718, 0.46104986909093, 2351.343141331292,
     1.58060784298199, 8.77738589078284, 0.37238884252424, 7.45],
]


def bd09_to_bd09mc(lng, lat):
    """BD09 经纬度 -> 百度墨卡托（米制 x,y），LL2MC 正向转换。"""
    cE = LL2MC[-1]
    for i, band in enumerate(LLBAND):
        if lat >= band:
            cE = LL2MC[i]
            break
    x = cE[0] + cE[1] * abs(lng)
    tmp = abs(lat) / cE[9]
    y = (cE[2] + cE[3] * tmp + cE[4] * tmp ** 2 + cE[5] * tmp ** 3
         + cE[6] * tmp ** 4 + cE[7] * tmp ** 5 + cE[8] * tmp ** 6)
    return x * (1 if lng > 0 else -1), y * (1 if lat > 0 else -1)


# ---------- 坐标串解析与批量转换 ----------
def convert_point(lng, lat, src, dst="wgs84"):
    """单点坐标转换。src/dst ∈ {wgs84, gcj02, bd09, bd09mc}。"""
    src, dst = src.lower(), dst.lower()
    if src == dst:
        return lng, lat
    if src == "bd09mc":
        if dst == "bd09":
            return bd09mc_to_bd09(lng, lat)
        if dst == "gcj02":
            b = bd09mc_to_bd09(lng, lat)
            return bd09_to_gcj02(*b)
        return bd09mc_to_wgs84(lng, lat)
    if src == "bd09":
        if dst == "gcj02":
            return bd09_to_gcj02(lng, lat)
        if dst == "wgs84":
            return bd09_to_wgs84(lng, lat)
        if dst == "bd09mc":
            return bd09_to_bd09mc(lng, lat)
    if src == "gcj02":
        if dst == "wgs84":
            return gcj02_to_wgs84(lng, lat)
        if dst == "bd09":
            return gcj02_to_bd09(lng, lat)
        if dst == "bd09mc":
            return bd09_to_bd09mc(*gcj02_to_bd09(lng, lat))
    if src == "wgs84":
        if dst == "gcj02":
            return wgs84_to_gcj02(lng, lat)
        if dst == "bd09":
            return gcj02_to_bd09(*wgs84_to_gcj02(lng, lat))
        if dst == "bd09mc":
            return bd09_to_bd09mc(*gcj02_to_bd09(*wgs84_to_gcj02(lng, lat)))
    raise ValueError(f"不支持的坐标转换：{src} -> {dst}")


def convert_points(points, src, dst="wgs84"):
    """批量转换 [(lng,lat),...]，bd09mc 的输入即 (x,y) 米制坐标。"""
    return [convert_point(x, y, src, dst) for x, y in points]

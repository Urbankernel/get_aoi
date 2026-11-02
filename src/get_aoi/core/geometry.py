# -*- coding: utf-8 -*-
"""几何工具：GeoJSON 构建、球面近似面积、中心点、距离。

geometry 统一为 GeoJSON dict（WGS-84）。面积/中心均为近似值，
足以支撑"面积过滤"与"综合排序"的业务判断，不用于精确量算。
"""
import math

EARTH_R_KM = 6371.0088


def close_ring(ring):
    """首尾闭合为合法环。"""
    if ring and ring[0] != ring[-1]:
        return list(ring) + [ring[0]]
    return list(ring)


def split_rings(points):
    """按"回到起点"把连续坐标点拆成多个闭合环。

    多部件/飞地 AOI 常把多个环首尾相接成一条坐标序列（下一个环的起点
    即上一个环的终点），检测到坐标回到起始点即视为一个环闭合，其后开启
    新环；单环或无闭合标记时整体作为一个环返回。
    """
    if not points:
        return []
    rings = []
    current = []
    start = None
    for p in points:
        if not current:
            current = [p]
            start = p
        else:
            current.append(p)
            if p == start:
                rings.append(current)
                current = []
    if current:
        rings.append(current)
    return rings


def polygon_geometry(rings):
    """rings=[外环, 洞1, ...]，每环 [(lng,lat),...] -> Polygon GeoJSON。"""
    closed = [[[round(x, 7), round(y, 7)] for x, y in close_ring(r)]
              for r in rings if len(r) >= 3]
    if not closed:
        return None
    return {"type": "Polygon", "coordinates": closed}


def multipolygon_geometry(polys):
    """polys=[rings1, rings2, ...] -> MultiPolygon GeoJSON。"""
    coords = []
    for rings in polys:
        closed = [[[round(x, 7), round(y, 7)] for x, y in close_ring(r)]
                  for r in rings if len(r) >= 3]
        if closed:
            coords.append(closed)
    if not coords:
        return None
    if len(coords) == 1:
        return {"type": "Polygon", "coordinates": coords[0]}
    return {"type": "MultiPolygon", "coordinates": coords}


def _iter_polygons(geometry):
    if not geometry:
        return
    if geometry["type"] == "Polygon":
        yield geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        for poly in geometry["coordinates"]:
            yield poly


def _ring_area_km2(ring):
    """等距圆柱投影 + shoelace，适合校区/街区等小区域近似面积。"""
    if len(ring) < 3:
        return 0.0
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    pts = [(math.radians(lng) * EARTH_R_KM * math.cos(lat0),
            math.radians(lat) * EARTH_R_KM) for lng, lat in ring]
    area = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def geometry_area_km2(geometry):
    """多边形面积（外环减洞），MultiPolygon 求和，单位 km²。"""
    total = 0.0
    for poly in _iter_polygons(geometry):
        if not poly:
            continue
        area = _ring_area_km2(poly[0])
        for hole in poly[1:]:
            area -= _ring_area_km2(hole)
        total += max(area, 0.0)
    return total


def _poly_area_km2(poly):
    """单个部件（外环减洞）的面积，用于 MultiPolygon 选主部件。"""
    if not poly:
        return 0.0
    area = _ring_area_km2(poly[0])
    for hole in poly[1:]:
        area -= _ring_area_km2(hole)
    return max(area, 0.0)


def geometry_center(geometry):
    """面积最大部件的外环顶点均值作为近似中心，返回 (lng, lat)。

    MultiPolygon（多校区/飞地合并）时，取**面积最大的部件**算中心，
    避免所有顶点均值把中心拉到空地、导致 distance 打分失真。
    注意剔除首尾闭合的重复点，避免均值偏向首点。
    """
    polys = [p for p in _iter_polygons(geometry) if p]
    if not polys:
        return None
    ring = max(polys, key=_poly_area_km2)[0]
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    if not xs:
        return None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def haversine_km(lng1, lat1, lng2, lat2):
    """两点球面距离，单位 km。"""
    r = math.radians
    dlat, dlng = r(lat2 - lat1), r(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(dlng / 2) ** 2)
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))

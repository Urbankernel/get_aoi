# -*- coding: utf-8 -*-
"""通用候选过滤：分类、父子关系、名称相关性、去重与结果取舍。

规则不绑定具体地名：先排除附属点和交通设施，再保护精确同名目标、
排除真正的子 POI，最后识别各行业通用的分支/片区变体并按 poi_id 去重。
"""
import re
from typing import Iterable, List, Optional

from ..models import Candidate
from .text import compact_display, normalize_name

# 默认排除的一级分类（点状/交通设施，通常无独立 AOI 面）
DEFAULT_EXCLUDE_TYPES = {"交通设施服务", "交通设施", "出入口"}
# 默认排除的高德 typecode（地铁站/公交站/停车场相关）
DEFAULT_EXCLUDE_TYPECODES = {"150500", "150700", "150905", "150908"}
# 名称片区后缀（如"同济大学-东区"），parent 未标全时的补充判断
SUBAREA_SUFFIX = re.compile(r"[-—(（]?[东南西北]区[)）]?$")
# 通用名称关系词，不绑定任何具体地名或行业。
RELATION_EXCLUDE_WORDS = ("附属", "内部", "附近", "周边", "对面", "旁边")
BRANCH_WORDS = {
    "校区", "院区", "园区", "馆区", "厂区", "分校", "分院", "分馆",
    "分店", "分部", "本部", "总校", "总院", "总馆", "新馆", "老馆",
    "新址", "旧址",
}
BRANCH_PATTERN = re.compile(
    r"[东南西北中](?:园|院|馆)|(?:[一二三四五六七八九十]+|\d+)期")


def _is_branch_variant(raw_query, raw_name):
    """识别通用分支/片区名称，不使用任何具体地名作为特判。"""
    if not raw_query or not raw_name.startswith(raw_query):
        return False
    if any(word in raw_name for word in RELATION_EXCLUDE_WORDS):
        return False
    suffix = raw_name[len(raw_query):]
    if not suffix:
        return False
    # “名称(人民广场馆)”等括号限定适用于所有 POI 类型。
    if suffix.startswith(("(", "（", "[", "【")):
        return True
    normalized_suffix = normalize_name(suffix)
    if BRANCH_PATTERN.search(normalized_suffix):
        return True
    # 分支词（校区/分院/分店等）必须紧跟名称之后（限定词较短，通常是
    # "地名(≤2字)+分支词(2字)"），避免"和平公园老面馒头店(杨浦分店)"里的
    # "分店"被误判成"和平公园"的分支。
    return any(0 <= normalized_suffix.find(word) <= 4
               for word in BRANCH_WORDS)


def relevant_candidates(candidates: Iterable[Candidate],
                        query_name: str) -> List[Candidate]:
    """保留精确同名和通用分支变体，不接受仅部分相似的名称。

    精确目标与校区/院区/分馆/分店/多期等变体可同时保留，交由 all/main/
    keyword 决定输出数量；附属、内部、附近设施及非前缀相似名称一律排除。
    """
    query = normalize_name(query_name)
    if not query:
        return []
    raw_query = compact_display(query_name)
    related = []
    for c in candidates:
        raw_name = compact_display(c.name)
        normalized = normalize_name(raw_name)
        if normalized == query:
            related.append(c)
        elif normalized.endswith(query):
            # 官方名常带城市/行政区前缀（如"上海和平公园""上海市同济大学"），
            # query 落在名称末尾，视为同一目标。
            related.append(c)
        elif _is_branch_variant(raw_query, raw_name):
            related.append(c)
    return related


def deduplicate_candidates(candidates: Iterable[Candidate]) -> List[Candidate]:
    """单次 Provider 检索内按 poi_id 去重，保留检索排名最前的一条。"""
    seen = set()
    unique = []
    for c in candidates:
        if c.poi_id in seen:
            continue
        seen.add(c.poi_id)
        unique.append(c)
    return unique


def _type_levels(poi_type: str) -> List[str]:
    """把 poi_type 拆成各级分类，去掉空段与首尾空格。

    高德 type / 百度 classified_poi_tag 形如 ``大类;中类;小类``，
    分隔符可能混用 ``;`` 或 ``|``；返回非空层级列表，顺序保持原字段顺序。
    """
    if not poi_type:
        return []
    return [s.strip() for s in poi_type.replace("|", ";").split(";")
            if s.strip()]


def filter_candidates(candidates: Iterable[Candidate],
                      keep_types: Optional[Iterable[str]] = None,
                      exclude_types: Optional[Iterable[str]] = None,
                      exclude_typecodes: Optional[Iterable[str]] = None,
                      skip_children: bool = True,
                      skip_subarea_name: bool = False,
                      query_name: Optional[str] = None) -> List[Candidate]:
    # 白名单各项去首尾空格（配置里逗号分隔易残留空格）
    keep = {t.strip() for t in keep_types if t.strip()} if keep_types else None
    exclude = set(exclude_types) if exclude_types else DEFAULT_EXCLUDE_TYPES
    exclude_codes = (set(exclude_typecodes) if exclude_typecodes
                     else DEFAULT_EXCLUDE_TYPECODES)
    kept = []
    normalized_query = normalize_name(query_name) if query_name else ""
    for c in candidates:
        if not c.poi_id:
            continue
        # 闸①：百度附属点
        if c.detail is not None and c.detail != 1:
            continue
        levels = _type_levels(c.poi_type)
        first_type = levels[0] if levels else ""
        # 闸①/②：分类过滤。白名单按「任一级命中」保留（支持二级/三级分类，
        # 如直接填“住宅区”“银行”）；黑名单仍按一级分类精确排除（交通设施等）。
        if keep is not None and not (set(levels) & keep):
            continue
        if first_type in exclude:
            continue
        if c.typecode and c.typecode in exclude_codes:
            continue
        # 闸③：子面跳过；但精确同名目标可能隶属于更大的住宅区/片区，
        # parent 非空不等于它是子面，不能误删用户明确查询的目标。
        is_exact_query = bool(normalized_query) and normalize_name(c.name) == normalized_query
        if skip_children and c.parent_id and not is_exact_query:
            continue
        # 补充：名称片区后缀（parent 未标全的"伪校区"）；精确查询除外。
        if (skip_subarea_name and not is_exact_query
                and SUBAREA_SUFFIX.search(c.name or "")):
            continue
        kept.append(c)
    return kept


def select_candidates(candidates: List[Candidate], want: str = "all",
                      keyword: Optional[str] = None) -> List[Candidate]:
    """候选处理：多结果取舍（业务决策"要几个"）。

    want=all      保留全部相关目标与分支变体，不再走综合排序
    want=keyword  仅保留名称含 keyword 的候选（指定校区/院区/分馆等）
    want=main     全保留，交由综合排序取第一
    """
    if want == "keyword" and keyword:
        normalized_keyword = compact_display(keyword)
        return [c for c in candidates
                if normalized_keyword in compact_display(c.name)]
    return candidates

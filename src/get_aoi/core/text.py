# -*- coding: utf-8 -*-
"""文本标准化工具：NFKC 归一、去空白/标点、大小写折叠。

供候选过滤（filter）与综合排序（matcher）共用，保证两者使用同一套
名称标准化规则，避免全半角、括号、空白等差异造成不一致判断。
"""
import re
import unicodedata

# 名称中视为等价、可忽略的标点与符号
NAME_PUNCTUATION = re.compile(r"[\s\-—_·•,，。()（）\[\]【】]")


def compact_display(value):
    """NFKC 归一 + 折叠空白 + 忽略大小写（保留标点，用于展示/关键词匹配）。"""
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", "", value).casefold()


def normalize_name(value):
    """NFKC 归一 + 去除标点/空白 + 忽略大小写（用于名称相关性判断）。"""
    value = unicodedata.normalize("NFKC", value or "")
    return NAME_PUNCTUATION.sub("", value).casefold()

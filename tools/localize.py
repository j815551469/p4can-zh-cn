#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
localize.py — 把 P4CAN / T2CAN 仪表板 HTML 的英文文案替换为中文（私有自用分支工具）

用法:
  python tools/localize.py \
      --src dashboard_source.html \
      --dict i18n/zh-CN.json \
      --out i18n/dashboard_source.zh.html \
      --report i18n/untranslated.csv

特性:
  * 只替换“可见文本节点”和 aria-label / placeholder / title 属性
  * 保留原有首尾空白、HTML 实体转义
  * 不做模糊匹配：词表 key 必须与英文原文完全一致（大小写、标点、· 都要一致）
  * 生成未翻译清单（CSV），方便按批补齐
  * 幂等：对已生成的中文文件再跑一次不会破坏内容

注意:
  * 不翻译 JSON 字段名 / API 路径 / 枚举值 —— 这些不在本工具范围内
  * 词表以英文原文为 key，上游改文案时该条会自动落入“未翻译”清单
"""
import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

ATTRS = ("aria-label", "placeholder", "title", "alt")
TAG_SPLIT = re.compile(r"(<[^>]*>)")


def esc(text: str) -> str:
    """最小化转义，保持与源文件一致的写法。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def translate_text_nodes(src: str, table: dict, missing: dict) -> str:
    parts = TAG_SPLIT.split(src)
    out = []
    for part in parts:
        if part.startswith("<"):
            out.append(translate_attrs(part, table, missing))
            continue
        if not part.strip():
            out.append(part)
            continue
        lead = part[: len(part) - len(part.lstrip())]
        trail = part[len(part.rstrip()):]
        core = part.strip()
        decoded = html.unescape(core)
        if decoded in table:
            out.append(lead + esc(table[decoded]) + trail)
        else:
            if re.search(r"[A-Za-z]{3,}", decoded):
                missing.setdefault(decoded, 0)
                missing[decoded] += 1
            out.append(part)
    return "".join(out)


def translate_attrs(tag: str, table: dict, missing: dict) -> str:
    def repl(m):
        attr, value = m.group(1), m.group(2)
        decoded = html.unescape(value)
        if decoded in table:
            return f'{attr}="{esc(table[decoded])}"'
        if re.search(r"[A-Za-z]{3,}", decoded):
            missing.setdefault(decoded, 0)
            missing[decoded] += 1
        return m.group(0)

    pattern = r'(' + "|".join(ATTRS) + r')="([^"]*)"'
    return re.sub(pattern, repl, tag)


SCRIPT_BLOCK = re.compile(r"(<script\b[^>]*>)([\s\S]*?)(</script>)", re.I)
QUOTED = [
    re.compile(r'"([^"\\\n]{2,160})"'),
    re.compile(r"'([^'\\\n]{2,160})'"),
    re.compile(r"`([^`\\$]{2,160})`"),
]


def translate_js_strings(src: str, table: dict, missing: dict) -> str:
    """在 <script> 内替换与词表完全一致的字符串字面量（跳过含转义/模板变量的）。"""
    def do_block(m):
        open_tag, body, close_tag = m.group(1), m.group(2), m.group(3)
        for pat in QUOTED:
            def repl(mm):
                inner = mm.group(1)
                if inner in table:
                    q = mm.group(0)[0]
                    return q + table[inner] + q
                return mm.group(0)
            body = pat.sub(repl, body)
        return open_tag + body + close_tag
    return SCRIPT_BLOCK.sub(do_block, src)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dict", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    src_path = Path(args.src)
    dict_path = Path(args.dict)
    out_path = Path(args.out)

    src = src_path.read_text(encoding="utf-8")
    table = json.loads(dict_path.read_text(encoding="utf-8"))

    missing: dict = {}
    result = translate_text_nodes(src, table, missing)
    result = translate_js_strings(result, table, missing)
    out_path.write_text(result, encoding="utf-8")

    # 统计
    total = len(re.findall(r">\s*[^<>\s][^<>]*<", src))
    print(f"词表条目: {len(table)}")
    print(f"已写入: {out_path}")
    print(f"未命中(去重): {len(missing)}")

    if args.report:
        report = Path(args.report)
        with report.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["en", "occurrences"])
            for text, count in sorted(missing.items(), key=lambda kv: (-kv[1], kv[0])):
                w.writerow([text, count])
        print(f"未翻译清单: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

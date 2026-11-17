#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验中文仪表板：结构一致、无逻辑串被翻译、词表已全部生效。

用法:
  python tools/verify_localization.py \
      --src i18n-audit/p4_dashboard.html \
      --out dashboard_source.html \
      --dict i18n/zh-CN.json --js-dict i18n/dashboard-js-zh.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localize as loc  # noqa: E402

CJK = r"\u4e00-\u9fff"
DATA_PATTERNS = [
    rf"===?\s*(['\"])[^'\"]*[{CJK}][^'\"]*\1",
    rf"!==?\s*(['\"])[^'\"]*[{CJK}][^'\"]*\1",
    rf"\.(includes|startsWith|endsWith|indexOf|match)\(\s*(['\"])[^'\"]*[{CJK}][^'\"]*\2",
    rf"\[\s*(['\"])[^'\"]*[{CJK}][^'\"]*\1\s*\]",
    rf"case\s+(['\"])[^'\"]*[{CJK}][^'\"]*\1",
    rf"dataset\.[\w$]+\s*=\s*(['\"])[^'\"]*[{CJK}][^'\"]*\1",
]
STRUCTURE = {
    "tags": r"<[a-zA-Z][^>]*>",
    "script_blocks": r"<script\b",
    "ids": r'id="[^"]*"',
    "lines": r"\n",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dict", required=True)
    ap.add_argument("--js-dict", default=None)
    ap.add_argument("--lang", default="zh-CN")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    src = Path(args.src).read_text(encoding="utf-8")
    out = Path(args.out).read_text(encoding="utf-8")
    problems = []

    # 1) 结构必须与英文源一一对应，避免误伤代码
    for name, pat in STRUCTURE.items():
        a, b = len(re.findall(pat, src)), len(re.findall(pat, out))
        if a != b:
            problems.append(f"结构不一致：{name} 英文 {a} / 中文 {b}")

    # 2) lang 属性
    m = re.search(r'<html\b[^>]*\blang="([^"]*)"', out, re.I)
    if not m or m.group(1) != args.lang:
        problems.append(f"<html lang> 应为 {args.lang}，实际 {m.group(1) if m else '缺失'}")

    # 3) 比较/数据上下文里不能出现中文
    for pat in DATA_PATTERNS:
        for hit in re.finditer(pat, out):
            problems.append("逻辑串被翻译：" + repr(out[max(0, hit.start() - 50):hit.end() + 30]))

    # 4) 词表必须全部生效（受保护字面量除外）
    table = json.loads(Path(args.dict).read_text(encoding="utf-8"))
    if args.js_dict and Path(args.js_dict).is_file():
        table.update(json.loads(Path(args.js_dict).read_text(encoding="utf-8")))
    protected = loc.collect_protected(src)

    # 英文源里出现、且词表有条目、却没被替换的文本节点/属性
    markup, last = [], 0
    for m in loc.SCRIPT_BLOCK.finditer(src):
        markup.append(src[last:m.start()])
        last = m.end()
    markup.append(src[last:])
    for segment in markup:
        for part in loc.TAG_SPLIT.split(segment):
            if part.startswith("<"):
                for attr, value in re.findall(r'(' + "|".join(loc.ATTRS) + r')="([^"]*)"', part):
                    if value in table and f'{attr}="{loc.esc(table[value])}"' not in out:
                        problems.append(f"属性未生效：{attr}={value!r}")
                continue
            text = part.strip()
            if text and text in table and loc.esc(table[text]) not in out:
                problems.append(f"文本节点未生效：{text!r}")

    for m in loc.SCRIPT_BLOCK.finditer(src):
        body = m.group(2)

        def walk(code):
            for start, end, quote, raw in loc.scan_literals(code):
                if raw in protected:
                    continue
                original = code[start:end]
                produced = loc.translate_code(original, table, protected, {})
                if produced != original and produced not in out:
                    problems.append(f"JS 字面量未生效：{raw[:70]!r}")

        walk(body)

    if problems:
        print(f"FAIL · {len(problems)} 个问题")
        for p in problems[:40]:
            print("  -", p)
        return 1

    rest = sum(1 for _ in re.finditer(rf"[{CJK}]", out))
    print(f"OK · 结构一致 · lang={args.lang} · 中文 {rest} 字 · 词表 {len(table)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())

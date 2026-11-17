#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
localize.py — 把 P4CAN / T2CAN 仪表板 HTML 的英文文案替换为中文（私有自用分支工具）

用法:
  python tools/localize.py \
      --src i18n-audit/p4_dashboard.html \
      --dict i18n/zh-CN.json \
      --js-dict i18n/dashboard-js-zh.json \
      --out dashboard_source.html \
      --report i18n/untranslated.csv

特性:
  * 文本节点 + aria-label / placeholder / title / alt 属性
  * <script> 内的字符串字面量（'…' / "…" / `…`），含带 ${…} 的模板串
    （模板串按 `{e0}`、`{e1}` 占位匹配，见 dashboard-js-zh.json）
  * **只翻“文案”，绝不翻“数据”**：出现在比较/匹配/对象键/成员访问/赋给
    dataset·value 等上下文里的字符串会被记为“受保护”，任何位置都不翻译。
    这条规则用于防止把 `state==='READY'` 里的 READY 翻成中文导致逻辑失效。
  * <html lang> 改为 zh-CN
  * 保留原有首尾空白、HTML 实体转义；不做模糊匹配（key 必须完全一致）
  * 生成未翻译清单（CSV），方便按批补齐
  * 幂等：对已生成的中文文件再跑一次不会破坏内容
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
SCRIPT_BLOCK = re.compile(r"(<script\b[^>]*>)([\s\S]*?)(</script>)", re.I)
LANG_ATTR = re.compile(r'(<html\b[^>]*\blang=")[^"]*(")', re.I)

# 上下文判定：命中则说明这个字面量是“数据/逻辑”而非“文案”
CMP_BEFORE = re.compile(r"(?:===?|!==?)\s*$")
CMP_AFTER = re.compile(r"^\s*(?:===?|!==?)")
CASE_BEFORE = re.compile(r"\bcase\s*$")
MATCH_BEFORE = re.compile(
    r"\.(?:includes|indexOf|lastIndexOf|startsWith|endsWith|match|matchAll|test|search|split)\s*\(\s*$")
DATA_BEFORE = re.compile(r"(?:dataset\.[\w$]+|\.value|\.id|\.key|\.name)\s*=\s*$")
MEMBER_AROUND = (re.compile(r"\[\s*$"), re.compile(r"^\s*\]"))


def esc(text: str) -> str:
    """最小化转义，保持与源文件一致的写法。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def translate_text_nodes(src: str, table: dict, missing: dict) -> str:
    """只翻 <script>/<style> 之外的文本节点与属性；脚本内容交给 translate_js。"""
    out, last = [], 0
    for m in SCRIPT_BLOCK.finditer(src):
        out.append(_translate_markup(src[last:m.start()], table, missing))
        out.append(m.group(0))
        last = m.end()
    out.append(_translate_markup(src[last:], table, missing))
    return "".join(out)


def _translate_markup(src: str, table: dict, missing: dict) -> str:
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


# ---------------------------------------------------------------- JS 字面量

def scan_literals(body: str):
    """产出 (start, end, quote, raw) —— raw 为引号内的原始文本（含转义、含 ${…}）。

    跳过 // 与 /* */ 注释；单行字符串里出现裸换行说明这不是字符串
    （多半是注释里的撇号），按“非字面量”处理，避免整段代码被吞掉。
    """
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c == "/" and body.startswith("//", i):
            j = body.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and body.startswith("/*", i):
            j = body.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c not in "'\"`":
            i += 1
            continue
        quote = c
        j = i + 1
        ok = True
        while j < n:
            ch = body[j]
            if ch == "\\":
                j += 2
                continue
            if ch == quote:
                break
            if quote != "`" and ch == "\n":
                ok = False
                break
            if quote == "`" and body.startswith("${", j):
                j = scan_expr(body, j)
                continue
            j += 1
        if not ok or j >= n:
            i += 1
            continue
        yield i, j + 1, quote, body[i + 1:j]
        i = j + 1


def scan_expr(body: str, start: int) -> int:
    """body[start:start+2] == '${'，返回匹配的 '}' 之后的下标。"""
    depth = 0
    i = start + 1
    n = len(body)
    while i < n:
        ch = body[i]
        if ch in "'\"`":
            quote = ch
            i += 1
            while i < n:
                if body[i] == "\\":
                    i += 2
                    continue
                if body[i] == quote:
                    break
                if quote != "`" and body[i] == "\n":
                    break
                i += 1
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def is_data_context(body: str, start: int, end: int) -> bool:
    before = body[max(0, start - 40):start]
    after = body[end:end + 40]
    if CMP_BEFORE.search(before) or CMP_AFTER.search(after):
        return True
    if CASE_BEFORE.search(before):
        return True
    if MATCH_BEFORE.search(before):
        return True
    if DATA_BEFORE.search(before):
        return True
    if MEMBER_AROUND[0].search(before) and MEMBER_AROUND[1].search(after):
        return True
    return False


def template_key(raw: str):
    """把 `Saving ${a} · ${b} x` 变成 ('Saving {e0} · {e1} x', ['${a}', '${b}'])。"""
    parts, exprs, pos = [], [], 0
    while True:
        idx = raw.find("${", pos)
        if idx < 0:
            parts.append(raw[pos:])
            break
        parts.append(raw[pos:idx])
        end = scan_expr(raw, idx)
        exprs.append(raw[idx:end])
        parts.append(f"{{e{len(exprs) - 1}}}")
        pos = end
    return "".join(parts), exprs


def escape_js(text: str, quote: str) -> str:
    out = text.replace("\\", "\\\\")
    out = out.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if quote == '"':
        out = out.replace('"', '\\"')
    elif quote == "'":
        out = out.replace("'", "\\'")
    else:
        out = out.replace("`", "\\`")
    return out


def render_js_value(zh: str, exprs, quote: str) -> str:
    """把翻译结果渲染成 JS 字面量内容：文本段转义，`{eN}` 原样还原为表达式。"""
    if not exprs:
        return escape_js(zh, quote)
    out, pos = [], 0
    for m in re.finditer(r"\{e(\d+)\}", zh):
        out.append(escape_js(zh[pos:m.start()], quote))
        out.append(exprs[int(m.group(1))])
        pos = m.end()
    out.append(escape_js(zh[pos:], quote))
    return "".join(out)


def norm_key(raw: str) -> str:
    """把 JS 里的转义写法还原成可读文本，便于词表用真实换行/引号书写。"""
    return (raw.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
               .replace('\\"', '"').replace("\\'", "'"))


def lookup(table: dict, key: str):
    if key in table:
        return table[key]
    return table.get(norm_key(key))


def collect_protected(src: str) -> set:
    protected = set()
    for m in SCRIPT_BLOCK.finditer(src):
        body = m.group(2)
        for start, end, _quote, raw in scan_literals(body):
            if is_data_context(body, start, end):
                protected.add(raw)
            for kind, chunk in split_template(raw) if "${" in raw else ():
                if kind == "expr":
                    protected |= collect_protected_code(chunk)
    return protected


def collect_protected_code(code: str) -> set:
    out = set()
    for start, end, _quote, raw in scan_literals(code):
        if is_data_context(code, start, end):
            out.add(raw)
        if "${" in raw:
            for kind, chunk in split_template(raw):
                if kind == "expr":
                    out |= collect_protected_code(chunk)
    return out


def split_template(raw: str):
    """把模板串正文切成 ('text', 原文) / ('expr', ${…} 内部表达式)。"""
    out, pos = [], 0
    while True:
        idx = raw.find("${", pos)
        if idx < 0:
            out.append(("text", raw[pos:]))
            return out
        out.append(("text", raw[pos:idx]))
        end = scan_expr(raw, idx)
        out.append(("expr", raw[idx + 2:end - 1]))
        pos = end


def translate_code(code: str, table: dict, protected: set, missing: dict) -> str:
    """翻译一段 JS 代码里的字面量（递归处理模板串 ${…} 内的字面量）。"""
    out, last = [], 0
    for start, end, quote, raw in scan_literals(code):
        out.append(code[last:start])
        replacement = None
        if raw not in protected:
            zh = None
            exprs = None
            if "${" in raw and quote == "`":
                key, exprs = template_key(raw)
                zh = lookup(table, key)
            else:
                zh = lookup(table, raw)
            if zh is not None:
                if exprs:
                    exprs = [translate_code(e, table, protected, missing) for e in exprs]
                replacement = render_js_value(zh, exprs, quote)
            elif re.search(r"[A-Za-z]{3,}", raw) and " " in raw.strip():
                missing.setdefault(norm_key(raw), 0)
                missing[norm_key(raw)] += 1
        if replacement is None and "${" in raw and quote == "`":
            # 整段没命中：保留模板结构，递归翻译 ${…} 里的字面量
            pieces = []
            for kind, chunk in split_template(raw):
                if kind == "text":
                    pieces.append(chunk)
                else:
                    inner = translate_code(chunk, table, protected, missing)
                    pieces.append("${" + inner + "}")
            out.append(quote + "".join(pieces) + quote)
        elif replacement is not None:
            out.append(quote + replacement + quote)
        else:
            out.append(code[start:end])
        last = end
    out.append(code[last:])
    return "".join(out)


def translate_js(src: str, table: dict, protected: set, missing: dict) -> str:
    def do_block(m):
        return m.group(1) + translate_code(m.group(2), table, protected, missing) + m.group(3)

    return SCRIPT_BLOCK.sub(do_block, src)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dict", required=True)
    ap.add_argument("--js-dict", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None)
    ap.add_argument("--lang", default="zh-CN")
    args = ap.parse_args()

    src = Path(args.src).read_text(encoding="utf-8")
    table = json.loads(Path(args.dict).read_text(encoding="utf-8"))
    if args.js_dict and Path(args.js_dict).is_file():
        table.update(json.loads(Path(args.js_dict).read_text(encoding="utf-8")))

    protected = collect_protected(src)
    missing: dict = {}
    result = translate_text_nodes(src, table, missing)
    result = translate_js(result, table, protected, missing)
    result = LANG_ATTR.sub(lambda m: m.group(1) + args.lang + m.group(2), result, count=1)

    out_path = Path(args.out)
    out_path.write_text(result, encoding="utf-8")
    print(f"词表条目: {len(table)}")
    print(f"受保护字面量(不翻译): {len(protected)}")
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_build.py — 校验固件 BIN 内嵌的仪表板是否为中文版

原理：仪表板以 gzip 流的形式嵌在固件里（index_html.h → INDEX_HTML_GZ）。
本工具在 BIN 里扫描 gzip 流，解压后与 dashboard_source.html 逐字节比对，
并统计中文字符，用于确认“编译进去的确实是中文仪表板”。

用法:
  python tools/verify_build.py --bin dist/P4-CAN-Universal-v3.29.3-zh.OTA.bin
  python tools/verify_build.py --bin build/out/P4-CAN-Universal-v3.29.3.ino.bin \
      --html dashboard_source.html

退出码: 0 = 校验通过；1 = 未找到仪表板 / 与源文件不一致 / 无中文。
"""
import argparse
import hashlib
import re
import sys
import zlib
from pathlib import Path

HAN = re.compile(r"[\u4e00-\u9fff]")
GZIP_MAGIC = b"\x1f\x8b\x08"
MAX_CANDIDATES = 64


def iter_gzip_streams(data: bytes):
    """扫描二进制里所有能完整解压的 gzip 流，产出 (offset, 解压后内容)。"""
    offset = 0
    seen = 0
    while seen < MAX_CANDIDATES:
        offset = data.find(GZIP_MAGIC, offset)
        if offset < 0:
            return
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            raw = d.decompress(data[offset:])
        except zlib.error:
            offset += 1
            continue
        if d.eof and raw:
            seen += 1
            yield offset, raw
        offset += 1


def looks_like_dashboard(raw: bytes) -> bool:
    head = raw[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def sample_chinese(text: str, limit: int = 6) -> list:
    """抽出包含中文的短片段，便于肉眼确认。"""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and HAN.search(line) and len(line) <= 120:
            out.append(line)
        if len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="校验固件 BIN 内嵌的中文仪表板")
    ap.add_argument("--bin", required=True, help="OTA BIN 或整片镜像")
    ap.add_argument("--html", help="对照用的 dashboard_source.html（建议传入）")
    ap.add_argument("--quiet", action="store_true", help="只输出结论行")
    args = ap.parse_args()

    bin_path = Path(args.bin)
    if not bin_path.is_file():
        print(f"[FAIL] 找不到文件: {bin_path}")
        return 1
    data = bin_path.read_bytes()

    canvas = next(((off, raw) for off, raw in iter_gzip_streams(data) if looks_like_dashboard(raw)), None)
    if canvas is None:
        print(f"[FAIL] {bin_path.name}: 未找到 HTML 仪表板的 gzip 流（{len(data)} 字节已扫描）")
        return 1

    offset, raw = canvas
    text = raw.decode("utf-8", "replace")
    han_count = len(HAN.findall(text))

    ok = han_count > 0
    expect = None
    if args.html:
        expect_path = Path(args.html)
        expect = expect_path.read_bytes()
        ok = ok and (expect == raw)

    if not args.quiet:
        print(f"文件      : {bin_path}")
        print(f"大小      : {len(data):,} 字节")
        print(f"仪表板偏移: 0x{offset:X} ({offset:,})")
        print(f"解压大小  : {len(raw):,} 字节")
        print(f"SHA256    : {hashlib.sha256(raw).hexdigest()}")
        print(f"中文字符  : {han_count} 个")
        if expect is not None:
            verdict = "逐字节一致" if expect == raw else f"不一致（期望 {len(expect):,} 字节）"
            print(f"对照源文件: {verdict}")
        for line in sample_chinese(text):
            print(f"  样例    : {line}")
    if ok:
        print(f"[PASS] {bin_path.name}: 内嵌中文仪表板校验通过")
        return 0
    print(f"[FAIL] {bin_path.name}: 内嵌仪表板不是中文版或与源文件不一致")
    return 1


if __name__ == "__main__":
    sys.exit(main())

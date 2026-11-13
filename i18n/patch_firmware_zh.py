# -*- coding: utf-8 -*-
"""
patch_firmware_zh.py — 把 web_api.h / serial_diag.h 里的「给人看的消息」替换成中文。

安全策略：
  * 只替换白名单里的字符串（排除 SINGLE TX / 350ms BURST / Body CAN A 这类
    可能是接口枚举值、被网页 JS 用于逻辑判断的字符串）
  * 默认 dry-run，只打印将要替换的条目；加 --apply 才真正写文件
  * 自动备份为 *.zh.bak，可用 --rollback 还原

用法：
  python i18n/patch_firmware_zh.py            # 预览
  python i18n/patch_firmware_zh.py --apply    # 应用
  python i18n/patch_firmware_zh.py --rollback # 还原
"""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["web_api.h", "serial_diag.h"]

# 只翻“纯消息/说明”，不翻枚举值
WHITELIST = [
    "CAN stop not confirmed; OTA refused. Reboot required.",
    "SSID must be 1-32 bytes",
    "SSID/password contain control characters",
    "Select a supported method that matches your vehicle's Autopilot setting.",
    "Unavailable for this vehicle connection. Body + Chassis is required for Continuous AP.",
    "Upload interrupted (connection closed or receive timeout)",
    "WiFi: Starting AP...",
    "WiFi: custom AP failed; restoring fail-safe default AP",
    "[P4-CAN WiFi] Starting ESP-Hosted C6...",
    "password must be 8-63 bytes",
    "invalid enabled",
    "missing enabled",
    "keep-BLE reset allowlist count must match the failure model",
    "rolling snapshot PRE + trigger + selected POST",
    "RAW RX ring PRE 5s + trigger + POST 2s · auto re-arm",
    "RAW AUTO LEFT OPEN 6/8 ↔ BLOCKED other state · PRE 2s + POST 2s · manual C/D PRE 5s + POST 2s",
    "ULC CONFIRM targeted RX · PRE 3s + trigger + POST 7s · 6 IDs · BODY + CHASSIS + PARTY",
    "DAS visual debug / Auto Blinker source",
    "SCCM stalk status",
    "DAS/AP state",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()

    table = json.loads((ROOT / "i18n" / "firmware_zh.json").read_text(encoding="utf-8"))
    pairs = [(en, table[en]) for en in WHITELIST if en in table]

    for name in TARGETS:
        path = ROOT / name
        if not path.exists():
            continue
        bak = path.with_suffix(path.suffix + ".zh.bak")
        if args.rollback:
            if bak.exists():
                shutil.copy2(bak, path)
                print(f"已还原 {name}")
            continue
        if args.apply and not bak.exists():
            shutil.copy2(path, bak)
        src = path.read_text(encoding="utf-8")
        hits = 0
        for en, zh in pairs:
            lit = '"' + en + '"'
            if lit in src:
                hits += src.count(lit)
                if args.apply:
                    src = src.replace(lit, '"' + zh + '"')
        if args.apply:
            path.write_text(src, encoding="utf-8")
        print(f"{name}: 可替换 {hits} 处" + ("（已写入）" if args.apply else "（预览，加 --apply 生效）"))

    print("提示：改完需重新编译；仓库里的 host/browser 测试若断言英文文案会失败，属预期。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

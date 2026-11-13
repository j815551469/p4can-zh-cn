# -*- coding: utf-8 -*-
"""把 Android 源码里的 UI 字面量替换为中文，并放入 values-zh-rCN 资源（私有自用）。"""
import json
import shutil
from pathlib import Path

ROOT = Path(r"D:\harness works\p4can-zh-fork")
AND = ROOT / "android" / "Tesla-Unlock-1.2.1"

UI = {
    "Cancel": "取消",
    "Check connection": "检查连接",
    "Close": "关闭",
    "Connect": "连接",
    "Connection": "连接",
    "Could not securely save profile. Existing profiles were kept.": "无法安全保存配置，已保留原有配置。",
    "Dashboard failed": "控制台加载失败",
    "Delete": "删除",
    "Delete device?": "删除设备？",
    "Devices": "设备",
    "Devices / connection settings": "设备 / 连接设置",
    "Manual connection": "手动连接",
    "Only this app's saved connection profile will be removed.": "只会删除本应用保存的连接配置。",
    "Permission required": "需要权限",
    "Save": "保存",
    "Secure profiles unavailable": "安全配置不可用",
    "T2CAN connection": "T2CAN 连接",
    "Tap Connect once to allow Wi-Fi access. After approval, this device will connect automatically when you reopen the app.": "点一次「连接」以允许 Wi-Fi 访问。授权后，重新打开应用时会自动连接。",
    "Wi-Fi permission was not granted. Use App permissions in connection settings, or Manual connection.": "未授予 Wi-Fi 权限。请在连接设置里打开应用权限，或使用「手动连接」。",
    "Wi-Fi ready. Opening the dashboard…": "Wi-Fi 已就绪，正在打开控制台…",
    "Wi-Fi responded, but the dashboard could not load. Check the address, WebView, VPN or Private DNS settings, then retry.": "Wi-Fi 有响应，但控制台无法加载。请检查地址、WebView、VPN 或私有 DNS 设置后重试。",
    "Wi-Fi security": "Wi-Fi 安全",
}

# 1) 覆盖 Java 字面量
count = 0
for f in (AND / "src" / "dev" / "t2can" / "unlock").glob("*.java"):
    s = f.read_text(encoding="utf-8")
    orig = s
    for en, zh in UI.items():
        lit = '"' + en + '"'
        if lit in s:
            count += s.count(lit)
            s = s.replace(lit, '"' + zh + '"')
    if s != orig:
        f.write_text(s, encoding="utf-8")
print("Java 字面量已替换:", count, "处")

# 2) values-zh-rCN/strings.xml
res = AND / "res" / "values-zh-rCN"
res.mkdir(parents=True, exist_ok=True)
src = ROOT / "i18n" / "android" / "strings.xml"
if src.exists():
    shutil.copy2(src, res / "strings.xml")
    print("已写入", res / "strings.xml")

# 3) 记录映射，便于以后回滚
(ROOT / "i18n" / "android_ui_zh.json").write_text(
    json.dumps(UI, ensure_ascii=False, indent=2), encoding="utf-8")
print("映射已保存 i18n/android_ui_zh.json")

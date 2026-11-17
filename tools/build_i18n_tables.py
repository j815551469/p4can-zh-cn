# -*- coding: utf-8 -*-
"""生成固件消息中文表 + Android values-zh-rCN/strings.xml（私有自用）"""
import csv
import json
from pathlib import Path

d = Path(r"D:\harness works\p4can\manual")
i18n = d / "i18n"

FW = {
    "350ms BURST": "350 毫秒脉冲",
    "Body CAN A": "车身 CAN A",
    "CAN stop not confirmed; OTA refused. Reboot required.": "未能确认 CAN 已停止，已拒绝 OTA。需要重启。",
    "Chassis CAN B": "底盘 CAN B",
    "DAS visual debug / Auto Blinker source": "DAS 视觉调试 / 自动转向灯来源",
    "DAS/AP state": "DAS/AP 状态",
    "NEW ZEALAND": "新西兰",
    "NO DATA": "无数据",
    "Party CAN A": "智驾 CAN A",
    "RAW AUTO LEFT OPEN 6/8 ↔ BLOCKED other state · PRE 2s + POST 2s · manual C/D PRE 5s + POST 2s": "RAW 自动：左开 6/8 ↔ 其他状态阻塞 · 前置 2 秒 + 后置 2 秒 · 手动 C/D 前置 5 秒 + 后置 2 秒",
    "RAW RX ring PRE 5s + trigger + POST 2s · auto re-arm": "RAW 接收环形：前置 5 秒 + 触发 + 后置 2 秒 · 自动续录",
    "SCCM stalk status": "SCCM 拨杆状态",
    "SETTINGS PedalMap": "设置 PedalMap",
    "SINGLE TX": "单次发送",
    "SSID must be 1-32 bytes": "SSID 必须为 1–32 字节",
    "SSID/password contain control characters": "SSID/密码包含控制字符",
    "Select a supported method that matches your vehicle's Autopilot setting.": "请选择与车辆辅助驾驶设置匹配的受支持方式。",
    "ULC CONFIRM targeted RX · PRE 3s + trigger + POST 7s · 6 IDs · BODY + CHASSIS + PARTY": "ULC 确认：定向接收 · 前置 3 秒 + 触发 + 后置 7 秒 · 6 个 ID · 车身 + 底盘 + 智驾",
    "Unavailable for this vehicle connection. Body + Chassis is required for Continuous AP.": "当前车辆连接方式不可用。连续 AP 需要「车身 + 底盘」。",
    "Upload interrupted (connection closed or receive timeout)": "上传中断（连接关闭或接收超时）",
    "WiFi: Starting AP...": "WiFi：正在启动热点…",
    "WiFi: custom AP failed; restoring fail-safe default AP": "WiFi：自定义热点失败，正在恢复默认安全热点",
    "[P4-CAN WiFi] Starting ESP-Hosted C6...": "[P4-CAN WiFi] 正在启动 ESP-Hosted C6…",
    "invalid enabled": "enabled 参数无效",
    "keep-BLE reset allowlist count must match the failure model": "保留 BLE 的重置白名单数量必须与故障模型一致",
    "missing enabled": "缺少 enabled 参数",
    "password must be 8-63 bytes": "密码必须为 8–63 字节",
    "rolling snapshot PRE + trigger + selected POST": "滚动快照：前置 + 触发 + 所选后置",
}

APK = {
    "app_name": "特斯拉解锁",
    "header_title": "特斯拉解锁",
    "status_disconnected": "未连接",
    "status_connecting": "连接中…",
    "connection_label": "T2CAN 连接",
    "connection_initial": "请连接 T2CAN 的 Wi-Fi。\\n控制台会自动打开。",
    "connection_failed": "无法连接 T2CAN。\\n请检查设备供电与 Wi-Fi。",
    "connection_loading": "已连接 T2CAN。\\n正在打开控制台…",
    "open_wifi_settings": "打开 Wi-Fi 设置",
    "retry_connection": "重试连接",
    "endpoint_version": "192.168.4.1 · App 1.2.1",
    "file_picker_unavailable": "无法打开系统文件选择器。",
    "use_dashboard_download": "请用控制台的日志下载按钮保存该文件。",
    "connect_t2can_wifi": "请在 Wi-Fi 设置中连接 T2CAN 网络。",
    "file_transfer_busy": "请等待文件传输完成后再返回。",
    "modal_open": "请使用打开对话框中的按钮。",
    "dialog_ok": "确定",
    "dialog_cancel": "取消",
}

# 1) 固件 JSON
(i18n / "firmware_zh.json").write_text(json.dumps(FW, ensure_ascii=False, indent=2), encoding="utf-8")

# 2) 固件 CSV 回填
csv_path = i18n / "firmware_strings.csv"
rows = list(csv.reader(csv_path.open(encoding="utf-8-sig")))
head, body = rows[0], rows[1:]
hit = 0
for r in body:
    if r[1] in FW:
        r[2] = FW[r[1]]
        hit += 1
with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(head)
    w.writerows(body)
print(f"固件消息: 已翻译 {hit}/{len(body)}")

# 3) Android values-zh-rCN/strings.xml
android_dir = i18n / "android"
android_dir.mkdir(exist_ok=True)
lines = ['<?xml version="1.0" encoding="utf-8"?>',
         "<!-- 私有自用中文资源：放入 Tesla-Unlock-1.2.1/res/values-zh-rCN/strings.xml -->",
         "<resources>"]
for k, v in APK.items():
    lines.append(f'    <string name="{k}">{v}</string>')
lines.append("</resources>")
(android_dir / "strings.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Android 资源:", android_dir / "strings.xml")

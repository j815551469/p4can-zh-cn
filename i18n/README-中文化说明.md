# 中文分支（私有自用）说明

> 仅用于本车私有研究，不对外分发。原项目无 LICENSE（默认保留所有权利），
> 因此本目录只保存在本地私有仓库，**不要公开、不要上传 Release**。

## 1. 目录

```
tools/localize.py              中文注入工具（文本节点 + aria-label/placeholder/title + JS 整串）
i18n/zh-CN.json                词表（key = 英文原文，value = 中文），共 788 条
i18n/zh-CN.batch2/3/4.json     分批翻译的历史批次（可留档）
i18n/dashboard_source.zh.html  生成的中文版仪表板（不要手改）
i18n/untranslated.csv          自动扫描到的未命中项（多为 JS 代码片段）
i18n/js_strings_left.txt       JS 内剩余待译候选（489 条，需人工甄别）
i18n/preview_zh_dashboard.png  中文版渲染预览
i18n-audit/p4_dashboard.html   上游原始源文件（同步上游后替换）
i18n-audit/dashboard_strings_zh.csv  788 条文案全表（中文列已 100% 填满）
```

## 2. 用法

```bash
# 1) 同步上游源文件 -> i18n-audit/p4_dashboard.html
# 2) 生成中文版
python tools/localize.py \
  --src i18n-audit/p4_dashboard.html \
  --dict i18n/zh-CN.json \
  --out i18n/dashboard_source.zh.html \
  --report i18n/untranslated.csv
# 3) 浏览器打开生成的 html 预览
```

## 3. 进度（2026-11-13）

| 范围 | 状态 |
|---|---|
| 仪表板静态文案（788 条） | ✅ **100% 已翻译** |
| HTML 属性（aria-label / placeholder / title） | ✅ 已覆盖 |
| JS 整串（与词表完全一致的） | ✅ 已覆盖 |
| JS 动态提示（档案状态/连接/AP 状态等） | ✅ 已补 30+ 条 |
| JS 拼接片段（`js_strings_left.txt`，489 候选） | ⏳ 约 100 条是真 UI 文案，待人工甄别 |
| 固件 API 消息（`web_api.h` 等，28 条） | ✅ **28/28 已翻译**（`firmware_zh.json`） |
| Android 资源（18 条） | ✅ **18/18**（`android/strings.xml`） |
| Android 硬编码（约 60 处 Java 字符串） | ⏳ 待抽资源 |
| 固件接入（embed / build 脚本切换） | ⏳ 待改构建链 |
| 真机 + 编译验证 | ⏳ 需要 Arduino-ESP32 / Android SDK 环境 |

## 4. 术语表（必须统一）

| 英文 | 中文 |
|---|---|
| Profile | 车型档案 |
| Vehicle functions | 车辆功能 |
| Nag Killer | 握持提示抑制 |
| Advanced EAP | 增强版 EAP |
| Summon | 智能召唤 |
| TLSSC | 红绿灯与停车标志控制 |
| DMS | 驾驶员监控 |
| Injection | 注入 |
| Dashboard | 控制台 |
| CAN capture | CAN 抓包 |
| STOCK | 原车 |
| OFF | 关闭 |
| TX / RX | 发送 / 接收 |
| HO | 握持（Hands-On） |
| ALC | 自动变道 |

## 5. 不要翻译的东西

- JSON 字段名、API 路径（`/api/...`）
- 枚举值（`BODY`/`PARTY`/`CHASSIS` 作为数据出现时）
- CAN 信号名、报文 ID（`0x3F8`、`UI_driverAssistControl`）
- 日志字段名、错误码
- 代码注释

## 6. 接入固件

上游构建链：`dashboard_source.html` →（`tools/build_dashboard.py`）→（`tools/embed_dashboard.py`）→ `index_html.h`（gzip）。

- **方式 A（改动最小）**：把 `embed_dashboard.py` 的输入换成 `dashboard_source.zh.html`。
- **方式 B（双语）**：同时嵌入 en/zh 两份，按 NVS `lang` 返回对应一份（flash 约翻倍，P4 32MB 可承受）。

## 7. 后续路线

1. JS 拼接片段人工甄别（`js_strings_left.txt`）→ 补进词表
2. 固件消息表：`web_api.h` / `serial_diag.h` → `i18n_strings.h`（中英双表 + NVS 开关）
3. APK：`values-zh-rCN/strings.xml` + 抽硬编码 + 补 Gradle 工程
4. 真机验证：320/390/430px 三档宽度截图查溢出

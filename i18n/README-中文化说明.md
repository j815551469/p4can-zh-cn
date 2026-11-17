# 中文分支（私有自用）说明

> 仅用于本车私有研究，不对外分发。原项目无 LICENSE（默认保留所有权利），
> 因此本目录只保存在本地私有仓库，**不要公开、不要上传 Release**。

## 1. 文件

| 文件 | 作用 |
|---|---|
| `tools/localize.py` | 中文注入工具：文本节点 + aria/placeholder/title 属性 + JS 字面量（含 `` `${…}` `` 模板串） |
| `i18n/zh-CN.json` | **静态文案词表**（文本节点、属性、静态 JS 串），key = 英文原文 |
| `i18n/dashboard-js-zh.json` | **动态文案词表**（JS 运行时拼的提示/状态/确认框），模板串用 `{e0}`/`{e1}` 占位 |
| `tools/verify_localization.py` | 校验器：结构一致、无逻辑串被翻译、词表全部生效、`lang=zh-CN` |
| `dashboard_source.html` | 生成物（中英文对照唯一来源是 `manual/i18n-audit/p4_dashboard.html`） |

> 仓库外的英文源文件在 `D:\harness works\p4can\manual\i18n-audit\p4_dashboard.html`。
> **不要手改 `dashboard_source.html`**——下次重新生成会被覆盖。

## 2. 重新生成

```powershell
cd 'D:\harness works\p4can\repo'
python tools\localize.py `
  --src ..\manual\i18n-audit\p4_dashboard.html `
  --dict i18n\zh-CN.json `
  --js-dict i18n\dashboard-js-zh.json `
  --out dashboard_source.html `
  --report ..\manual\i18n\untranslated.csv

# 必须过校验（结构/逻辑串/词表生效/语言标记）
python tools\verify_localization.py `
  --src ..\manual\i18n-audit\p4_dashboard.html `
  --out dashboard_source.html `
  --dict i18n\zh-CN.json --js-dict i18n\dashboard-js-zh.json

# 再重建内嵌 gzip 头
python tools\build_dashboard.py
```

`--js-dict` 可省略（没有它时只翻静态文案）。生成是确定性的：同一份英文源 +
两份词表，产物逐字节一致，可放心重复执行。

## 3. 硬规则：只翻“文案”，绝不翻“数据”

工具会先扫一遍英文源，把出现在下列位置的字符串记为**受保护**，任何地方都不翻译：

- 比较/匹配上下文：`===` `!==` `==` `!=`、`case`、`.includes(` `.indexOf(` `.startsWith(` 等
- 数据赋值：`dataset.x=`、`.value=`、`.id=`、`.key=`、`.name=`
- 成员访问：`obj['KEY']`
- 键名/页面 id（`panelDevice`、`settings-lite` 等）

这条规则来自一次真实事故：早期版本把 `state==='READY'` 里的 `READY` 翻成「就绪」、
把 `__p4CanBName==='CHASSIS'` 翻成「底盘」、把 `event.key==='Home'` 翻成「首页」，
导致状态判断、R79 路由、下拉键盘导航全部失效。现在这类字面量一律保留英文
（状态值本来就是固件返回的枚举，界面上显示 READY/ACTIVE 等与数据一致）。

`verify_localization.py` 会再查一遍“中文是否出现在比较里”，命中即失败。

## 4. 术语（统一）

| 英文 | 中文 | 备注 |
|---|---|---|
| Profile | 车型档案 | |
| Vehicle functions | 车辆功能 | |
| Nag / NAG | 握持提示 / 脱手提醒 | 方向盘扭力提醒 |
| Nag Killer | 握持提示抑制 | |
| Summon | 智能召唤 / 召唤 | |
| TLSSC | 红绿灯与停车标志控制 | 快捷块因宽度只写「红绿灯控制」 |
| DMS / Driver Monitoring | 驾驶员监控 | |
| ISA | ISA 限速提醒 | 智能限速辅助 |
| ALC | 自动变道（ALC） | 标志位名保留 ALC |
| ULC | 免确认变道（ULC） | `UI_ulcStalkConfirm` |
| HO | 握持（Hands-On） | |
| Injection | 注入 | |
| Dashboard | 控制台 | |
| CAN capture | CAN 抓包 | |
| STOCK | 原车 | |
| OFF / ON | 关闭 / 开启 | |
| TX / RX | 发送 / 接收 | |
| BODY / CHASSIS / PARTY | 车身 / 底盘 / 智驾 | 总线角色 |
| epoch | 世代 | |

## 5. 不要翻译

JSON 字段名、API 路径（`/api/...`）、枚举值（`READY`/`CHASSIS`/`SNAPSHOT` 等）、
CAN 信号名与报文 ID、日志字段、代码注释、下载文件名（`*.csv`）。

## 6. 现状（2026-11-17 复核）

| 范围 | 状态 |
|---|---|
| 仪表板静态文案 | ✅ 889 条词表，全部生效 |
| 仪表板 JS 动态文案 | ✅ 232 条（含 6 段配对向导 HTML 模板） |
| aria-label / placeholder | ✅ 已补 24 条 |
| 固件 API 消息（`web_api.h`） | ✅ 20 条，2026-11-17 修了「左开」「WiFi/C6」等 |
| Android 资源 | ✅ 18 条（`android/strings.xml`） |
| 真机 / 三档宽度截图 | ⏳ 需硬件（本机无 Playwright） |

## 7. 上游更新后怎么同步

1. 用新上游的 `dashboard_source.html` 覆盖 `manual/i18n-audit/p4_dashboard.html`
2. 重跑第 2 节两条命令
3. 看 `untranslated.csv`：新文案会落进来，按批补词表
4. 若上游改了已有英文原文，旧词条自动失效（key 对不上即不再翻译），不会误伤

# P4CAN 三路 CAN 方案 · 特斯拉 Model Y（2021）使用与安装

ESP32-P4 开发板 + 3 × SN65HVD230 → 特斯拉 Model Y（2021 款 / SOP6）X179 三总线。
读取车身/底盘/智驾三组 CAN，按固件规则补发与改写特定报文，从而改变车辆的部分辅助驾驶行为。

> [!WARNING]
> **仅供台架与封闭私有场地研究 · 严禁公共道路 · 禁止商用与再分发 · 风险自负**
>
> 本仓库与 Tesla, Inc. 无关，未获其授权。改动 ADAS、转向或驾驶员监控相关行为，在中国及
> 多数地区受法规约束，且通常导致厂商保修失效、可能影响保险理赔。
>
> 使用前请务必阅读 **[DISCLAIMER.md](DISCLAIMER.md)** 与 **[LICENSE](LICENSE)**。
> 下载、编译、刷写或使用本仓库任何内容，即视为你已阅读并同意其全部条款。

> 本仓库是上游 [P4can-universal-unlock](https://github.com/06066060606060/P4can-universal-unlock)
> 的中文分叉：**固件与仪表板中文化** + **P4 + C5 协处理器适配**（原固件按 C6 编译，在这块
> 板上会 abort）。上游英文 README 保留为 [README.en.md](README.en.md)。

完整安装手册（22 页，含测量值、验收表、故障树；**示意图全部重绘，不含厂商原图**）：
**[docs/P4CAN-2021-ModelY-安装手册-公开版-v1.pdf](docs/P4CAN-2021-ModelY-安装手册-公开版-v1.pdf)**
手册只讲硬件安装与验证，**不包含报文参数、位定义与功能开启方法**。
本 README 是它的浓缩介绍，细节以手册为准。

---

## 0 · 这是什么

车上有三条「内部对讲机频道」，分别叫 **VH（车身）**、**CH（底盘）**、**PARTY（智驾）**。
车里的电脑靠它们互相说话：打转向灯、请求变道、汇报方向盘力矩、报告 AP 状态……

这个项目做的事，就是在三条线上各接一台「会说话的设备」：用 ESP32-P4 读这些数据，
并按固件规则补发、改写其中几条特定的报文，于是车的行为就变了（转向灯自动打、
握持提示消失等）。

| 总线 | 管什么 | 本方案里对应功能 |
|---|---|---|
| VH / Body | 灯光、门锁、雨刮、座椅、车身控制器 | Advanced EAP 自动打转向灯、部分设置项 |
| CH / Chassis | 转向（EPAS）、制动 | Summon 解锁、R79 相关、转向灯路由 |
| PARTY | DAS / AP 状态、方向盘力矩（0x370） | Nag-killer（解除「请握方向盘」） |

**车型档案（Profile）**：2021 款 Model Y（国产 VIN 以 `LRW` 开头 / 进口 `5YJ`）属于
`Model Y Legacy`（代号 Y），转向灯是拨杆式 → 选 `STALK`。选错的话固件会保持「安全锁定」，
一个功能都不会生效。

难度：中等（会剥线、会用万用表、会照命令敲字即可，不需要写代码）。
采购 3–7 天；改造+线束 3–4 小时；台架 1 小时；上车 2–3 小时。

## 1 · 原理一句话

ESP32-P4 内部有 3 个 CAN 控制器（TWAI 0/1/2）→ 每个接一颗 SN65HVD230
（把 3.3 V 逻辑电平变成 CAN 差分信号）→ 分别接到车上 X179 连接器的三组总线
→ 手机连板子的 Wi-Fi 看 Dashboard 下指令。

```
        2021 Model Y（Legacy Y · LRW/5YJ）
        X179 · CAN Port（20 腔，只用 7 个）
        VH 9/10 · CH 13/14 · PARTY 2/3 · GND 20
                    │  3 × 双绞（500 kbit/s）
                    ▼
        3 × SN65HVD230（拆 120Ω · RS→GND · 3.3V）
                    │  GPIO20/21 · 22/23 · 26/27
                    ▼
        ESP32-P4 DevKit（32MB Flash · PSRAM · post-v3）
                    │  5V ← 手套箱 USB
                    ▼
        手机 Dashboard · 192.168.4.1 · SSID T2CAN-**** / 密码 12345678
        S3XY Button（可选，BLE，最多 3 个）
```

## 2 · 物料（照单买，不会错）

三条采购原则：

1. 板子必须 **32 MB Flash + PSRAM + post-v3 硅片**；
2. 收发器必须 **3.3 V 且 120 Ω 可拆**（TJA1050、MCP2551 是 5 V 器件，直接排除）；
3. X179 优先买**成品取线束**，不要自己破原车线。

| 物料 | 关键规格 | 数量 |
|---|---|---|
| ESP32-P4 开发板 | post-v3、32 MB Flash、PSRAM、USB-C、2.54 排针 | 1 |
| SN65HVD230 模块 | 蓝色小板 6 脚、3.3 V、≥1 Mbps、板载 120 Ω 可拆、带 RS | 3 |
| X179 取线束 | 成品公母对插（2021 Model Y，蓝色 20 芯插头） | 1 套 |
| USB-C 数据线 | USB 2.0 数据线（不是纯充电线） | 1–2 |
| 手套箱取电 | USB-A → USB-C | 1 |
| 双绞线 | 0.35 mm²（22 AWG），每组 1.5 m | 3 组 |
| 电源线 / 3.3 V 线 | 0.5 mm² 红黑；0.25 mm² 红 | 各 1 |
| 热缩管 / 绒布胶带 / 扎带 / 标签 | Φ2/Φ4/Φ6；Tesa 51608；2.5×100；防水标签 | 若干 |

工具：数字万用表、330–350 °C 恒温烙铁、吸锡带+镊子、剥线钳、斜口钳、
塑料撬棒、T20/T25 花键、10 mm 套筒、USB 电流表。

## 3 · 接线（逐针）

P4 侧共 9 根：

| P4 引脚 | 功能 | 接到 |
|---|---|---|
| GPIO20 / GPIO21 | TWAI 0 TX / RX | #1 VH 的 TXD / RXD |
| GPIO22 / GPIO23 | TWAI 1 TX / RX | #2 CH 的 TXD / RXD |
| GPIO26 / GPIO27 | TWAI 2 TX / RX | #3 PARTY 的 TXD / RXD |
| 3V3 | 3.3 V 输出 | 三颗 VCC（**不要接 5 V**） |
| GND | 地 | 三颗 GND + X179-20，**单点共地** |
| 5V | 供电输入 | 手套箱 USB |

X179 侧（车端线色为准）：

| 针 | 官方信号 | 线色 | 接到 |
|---|---|---|---|
| 9 | VH CAN P | 棕/白 | #1 CANH |
| 10 | VH CAN N | 棕 | #1 CANL |
| 13 | CH CAN P | 深绿/白 | #2 CANH |
| 14 | CH CAN N | 绿 | #2 CANL |
| 2 | PARTY CAN P | 黄/浅蓝 | #3 CANH |
| 3 | PARTY CAN N | 黄 | #3 CANL |
| 20 | GND | 黑 | 公共地 |

收发器改造（三颗都做）：拆掉板载 120 Ω → `CANH–CANL > 1 kΩ`；RS 脚接 GND（高速模式）；
VCC 只接 3.3 V。改完三条硬指标都过才允许上电。

## 4 · 供电

| 设备 | 典型 | 峰值 |
|---|---|---|
| ESP32-P4（含 Wi-Fi） | 180–300 mA | 500 mA |
| SN65HVD230 ×3 | ≈30 mA | 60 mA |
| 合计 | ≈0.25 A | ≈0.6 A |

**方案 A（推荐）**：手套箱 USB 5 V，完全免改线、可逆，车辆休眠自动断电。
**方案 B（备选）**：X181-16 ACC 12 V → 1 A 保险丝 → 降压模块调到 5.1 V → P4。

## 5 · 刷机（Windows）

固件需要自己编译，**本仓库不随附 `.bin` 成品镜像**（合规考虑，详见本节末尾）。

```powershell
# 1) 编译（产出 build/out/*.ino.bin 与 *.ino.merged.bin）
$env:ARDUINO_DIRECTORIES_DATA='C:\arduino-data2'
python tools/build_firmware.py

# 2) 刷写
python --version                     # 3.11+
pip install --upgrade esptool
esptool.py --chip esp32p4 -p COM5 flash_id    # 必须显示 32MB
esptool.py --chip esp32p4 -p COM5 -b 460800 write_flash `
  --flash_mode qio --flash_size 32MB 0x0 build\out\P4-CAN-Universal-v3.29.3.ino.merged.bin
```

- 地址必须是 **0x0**；`--chip` 必须是 `esp32p4`。
- 刷完 30–90 秒内应出现热点 `T2CAN-****`，连上后打开 <http://192.168.4.1>。
- **P4+C5 板**（C5-MINI-1U）必须先按
  [i18n/交接-下一步C5适配.md](i18n/交接-下一步C5适配.md) 重编 ESP-Hosted 库，否则启动会
  `Identified slave [esp32c5] != Expected [esp32c6]` 并 abort；C6 板无需此步骤。
- 历史构建记录（尺寸与 SHA256）见 [dist/BUILD-INFO.md](dist/BUILD-INFO.md)，可用于比对你
  自己的编译结果；同一份源码不保证逐字节相同（`__DATE__`/`__TIME__` 会进镜像）。

### 为什么仓库里没有成品固件

开箱即刷的镜像会让“拿到就能上车”变得没有门槛，而被改写的正是转向、驾驶员监控这类安全
相关功能。本仓库因此只提供源码与构建脚本：想用的人至少要自己搭一遍工具链、读一遍手册，
这一步本身就是必要的门槛。

## 6 · 首次开机与 Profile

选 `Model Y Legacy（Y）` + `STALK` + 拓扑 `Body(VH)+Chassis` 或 `Party+Chassis`，
保存后重启。**fail-closed**：没保存有效 Profile 前，CAN 发送、注入、蓝牙全部禁用，
只有 Wi-Fi 和 Profile Setup 可用——所以顺序是：先选车型，再接线测试。

Dashboard 页面：`HOME`（RX 计数是否在涨、TX Fail 是否为 0）、`DEVICES`（S3XY）、
`SETTINGS`（功能开关）、`LAB`（实验与抓包，只看不改）。

## 7 · 能开的功能（一次只开一项）

| 功能 | 用哪路 | 开启后怎么验证 | 风险 |
|---|---|---|---|
| Nag-killer | PARTY | 开 AP 后 30–60 s 内不再出现「请轻转方向盘」 | 中 |
| Advanced EAP（自动打灯） | VH | 变道请求时转向灯自动亮，可随时取消 | 中 |
| EU Unlock / R79 | CH | LAB 里 R79 位状态变化（国内意义有限） | 中 |
| Summon 解锁 | CH | 静止时召唤相关状态位变化 | 高 |
| ISA 提示音抑制 | VH | 限速提示音变化 | 低 |
| 关闭 DMS（LAB） | PARTY | 摄像头监控提示消失 | 中 |
| Country/Map 伪装 | VH | 区域设置变化 | 中 |
| **TLSSC 激活/恢复** | — | **不要开**：官方警告，非「已封」车辆会立刻被封 | 极高 |

逐项开启法：每开一项 → 静止观察 10–15 分钟 → 记录 → 关闭或保留 → 再开下一项。

## 8 · 安全红线

1. 只在台架或封闭私有场地测试，**公共道路绝对不试**。
2. 接线前先断电（中控屏「安全 → 关闭电源」并等 8–10 分钟），不要带电插拔 X179。
3. 手上永远留一个独立断电手段（拔 USB 供电 / 拔 X181 取电线）。
4. 车辆必须静止、P 挡、脚踩刹车时才逐项开功能。
5. 不要相信「Last Write Check」＝ECU 已接受；只有车的实际行为才算验证。

## 9 · 风险与法规

- **保修**：Tesla 服务公告写明非授权改装不属保修范围，需签 SC-18-00-008 才能做
  Modified Service，Tesla 不承担后果。
- **封禁**：TLSSC Restore 会让非「已封」车辆立刻被封。
- **法规**：改动 ADAS/转向行为上路，在中国及多数地区存在法律风险；仅供研究与私有场地验证。
- **保险**：改装未申报可能影响理赔。

> 本手册与固件不构成任何使用许可。若不确定上述风险，请止步于台架阶段。

---

## 本分叉做了什么

| 项 | 位置 | 说明 |
|---|---|---|
| 中文仪表板 | `dashboard_source.html` / `index_html.h` | 865 条词表，逐字节校验编译进固件 |
| 中文 APK 源码 | [`android/`](android/) | 界面中文化；APK 需自行构建 |
| P4 + C5 适配 | [`i18n/交接-下一步C5适配.md`](i18n/交接-下一步C5适配.md) | 重编 ESP-Hosted 为 C5 目标，修复启动 abort |
| 构建方式 | [`tools/build_firmware.py`](tools/build_firmware.py) | 仓库直编，内含中文仪表板与 TinyCrypt 契约校验 |
| 构建记录 | [`dist/BUILD-INFO.md`](dist/BUILD-INFO.md) | 历史产物的尺寸与 SHA256，供比对；**不含二进制** |

构建：

```powershell
$env:ARDUINO_DIRECTORIES_DATA='C:\arduino-data2'
python tools/build_firmware.py
```

## 参考资料

- 上游固件与官方接线图：<https://github.com/06066060606060/P4can-universal-unlock>
- 上游 Release 3.29.3：<https://github.com/06066060606060/P4can-universal-unlock/releases/tag/3.29.3>
- X181 官方公告 CD-20-17-001 R4：<https://service.tesla.cn/docs/ServiceBulletins/External/CD/>
- Model Y SOP6 电气参考（X179 针脚与位置图）：<https://service.tesla.cn/docs/ModelY/ElectricalReference/prog-202/connector/x179/>

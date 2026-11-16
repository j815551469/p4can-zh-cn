# 构建记录 · P4-CAN-Universal v3.29.3 (zh-CN)

构建时间：2026-11-13 16:08（本地）
构建来源：**本仓库源码**（`p4can-zh-fork` · 分支 `i18n/zh-cn` · 固件源码与提交 `82f1d71` 一致）
构建命令：`python tools/build_firmware.py`（见下，不要用别的目录编）
构建环境：Windows · arduino-cli 1.6.0 · ESP32 core **3.3.12**
数据目录：`C:\arduino-data2`（离线索引，工具链来自官方归档）

## 目标

```
esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio
```

## 结果

| 项 | 值 |
|---|---|
| 程序占用 | 1,393,208 B / 4,718,592 B（29%） |
| 全局变量 | 77,816 B / 327,680 B（23%） |
| 编译结果 | exit 0，无错误 |

## 产物

| 文件 | 大小 | SHA256 | 用途 |
|---|---|---|---|
| `P4-CAN-Universal-v3.29.3-zh.fullflash.bin` | 33,554,432 B | `00c3f97de038dfbb9f1d4b6b49e1f4c86fb3442e6628dbc41d5b3b08f1a19a51` | **整片镜像，烧到 0x0** |
| `P4-CAN-Universal-v3.29.3-zh.OTA.bin` | 1,393,920 B | `4dc79b0a6837c26fe20390366cd084524d76557fffd0417d9f9683799ee078b3` | 应用镜像（OTA/仅应用分区） |
| `SHA256SUMS.txt` | — | — | 校验和 |

镜像布局核对（fullflash.bin，实测）：

```
0x0000  FF FF FF FF ...   空白
0x2000  E9 03 02 5F ...   ESP 镜像头（bootloader）
0x8000  AA 50 01 02 ...   分区表
0x10000 E9 08 02 5F ...   应用程序（含中文仪表板）
```

## 中文化验证

```
python tools/verify_build.py --bin dist/P4-CAN-Universal-v3.29.3-zh.OTA.bin \
    --html dashboard_source.html
```

实测输出：仪表板 gzip 流位于 `0x371A0`（整片镜像里是 `0x471A0`），解压 365,511 字节，
与 `dashboard_source.html` **逐字节一致**（HTML SHA256 `3a39019e…`），含 **7,721 个汉字**。
（旧文档手工找偏移的写法已由该工具取代。）

## 与 2026-11-13 14:35 旧产物的差异（重要）

旧 `dist/` 的两份 BIN **不是从本仓库源码编出的**：它编自
`D:\harness works\P4-CAN-Universal-v3.29.3`——一份不完整的副本，缺少
`src/p4_tinycrypt/`（上游自带的 TinyCrypt 覆写实现）、`fonts/` 与 `tests/`。

后果与本次修正：

- 旧固件的 BLE 配对加密用的是 ESP-IDF 预编译 `libbt.a` 里的 TinyCrypt 实现；
  本仓库源码编出的固件用的是 `src/p4_tinycrypt/` 里的实现（map 文件可见
  `sketch/src/p4_tinycrypt/ecc.c.o` 提供 `EccPoint_mult` 等符号）。
- 两者差异 **仅限 TinyCrypt ECC 相关符号**（`.flash.text` +1,054 B，镜像 +2,000 B）；
  中文仪表板内容完全相同。
- 本目录的 BIN 已替换为**仓库直编**产物，可复现、可追溯；旧产物仍可从
  git 提交 `50b82a2` 取回作对照。

## TinyCrypt 契约校验（项目自带约束）

仓库里的 `tools/verify_p4_crypto.py` 与 `tests/test_p4_crypto_link.py` 规定：
`EccPoint_mult`、`uECC_shared_secret`、`uECC_make_key` 等必须由
`sketch/src/p4_tinycrypt/` 下的 `.o` 提供，且 map 中一旦出现
`libbt.a(ecc.c.obj)` 等 stock 成员就直接判失败（`ble_sm_alg_gen_dhkey` 例外，保留 NimBLE 原生适配）。

实测：

| 产物 | 结果 |
|---|---|
| 本目录（仓库直编） | ✅ 7 个符号全部来自 `src/p4_tinycrypt/*.o`，NimBLE 适配器未被替换 |
| 旧的 14:35 产物 | ❌ `Stock TinyCrypt archive member still linked: ecc.c.obj` |

`tools/build_firmware.py` 已把这项 owner 校验内置到构建流程里（Windows 路径先归一化再比对）。

> 注意：`tools/verify_p4_crypto.py` 完整版还会比对上游源文件 SHA256，但那是按 LF
> 工作区写的；本机 `core.autocrlf=true` 会把源码检出成 CRLF，从而误报
> `TinyCrypt source differs from upstream`。LF 归一化后哈希与 `UPSTREAM.json`
> 完全一致（已验证），源码本身没有问题。

## 可复现性

- 源码对应关系可复现：任意一份本仓库克隆，跑 `python tools/build_firmware.py`
  都应得到等价固件（同 core、同 FQBN、同 `dashboard_source.html`）。
- 脚本内置两项**内容级**校验：内嵌仪表板与 `dashboard_source.html` 逐字节比对、
  TinyCrypt 符号 owner 契约；两项都过才算成功。
- **SHA256 不保证每次相同**：ESP32 core 的 `chip-debug-report.cpp` /
  `firmware_msc_fat.c` 会把 `__DATE__` / `__TIME__` 编进镜像，每次编译必然变化。
  需要“内容级”校验时用 `tools/verify_build.py`，不要只比整包哈希。

## 二、中文 Android APK

| 项 | 值 |
|---|---|
| 产物 | `Tesla-Unlock-1.2.1-zh.apk`（181,105 B） |
| 签名 | 自签名，DN=`CN=T2CAN ZH Private`（**不是**作者原签名） |
| 中文验证 | `classes.dex` 含中文界面字符串（手动连接 / 控制台加载失败 / 取消…）；`resources.arsc` 含 `values-zh-rCN`（特斯拉解锁） |
| 构建 | JDK 23 + Android SDK Platform 36 + Build Tools 36.0.0（`tools/build.py` 已补 Windows `.exe` 支持） |

安装注意：

- 签名与官方 APK 不同，**先卸载官方版再装**，否则报签名冲突。
- APK 不含固件、不改功能，只做界面中文化。

## 烧录

```bash
esptool.py --chip esp32p4 -p COM5 -b 460800 \
  write_flash --flash_mode qio --flash_size 32MB \
  0x0 P4-CAN-Universal-v3.29.3-zh.fullflash.bin
```

或用 Espressif Flash Download Tool / SerialFlow ESP Flash（地址 `0x0`）。

## 注意

- 原项目无 LICENSE，**仅限私有自用**，请勿公开分发。
- 这是 **BETA**（上游 v3.29.3 标注），上车前先在台架验证。
- 上游若更新：按 `i18n/构建与联调.md` 重跑注入 → `python tools/build_firmware.py`。

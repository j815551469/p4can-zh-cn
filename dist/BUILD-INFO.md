# 构建记录 · P4-CAN-Universal v3.29.3 (zh-CN)

构建时间：2026-11-13 14:4x（本地）
构建环境：Windows · arduino-cli 1.6.0 · ESP32 core **3.3.12**
数据目录：`C:\arduino-data2`（离线索引，工具链来自官方归档）

## 目标

```
esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio
```

## 结果

| 项 | 值 |
|---|---|
| 程序占用 | 1,391,218 B / 4,718,592 B（29%） |
| 全局变量 | 77,816 B / 327,680 B（23%） |
| 编译结果 | exit 0，无错误 |

## 产物

| 文件 | 大小 | 用途 |
|---|---|---|
| `P4-CAN-Universal-v3.29.3-zh.fullflash.bin` | 32.0 MB | **整片镜像，烧到 0x0** |
| `P4-CAN-Universal-v3.29.3-zh.OTA.bin` | 1.36 MB | 应用镜像（OTA/仅应用分区） |
| `SHA256SUMS.txt` | — | 校验和 |

镜像布局核对（fullflash.bin）：

```
0x0000  FF FF FF FF ...   空白
0x2000  E9 03 02 5F ...   ESP 镜像头（bootloader）
0x8000  AA 50 01 02 ...   分区表
0x10000 E9 08 02 5F ...   应用程序（含中文仪表板）
```

## 中文化验证

在 `.ino.bin` 中定位到内嵌仪表板 gzip 流（偏移 `0x371EC`），解压 **365,511 字节**，
包含中文字符串（`车型档案状态不可用` 等）→ 确认编译进去的是中文版仪表板。

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
- 上游若更新，重新执行：`tools/localize.py` → `tools/build_dashboard.py` → `arduino-cli compile`。

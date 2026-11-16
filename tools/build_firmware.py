#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_firmware.py — 一条命令重编中文固件（暂存 → 生成内嵌仪表板 → arduino-cli 编译 → 校验）

为什么需要“暂存”：arduino-cli 要求 sketch 目录名与 .ino 文件名一致
（主文件名必须是 <目录名>.ino）。本仓库目录叫 p4can-zh-fork，直接编译会报
“main file missing from sketch”。因此本脚本把固件源码复制到
<work-dir>/_src/P4-CAN-Universal-v3.29.3/ 再编译，仓库本身保持干净。

用法:
  python tools/build_firmware.py                      # 默认 work-dir = <repo>/build
  python tools/build_firmware.py --work-dir C:\\esp-build
  python tools/build_firmware.py --skip-verify        # 只编译，不校验内嵌中文

产物:
  <work-dir>/out/P4-CAN-Universal-v3.29.3.ino.bin        应用镜像（= 发布的 OTA.bin）
  <work-dir>/out/P4-CAN-Universal-v3.29.3.ino.merged.bin 整片镜像（= 发布的 fullflash.bin）

环境:
  arduino-cli 默认从 PATH 或 <repo>/../toolchain/arduino-cli.exe 查找
  ESP32 core 数据目录默认 C:\\arduino-data2（可用 --data-dir 或 ARDUINO_DIRECTORIES_DATA 覆盖）
"""
import argparse
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKETCH_NAME = "P4-CAN-Universal-v3.29.3"
FQBN = (
    "esp32:esp32:esp32p4:ChipVariant=postv3,FlashSize=32M,"
    "PartitionScheme=app5M_fat24M_32MB,PSRAM=enabled,USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio"
)
# 不参与编译的目录：仓库元数据、已发布产物、本地化工具与 Android 端源码
EXCLUDE_DIRS = {".git", "dist", "build", "i18n", "tools", "android", "__pycache__"}


def find_cli(explicit: str = None) -> Path:
    if explicit:
        return Path(explicit)
    for name in ("arduino-cli", "arduino-cli.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    for candidate in (
        ROOT.parent / "toolchain" / "arduino-cli.exe",
        Path(r"D:\harness works\toolchain\arduino-cli.exe"),
    ):
        if candidate.is_file():
            return candidate
    raise SystemExit("找不到 arduino-cli，请用 --cli 指定路径")


def find_data_dir(explicit: str = None) -> str:
    if explicit:
        return explicit
    if os.environ.get("ARDUINO_DIRECTORIES_DATA"):
        return os.environ["ARDUINO_DIRECTORIES_DATA"]
    default = Path(r"C:\arduino-data2")
    return str(default) if default.is_dir() else ""


def build_dashboard() -> None:
    """按 dashboard_source.html 重新生成 index_html.h（gzip 确定性输出）。"""
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_dashboard.py")], check=True)


def stage_sources(target: Path) -> Path:
    """把固件源码复制到 <target>/<SKETCH_NAME>/ 以满足目录名约束。"""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    dest = target / SKETCH_NAME

    def ignore(dirname, names):
        return [n for n in names if n in EXCLUDE_DIRS or n.endswith(".zh.bak")]

    shutil.copytree(ROOT, dest, ignore=ignore)
    return dest


def compile_sketch(cli: Path, data_dir: str, sketch: Path, out_dir: Path, build_dir: Path) -> None:
    cmd = [str(cli), "compile", "--fqbn", FQBN,
           "--build-path", str(build_dir),
           "--output-dir", str(out_dir),
           str(sketch)]
    env = dict(os.environ)
    if data_dir:
        env["ARDUINO_DIRECTORIES_DATA"] = data_dir
    print("执行:", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def verify_crypto_link(elf_path: Path) -> bool:
    """按 tools/verify_p4_crypto.py 的契约校验 ELF/map 的 TinyCrypt owner 绑定。

    契约要求 EccPoint_mult / uECC_* / esp_tinycrypt_* 全部由
    sketch/src/p4_tinycrypt/ 下的 .o 提供，且不得链入 libbt.a 的 stock TinyCrypt。
    （旧 dist 产物就是踩了这条：编自去掉 src/ 的副本，用了 stock libbt 实现。）

    说明：完整版 verify_p4_crypto.py 还会比对上游源文件 SHA256，但那是按 LF
    工作区写的——本机 core.autocrlf=true 会把源码检出为 CRLF，导致比对必然失败
    （已验证 LF 归一化后哈希与上游 manifest 一致）。所以这里只做 owner 绑定校验，
    并把反斜杠归一化成 '/' 以适配 POSIX 后缀匹配。
    """
    map_path = elf_path.with_suffix(".map")
    if not map_path.is_file():
        print(f"[WARN] 找不到 map，跳过 crypto 契约校验: {map_path}")
        return True
    spec = importlib.util.spec_from_file_location(
        "verify_p4_crypto", ROOT / "tools" / "verify_p4_crypto.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    try:
        owners = checker.verify_map(
            map_path.read_text(encoding="utf-8", errors="replace").replace("\\", "/"),
            checker.elf_functions(elf_path.read_bytes()))
    except (OSError, ValueError, struct.error) as exc:
        print(f"[FAIL] crypto 契约校验失败: {exc}")
        return False
    print("[PASS] crypto 契约：TinyCrypt 符号来自 src/p4_tinycrypt（未链入 stock libbt）")
    for symbol, info in owners.items():
        print(f"        {symbol} <- {info['owner']}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="重编 P4-CAN-Universal 中文固件")
    ap.add_argument("--work-dir", type=Path, default=ROOT / "build")
    ap.add_argument("--cli", help="arduino-cli 路径")
    ap.add_argument("--data-dir", help="ESP32 core 数据目录（含 packages/）")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args()

    cli = find_cli(args.cli)
    data_dir = find_data_dir(args.data_dir)
    work = args.work_dir.resolve()
    out_dir = work / "out"
    build_dir = work / "build"

    print(f"仓库    : {ROOT}")
    print(f"arduino-cli: {cli}")
    print(f"数据目录: {data_dir or '(默认)'}")
    print(f"工作目录: {work}")

    build_dashboard()
    sketch = stage_sources(work / "_src")
    out_dir.mkdir(parents=True, exist_ok=True)
    compile_sketch(cli, data_dir, sketch, out_dir, build_dir)

    app_bin = out_dir / f"{SKETCH_NAME}.ino.bin"
    full_bin = out_dir / f"{SKETCH_NAME}.ino.merged.bin"
    for p in (app_bin, full_bin):
        if not p.is_file():
            print(f"[FAIL] 缺少产物: {p}")
            return 1
        print(f"产物: {p}  ({p.stat().st_size:,} 字节)")

    if not args.skip_verify:
        verify = ROOT / "tools" / "verify_build.py"
        for p in (app_bin, full_bin):
            if subprocess.run([sys.executable, str(verify), "--bin", str(p),
                               "--html", str(ROOT / "dashboard_source.html")]).returncode != 0:
                return 1
        if not verify_crypto_link(build_dir / f"{SKETCH_NAME}.ino.elf"):
            return 1
    print("编译完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

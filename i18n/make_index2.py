# -*- coding: utf-8 -*-
"""为 ESP32 3.3.12 生成完全离线的索引：按工具名手工映射到已下载的归档。"""
import hashlib
import json
import urllib.parse
from pathlib import Path

MIRROR = Path(r"C:\esp-mirror")
BASE = "http://127.0.0.1:8123/"

# 原始索引：优先用 Arduino15 里残留的副本，否则用本地镜像里的旧副本
candidates = [
    Path(r"C:\Users\Administrator\AppData\Local\Arduino15\package_esp32_index.json"),
    Path(r"C:\arduino-data\package_esp32_index.json"),
    MIRROR / "index_local.json",
]
src = next((c for c in candidates if c.exists()), None)
if src is None:
    raise SystemExit("找不到原始索引")

data = json.loads(src.read_text(encoding="utf-8-sig"))

# 工具名 -> 本地归档（手工映射）
MAP = {
    "esp-x32": "xtensa-esp-elf-14.2.0_20260121-i686-w64-mingw32.zip",
    "xtensa-esp-elf-gdb": "xtensa-esp-elf-gdb-17.1_20260402-i686-w64-mingw32.zip",
    "esp-rv32": "riscv32-esp-elf-14.2.0_20260121-i686-w64-mingw32.zip",
    "riscv32-esp-elf-gdb": "riscv32-esp-elf-gdb-17.1_20260402-i686-w64-mingw32.zip",
    "openocd-esp32": "openocd-esp32-win32-0.12.0-esp32-20260424.zip",
    "esptool_py": "esptool-v5.3.1-windows-amd64.zip",
    "mkspiffs": "mkspiffs-0.2.3-arduino-esp32-win32.zip",
    "mklittlefs": "i686-w64-mingw32-mklittlefs-db0513a.zip",
    "esp32-libs": "esp32-libs-3.3.12.zip",
    "esp32c3-libs": "esp32c3-libs-3.3.12.zip",
    "esp32c5-libs": "esp32c5-libs-3.3.12.zip",
    "esp32c6-libs": "esp32c6-libs-3.3.12.zip",
    "esp32h2-libs": "esp32h2-libs-3.3.12.zip",
    "esp32p4-libs": "esp32p4-libs-3.3.12.zip",
    "esp32p4_es-libs": "esp32p4_es-libs-3.3.12.zip",
    "esp32s2-libs": "esp32s2-libs-3.3.12.zip",
    "esp32s3-libs": "esp32s3-libs-3.3.12.zip",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


cache = {}
def meta(name):
    if name not in cache:
        p = MIRROR / name
        if not p.exists():
            raise SystemExit(f"缺少归档: {name}")
        cache[name] = ("SHA-256:" + sha256(p), str(p.stat().st_size))
    return cache[name]


pkg = [x for x in data["packages"] if x["name"] == "esp32"][0]
plat = [x for x in pkg["platforms"] if x["version"] == "3.3.12"][0]
core = "esp32-core-3.3.12.zip"
plat["url"] = BASE + core
plat["checksum"], plat["size"] = meta(core)
print("platform ->", core)

for dep in plat["toolsDependencies"]:
    name = dep["name"]
    if name not in MAP:
        print("!! 未映射工具:", name)
        continue
    fname = MAP[name]
    chk, size = meta(fname)
    hits = 0
    for tool in pkg["tools"]:
        if tool["name"] != name:
            continue
        for s in tool.get("systems", []):
            if "mingw" not in s.get("host", ""):
                continue
            s["url"] = BASE + fname
            s["checksum"] = chk
            s["size"] = size
            hits += 1
    print(f"{name:20} -> {fname:52} hosts={hits}")

out = MIRROR / "index_local.json"
out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print("wrote", out, out.stat().st_size)

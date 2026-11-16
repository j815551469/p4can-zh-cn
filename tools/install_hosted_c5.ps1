<#
.SYNOPSIS
    安装 C5 目标的 libespressif__esp_hosted.a，并把两份 sdkconfig.h 的协处理器目标改成 C5。

.DESCRIPTION
    改动只落在 C:\arduino-data2 的 core 工具目录里，不动仓库源码：
      1. lib\libespressif__esp_hosted.a          <- C5 版（原库备份在 backup\）
      2. qio_qspi\include\sdkconfig.h           C6 -> C5
      3. dio_qspi\include\sdkconfig.h           C6 -> C5
    幂等：已改过的 sdkconfig 不会重复改、也不会报错。

.PARAMETER NewLib
    tools/build_hosted_c5.ps1 产出的库；也可用 backup\libespressif__esp_hosted.a.c5。

.PARAMETER Libs
    esp32p4-libs 目录。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\install_hosted_c5.ps1
#>
param(
    [string]$NewLib = 'C:\esp-build-c5lib\libespressif__esp_hosted.a',
    [string]$Libs   = 'C:\arduino-data2\packages\esp32\tools\esp32p4-libs\3.3.12'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $NewLib)) { throw "找不到库文件: $NewLib" }
$Backup = Join-Path $Libs 'backup'
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

# 首次安装时把官方库/配置留一份 .bak（已存在则不动，避免覆盖真正的原件）
$lib = Join-Path $Libs 'lib\libespressif__esp_hosted.a'
$libBak = Join-Path $Backup 'libespressif__esp_hosted.a.bak'
if (-not (Test-Path $libBak)) { Copy-Item $lib $libBak -Force; Write-Output "备份原库 -> $libBak" }

Copy-Item $NewLib $lib -Force
Write-Output "已安装 -> $lib"
Write-Output ("  sha256: " + (Get-FileHash $lib).Hash)
if ((Get-FileHash $lib).Hash -eq (Get-FileHash $libBak).Hash) {
    Write-Warning '安装后的库与备份一致，可能没有换成 C5 版'
}

$patches = @(
    @{ From = '#define CONFIG_ESP_HOSTED_CP_TARGET_ESP32C6 1'
       To   = '#define CONFIG_ESP_HOSTED_CP_TARGET_ESP32C5 1' },
    @{ From = '#define CONFIG_ESP_HOSTED_IDF_SLAVE_TARGET "esp32c6"'
       To   = '#define CONFIG_ESP_HOSTED_IDF_SLAVE_TARGET "esp32c5"' },
    @{ From = '#define CONFIG_SLAVE_IDF_TARGET_ESP32C6 1'
       To   = '#define CONFIG_SLAVE_IDF_TARGET_ESP32C5 1' }
)

foreach ($v in 'qio_qspi', 'dio_qspi') {
    $f = Join-Path $Libs "$v\include\sdkconfig.h"
    if (-not (Test-Path $f)) { throw "找不到 $f" }
    $bak = Join-Path $Backup ($v + '_sdkconfig.h.bak')
    if (-not (Test-Path $bak)) { Copy-Item $f $bak -Force; Write-Output "备份 $v sdkconfig -> $bak" }

    $text = Get-Content $f -Raw
    foreach ($p in $patches) {
        if ($text.Contains($p.From)) { $text = $text.Replace($p.From, $p.To) }
        elseif ($text.Contains($p.To)) { }              # 已经改过
        else { throw "$v sdkconfig 里找不到锚点: $($p.From)" }
    }
    [System.IO.File]::WriteAllText($f, $text, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output "已改 $v 的 sdkconfig.h -> CP_TARGET=ESP32C5"
}

Write-Output ''
Write-Output '完成。重编固件: python tools/build_firmware.py'
Write-Output '回滚: 从 backup\ 拷回 *_sdkconfig.h.bak 与 libespressif__esp_hosted.a.bak'

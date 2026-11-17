<#
.SYNOPSIS
    按 ESP32-C5 协处理器目标重编 esp_hosted 2.12.13，产出 libespressif__esp_hosted.a。

.DESCRIPTION
    Arduino esp32 core 3.3.12 给 ESP32-P4 预编译的 esp_hosted 库是按 C6 协处理器编的，
    在 P4+C5 板上启动会 abort：
        Identified slave [esp32c5] != Expected [esp32c6]
    该“期望值”是编译期常量（CONFIG_ESP_HOSTED_CP_TARGET_ESP32C6 -> H_SLAVE_TARGET_ESP32C6
    -> transport_drv.c 的 exp_chip_id），只能重编库，改头文件/改字符串都无效。

    本脚本复用 core 自己导出的编译参数（flags/c_flags、flags/defines、flags/includes），
    只把 sdkconfig 里的 CP_TARGET 换成 C5，编译组件 CMakeLists 里 SDIO + VHCI 配置下的
    27 个 .c，打包成 .a。然后用 tools/install_hosted_c5.ps1 安装。

.PARAMETER Source
    esp_hosted 2.12.13 组件源码目录（含 host/、common/、CMakeLists.txt）。
    取自 https://components.espressif.com/components/espressif/esp_hosted/versions/2.12.13
    的归档（解压后目录名为 esp_hosted）。

.PARAMETER WorkDir
    中间目录：obj/、sdkconfig/、日志、产物 .a 都放这里。

.PARAMETER Libs
    esp32p4-libs 目录（core 的 3.3.12 P4 预编译库/头文件/flags 所在处）。

.PARAMETER SdkConfig
    sdkconfig.h 源文件，默认 qio_qspi 变体（FlashMode=qio）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\build_hosted_c5.ps1
#>
param(
    [string]$Source    = 'D:\harness works\p4can\esp-hosted-src\esp_hosted',
    [string]$WorkDir   = 'C:\esp-build-c5lib',
    [string]$Libs      = 'C:\arduino-data2\packages\esp32\tools\esp32p4-libs\3.3.12',
    [string]$SdkConfig = ''
)

$ErrorActionPreference = 'Continue'

if (-not $SdkConfig) { $SdkConfig = Join-Path $Libs 'qio_qspi\include\sdkconfig.h' }
$SdkDir = Join-Path $WorkDir 'sdkconfig'
$ObjDir = Join-Path $WorkDir 'obj'
$ToolsRoot = Split-Path (Split-Path $Libs -Parent) -Parent   # ...\packages\esp32\tools
$Gcc    = Join-Path $ToolsRoot 'esp-rv32\2601\bin\riscv32-esp-elf-gcc.exe'
$Ar     = Join-Path $ToolsRoot 'esp-rv32\2601\bin\riscv32-esp-elf-ar.exe'

foreach ($p in @($Source, $SdkConfig, $Gcc, $Ar)) {
    if (-not (Test-Path $p)) { throw "路径不存在: $p" }
}
New-Item -ItemType Directory -Force -Path $SdkDir | Out-Null
New-Item -ItemType Directory -Force -Path $ObjDir | Out-Null

# ------------------------------------------------------------- sdkconfig.h (C5)
$text = Get-Content $SdkConfig -Raw
$patches = @(
    @{ From = '#define CONFIG_ESP_HOSTED_CP_TARGET_ESP32C6 1'
       To   = '#define CONFIG_ESP_HOSTED_CP_TARGET_ESP32C5 1' },
    @{ From = '#define CONFIG_ESP_HOSTED_IDF_SLAVE_TARGET "esp32c6"'
       To   = '#define CONFIG_ESP_HOSTED_IDF_SLAVE_TARGET "esp32c5"' },
    @{ From = '#define CONFIG_SLAVE_IDF_TARGET_ESP32C6 1'
       To   = '#define CONFIG_SLAVE_IDF_TARGET_ESP32C5 1' }
)
foreach ($p in $patches) {
    if ($text.Contains($p.From)) { $text = $text.Replace($p.From, $p.To) }
    elseif ($text.Contains($p.To)) { }        # 已经是 C5（装过以后再编）
    else { throw "sdkconfig 里找不到锚点: $($p.From)" }
}
$sdkOut = Join-Path $SdkDir 'sdkconfig.h'
[System.IO.File]::WriteAllText($sdkOut, $text, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "sdkconfig -> $sdkOut (CP_TARGET=ESP32C5)"

# --------------------------------------------------------------- source list
# CMakeLists.txt: SDIO host interface + NIMBLE VHCI + 无 mempool + 无 OpenThread
$srcs = @(
    'host/api/src/esp_wifi_weak.c'
    'host/api/src/esp_hosted_api.c'
    'host/api/src/esp_hosted_transport_config.c'
    'host/api/src/esp_hosted_ota_api.c'
    'host/drivers/transport/transport_drv.c'
    'host/drivers/transport/transport_util.c'
    'host/drivers/serial/serial_ll_if.c'
    'host/utils/stats.c'
    'host/drivers/serial/serial_drv.c'
    'host/drivers/rpc/core/rpc_core.c'
    'host/drivers/rpc/core/rpc_req.c'
    'host/drivers/rpc/core/rpc_rsp.c'
    'host/drivers/rpc/core/rpc_evt.c'
    'host/drivers/rpc/core/rpc_utils.c'
    'host/drivers/rpc/slaveif/rpc_slave_if.c'
    'host/drivers/rpc/wrap/rpc_wrap.c'
    'host/drivers/virtual_serial_if/serial_if.c'
    'common/protobuf-c/protobuf-c/protobuf-c.c'
    'common/proto/esp_hosted_rpc.pb-c.c'
    'common/utils/esp_hosted_cli.c'
    'host/drivers/bt/vhci_drv.c'
    'host/drivers/power_save/power_save_drv.c'
    'host/drivers/transport/sdio/sdio_drv.c'
    'host/port/esp/freertos/src/port_esp_hosted_host_init.c'
    'host/port/esp/freertos/src/port_esp_hosted_host_os.c'
    'host/port/esp/freertos/src/port_esp_hosted_host_transport_defaults.c'
    'host/port/esp/freertos/src/port_esp_hosted_host_sdio.c'
)

# CMakeLists.txt 的 PRIV_INCLUDE_DIRS
$privInc = @(
    'host'
    'host/api/include'
    'host/drivers/transport'
    'host/drivers/transport/spi'
    'host/drivers/transport/sdio'
    'host/drivers/serial'
    'host/utils'
    'host/api/priv'
    'host/drivers/rpc/core'
    'host/drivers/rpc/slaveif'
    'host/drivers/rpc/wrap'
    'host/drivers/virtual_serial_if'
    'common'
    'common/log'
    'common/rpc'
    'common/transport'
    'common/protobuf-c'
    'common/proto'
    'common/mempool/include'
    'common/utils'
    'host/drivers/bt'
    'host/drivers/power_save'
    'host/port/esp/freertos/include'
)

# -iwithprefixbefore <rel> 解析成 -I<Libs>\include\<rel>（等价于 core 的 -iprefix）
$includeRoot = Join-Path $Libs 'include'
$tokens = (Get-Content (Join-Path $Libs 'flags\includes') -Raw) -split '\s+' | Where-Object { $_ -ne '' }
$incArgs = @()
for ($i = 0; $i -lt $tokens.Count; $i++) {
    if ($tokens[$i] -eq '-iwithprefixbefore') {
        $incArgs += ('-I' + (Join-Path $includeRoot $tokens[$i + 1])); $i++
    } elseif ($tokens[$i] -eq '-iwithprefix') {
        $incArgs += ('-idirafter' + (Join-Path $includeRoot $tokens[$i + 1])); $i++
    } else {
        Write-Warning "includes 里出现意外 token: $($tokens[$i])"
    }
}

$cFlagsArg  = '@' + (Join-Path $Libs 'flags\c_flags')
$definesArg = '@' + (Join-Path $Libs 'flags\defines')
$commonArgs = @(
    '-MMD', '-c',
    $cFlagsArg,
    '-w', '-Os', '-Werror=return-type',
    '-fno-exceptions', '-DARDUINO_CORE_BUILD',
    $definesArg
) + $incArgs + @('-I' + $SdkDir)
foreach ($d in $privInc) { $commonArgs += ('-I' + (Join-Path $Source $d)) }

# ---------------------------------------------------------------- compile
# GCC 的 @rsp 解析里 '\' 是转义符，所以 rsp 内路径统一写正斜杠。
function Quote-Arg([string]$a) {
    if ($a.StartsWith('-D')) { return $a }   # define 里可能含 \" 序列
    return ($a -replace '\\', '/')
}

$failed = @()
foreach ($rel in $srcs) {
    $file = Join-Path $Source ($rel -replace '/', '\')
    if (-not (Test-Path $file)) { throw "缺少源文件 $file" }
    $objName = (Split-Path $rel -Leaf) + '.obj'
    $obj = Join-Path $ObjDir $objName
    $rsp = Join-Path $WorkDir ('rsp_' + $objName + '.rsp')
    $lines = @($commonArgs) + @($file, '-o', $obj) | ForEach-Object { Quote-Arg $_ }
    [System.IO.File]::WriteAllLines($rsp, $lines, (New-Object System.Text.UTF8Encoding($false)))

    $errLog = Join-Path $WorkDir ('err_' + $objName + '.log')
    & $Gcc ('@' + $rsp) 1> (Join-Path $WorkDir ('out_' + $objName + '.log')) 2> $errLog
    if ($LASTEXITCODE -ne 0) {
        $failed += $rel
        Write-Warning "编译失败: $rel"
        Get-Content $errLog | Select-Object -Last 20
    } else {
        Write-Output "ok  $rel"
    }
}
if ($failed.Count) { throw ("编译失败: " + ($failed -join ', ')) }

# ---------------------------------------------------------------- archive
$out = Join-Path $WorkDir 'libespressif__esp_hosted.a'
if (Test-Path $out) { Remove-Item $out -Force }
$objs = Get-ChildItem $ObjDir -Filter *.obj | Sort-Object Name | ForEach-Object { $_.FullName }
& $Ar rcs $out @objs
if ($LASTEXITCODE -ne 0) { throw 'ar 失败' }

Write-Output ""
Write-Output "产物: $out"
Get-Item $out | Select-Object Length, LastWriteTime | Format-List
Write-Output "成员数: $((& $Ar t $out).Count)"
Write-Output "下一步: powershell -ExecutionPolicy Bypass -File tools\install_hosted_c5.ps1 -NewLib `"$out`""

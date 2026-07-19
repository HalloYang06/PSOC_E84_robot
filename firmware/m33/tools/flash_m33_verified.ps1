[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$SecureRoot = "",
    [string]$Image = "",
    [string]$XipImage = "",
    [string]$OpenOcdHome = "F:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0",
    [switch]$SkipBuild,
    [ValidateRange(1, 32)]
    [int]$Jobs = 4
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
if ([string]::IsNullOrWhiteSpace($SecureRoot)) {
    $SecureRoot = Join-Path (Split-Path -Parent $ProjectRoot) "secureCore"
}
$SecureRoot = (Resolve-Path -LiteralPath $SecureRoot).Path

$secureStartupRelativePath = "libs\TARGET_APP_KIT_PSE84_EVAL_EPC2\COMPONENT_CM33\COMPONENT_SECURE_DEVICE\s_start_pse84.c"
$trackedSecureStartup = Join-Path $ProjectRoot $secureStartupRelativePath
$actualSecureStartup = Join-Path $SecureRoot $secureStartupRelativePath

foreach ($startupSource in @($trackedSecureStartup, $actualSecureStartup)) {
    if (-not (Test-Path -LiteralPath $startupSource -PathType Leaf)) {
        throw "Secure startup source not found: $startupSource"
    }
}

$trackedSecureStartupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $trackedSecureStartup).Hash
$actualSecureStartupHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $actualSecureStartup).Hash
if ($trackedSecureStartupHash -ne $actualSecureStartupHash) {
    throw "Secure startup source mismatch: tracked=$trackedSecureStartupHash actual=$actualSecureStartupHash"
}

$makeExe = "F:\RT-ThreadStudio\platform\env_released\env\tools\bin\make.exe"
$makeBin = Split-Path -Parent $makeExe
$buildToolsBin = "F:\RT-ThreadStudio\platform\env_released\env\tools\BuildTools\2.12-20190422-1053\bin"
$toolchainBin = "F:\RT-ThreadStudio\repo\Extract\ToolChain_Support_Packages\ARM\GNU_Tools_for_ARM_Embedded_Processors\13.3\bin"
$projectLinkerBin = "F:\RT-ThreadStudio\plugins\org.rt-thread.studio.project.gener_1.0.30\builder"
$edgeProtectTools = Join-Path $ProjectRoot "tools\edgeprotecttools\bin\edgeprotecttools.exe"
$secureBuildDirectory = Join-Path $SecureRoot "Debug"
$nsBuildDirectory = Join-Path $ProjectRoot "Debug"
$secureHex = Join-Path $secureBuildDirectory "rtthread.hex"
$secureImageDestination = Join-Path $ProjectRoot "tools\edgeprotecttools\cm33_s_signed_fw\proj_cm33_s_signed.hex"

if ([string]::IsNullOrWhiteSpace($Image)) {
    $Image = Join-Path $nsBuildDirectory "rtthread.hex"
}
if ([string]::IsNullOrWhiteSpace($XipImage)) {
    $XipImage = Join-Path $nsBuildDirectory "rtthread_xip_verify.hex"
}

foreach ($requiredTool in @($makeExe, $edgeProtectTools)) {
    if (-not (Test-Path -LiteralPath $requiredTool -PathType Leaf)) {
        throw "Required tool not found: $requiredTool"
    }
}

if (-not $SkipBuild) {
    $env:PATH = "$toolchainBin;$projectLinkerBin;$buildToolsBin;$makeBin;$env:PATH"
    $env:MAKE = "make"
    $env:RTT_EXEC_PATH = $toolchainBin

    Write-Host "[m33] Building Secure image..."
    Invoke-Native -FilePath $makeExe -Arguments @("-C", $secureBuildDirectory, "-j$Jobs", "rtthread.elf")
    Invoke-Native -FilePath $makeExe -Arguments @("-C", $secureBuildDirectory, "post-build")
    if (-not (Test-Path -LiteralPath $secureHex -PathType Leaf)) {
        throw "Secure build did not produce: $secureHex"
    }
    Copy-Item -LiteralPath $secureHex -Destination $secureImageDestination -Force

    Write-Host "[m33] Building Non-secure combined image..."
    Invoke-Native -FilePath $makeExe -Arguments @("-C", $nsBuildDirectory, "-j$Jobs", "rtthread.elf")
    Invoke-Native -FilePath $makeExe -Arguments @("-C", $nsBuildDirectory, "post-build")
}

if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) {
    throw "Combined M33 image not found: $Image"
}

# Relocate both raw/S-AHB ranges to their C-AHB aliases. OpenOCD uses this
# second HEX only for a full cached-path verify; it is never programmed.
if (Test-Path -LiteralPath $XipImage) {
    Remove-Item -LiteralPath $XipImage -Force
}
Invoke-Native -FilePath $edgeProtectTools -Arguments @(
    "hex-relocate",
    "--input", $Image,
    "--region", "0x60000000", "0x01000000", "0x08000000",
    "--region", "0x70000000", "0x01000000", "0x18000000",
    "--output", $XipImage
)

$openOcd = Join-Path $OpenOcdHome "bin\openocd.exe"
$openOcdScripts = Join-Path $OpenOcdHome "scripts"
$flmDirectory = Join-Path $OpenOcdHome "flm\cypress\cat1d"
$flashLoader = Join-Path $flmDirectory "PSE84_SMIF.FLM"
$flowScript = Join-Path $ProjectRoot "tools\openocd\pse84_m33_verified_flash.tcl"

foreach ($requiredPath in @($openOcd, $flashLoader, $flowScript, $XipImage)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required flash input not found: $requiredPath"
    }
}

function Convert-ToTclPath([string]$Path) {
    return $Path.Replace("\", "/")
}

$imageTcl = Convert-ToTclPath $Image
$xipImageTcl = Convert-ToTclPath $XipImage
$flashLoaderTcl = Convert-ToTclPath $flashLoader

Write-Host "[m33] Programming, raw-verifying, invalidating caches, XIP-verifying, and starting CM33..."
Invoke-Native -FilePath $openOcd -Arguments @(
    "-s", $openOcdScripts,
    "-s", $flmDirectory,
    "-f", "interface/kitprog3.cfg",
    "-c", "transport select swd",
    "-c", "set QSPI_FLASHLOADER {$flashLoaderTcl}",
    "-c", "set ENABLE_CM55 0; set DEVICE PSE84xGxS2",
    "-f", "target/infineon/pse84.cfg",
    "-c", "set M33_IMAGE {$imageTcl}",
    "-c", "set M33_XIP_IMAGE {$xipImageTcl}",
    "-c", "set M33_STANDALONE 1",
    "-f", $flowScript
)

Write-Host "[m33] Verified flash completed successfully."

param(
    [string]$UnityProjectPath = "D:\unity_project\My project",
    [string]$UnityScenePath = "Assets/Education2D/Scenes/ReferenceBuilds/Education2D_Ref_InteriorLab.unity",
    [string]$PlatformRoot = "D:\ai-collab-product",
    [string]$TuanjieEditorPath = "D:\unity\2022.3.62t7\Editor\Tuanjie.exe",
    [switch]$SkipWebBuild,
    [switch]$KeepCopy
)

$ErrorActionPreference = "Stop"

function Assert-PathExists([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
}

Assert-PathExists $UnityProjectPath "Unity project"
Assert-PathExists (Join-Path $UnityProjectPath $UnityScenePath) "Unity scene"
Assert-PathExists $PlatformRoot "Platform root"
Assert-PathExists $TuanjieEditorPath "Tuanjie editor"

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runtimeRoot = Join-Path $PlatformRoot ".codex-runtime"
$copyRuntimeRoot = "D:\a-agent-unity-builds"
$copyRoot = Join-Path $copyRuntimeRoot "unity-webgl-copy-$timestamp"
$logPath = Join-Path $runtimeRoot "unity-webgl-build-$timestamp.log"
$outputPath = Join-Path $PlatformRoot "apps\web\public\unity\education2d"

New-Item -ItemType Directory -Force -Path $copyRuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $copyRoot | Out-Null
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null

foreach ($folder in @("Assets", "Packages", "ProjectSettings")) {
    $src = Join-Path $UnityProjectPath $folder
    $dst = Join-Path $copyRoot $folder
    Assert-PathExists $src "Unity $folder folder"
    robocopy $src $dst /E /MT:16 /R:2 /W:2 /NFL /NDL /NP | Out-Host
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed for $folder with exit code $LASTEXITCODE"
    }
}

$buildToolsPath = Join-Path $copyRoot "Assets\Education2D\Editor\Education2DPlatformBuildTools.cs"
Assert-PathExists $buildToolsPath "Unity WebGL build tools"
$buildToolsContent = Get-Content -LiteralPath $buildToolsPath -Raw
$legacyInstallerCall = "        Education2DInteriorLabPlatformInstaller.InstallPlatformPortals(gameScenePath);"
if ($buildToolsContent.Contains($legacyInstallerCall)) {
    $clickOnlyReplacement = @"
        // A Agent click-only shell: React/DOM buttons own platform module launchers.
        // Do not re-install Unity in-world interactables during WebGL export.
        // Education2DInteriorLabPlatformInstaller.InstallPlatformPortals(gameScenePath);
"@
    $buildToolsContent = $buildToolsContent.Replace($legacyInstallerCall, $clickOnlyReplacement.TrimEnd())
    Set-Content -LiteralPath $buildToolsPath -Value $buildToolsContent -Encoding UTF8
}

$previewPath = Join-Path $UnityProjectPath "Education2D_Game_1280x720.png"
if (Test-Path -LiteralPath $previewPath) {
    Copy-Item -LiteralPath $previewPath -Destination (Join-Path $copyRoot "Education2D_Game_1280x720.png") -Force
}

$env:A_AGENT_WEB_UNITY_OUTPUT = $outputPath.Replace("\", "/")
$env:A_AGENT_UNITY_SOURCE_PROJECT = $UnityProjectPath.Replace("\", "/")
$env:A_AGENT_UNITY_SCENE_PATH = $UnityScenePath.Replace("\", "/")

$unityArgs = @(
    "-batchmode",
    "-nographics",
    "-quit",
    "-projectPath",
    $copyRoot,
    "-executeMethod",
    "Education2DPlatformBuildTools.BuildWebGLToPlatformPublic",
    "-logFile",
    $logPath
)

$unityProcess = Start-Process -FilePath $TuanjieEditorPath -ArgumentList $unityArgs -PassThru -Wait -WindowStyle Hidden
if ($unityProcess.ExitCode -ne 0) {
    throw "Unity WebGL build failed with exit code $($unityProcess.ExitCode). Log: $logPath"
}

$requiredFiles = @(
    (Join-Path $outputPath "index.html"),
    (Join-Path $outputPath "Build\education2d.loader.js"),
    (Join-Path $outputPath "Build\education2d.framework.js"),
    (Join-Path $outputPath "Build\education2d.data"),
    (Join-Path $outputPath "Build\education2d.wasm")
)

foreach ($file in $requiredFiles) {
    Assert-PathExists $file "Unity WebGL output"
}

$stylePath = Join-Path $outputPath "TemplateData\style.css"
Assert-PathExists $stylePath "Unity WebGL style"
$fullscreenPatch = @"

/* A Agent platform fullscreen shell patch.
   Unity/Tuanjie defaults to a centered 960x600 desktop canvas, which leaves
   large white browser margins. The platform entry should behave like a game. */
html,
body {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #000;
}

#tuanjie-container,
#tuanjie-container.tuanjie-desktop,
#tuanjie-container.tuanjie-mobile {
  position: fixed !important;
  inset: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  left: 0 !important;
  top: 0 !important;
  transform: none !important;
  background: #000;
}

#tuanjie-canvas,
.tuanjie-mobile #tuanjie-canvas {
  width: 100vw !important;
  height: 100vh !important;
  display: block;
  background: #000;
}

#tuanjie-footer {
  display: none !important;
}
"@
$styleContent = Get-Content -LiteralPath $stylePath -Raw
if ($styleContent -notlike "*A Agent platform fullscreen shell patch*") {
    Add-Content -LiteralPath $stylePath -Value $fullscreenPatch -Encoding UTF8
}

if (-not $SkipWebBuild) {
    Push-Location $PlatformRoot
    try {
        npm run build:web
    } finally {
        Pop-Location
    }
}

if (-not $KeepCopy) {
    $resolvedCopyRoot = (Resolve-Path -LiteralPath $copyRoot).Path
    if (-not $resolvedCopyRoot.StartsWith((Resolve-Path -LiteralPath $copyRuntimeRoot).Path, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete unexpected copy path: $resolvedCopyRoot"
    }
    Remove-Item -LiteralPath $resolvedCopyRoot -Recurse -Force
}

Write-Host "Unity WebGL build completed."
Write-Host "Output: $outputPath"
Write-Host "Log: $logPath"

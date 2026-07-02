$ErrorActionPreference = "Stop"

$javaHome = "D:\Java\jdk-21"
$androidHome = "D:\Android\Sdk"

if (-not (Test-Path (Join-Path $javaHome "bin\java.exe"))) {
    throw "JDK 21 not found at $javaHome"
}

if (-not (Test-Path (Join-Path $androidHome "cmdline-tools\latest\bin\sdkmanager.bat"))) {
    throw "Android SDK command-line tools not found at $androidHome"
}

$env:JAVA_HOME = $javaHome
$env:ANDROID_HOME = $androidHome
$env:ANDROID_SDK_ROOT = $androidHome
$env:Path = @(
    (Join-Path $javaHome "bin"),
    (Join-Path $androidHome "cmdline-tools\latest\bin"),
    (Join-Path $androidHome "platform-tools"),
    (Join-Path $androidHome "emulator"),
    (Join-Path $androidHome "build-tools\35.0.0"),
    $env:Path
) -join ";"

Write-Host "JAVA_HOME=$env:JAVA_HOME"
Write-Host "ANDROID_HOME=$env:ANDROID_HOME"
java -version
adb version

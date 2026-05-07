param(
  [Parameter(Mandatory = $true)]
  [string]$Url,
  [Parameter(Mandatory = $true)]
  [string]$Output,
  [string]$TitleHint = "",
  [int]$Width = 1680,
  [int]$Height = 1260,
  [int]$WaitSeconds = 10
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -ReferencedAssemblies @("System.Drawing") @"
using System;
using System.Runtime.InteropServices;
using System.Drawing;
public static class NativeWindowTools {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT {
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
  }
  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")]
  public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")]
  public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, int nFlags);

  public static Bitmap CaptureWindow(IntPtr hWnd, int fallbackWidth, int fallbackHeight) {
    RECT rect;
    bool hasRect = GetWindowRect(hWnd, out rect);
    int width = hasRect ? Math.Max(1, rect.Right - rect.Left) : Math.Max(1, fallbackWidth);
    int height = hasRect ? Math.Max(1, rect.Bottom - rect.Top) : Math.Max(1, fallbackHeight);
    Bitmap bitmap = new Bitmap(width, height);
    using (Graphics graphics = Graphics.FromImage(bitmap)) {
      IntPtr hdc = graphics.GetHdc();
      try {
        bool ok = PrintWindow(hWnd, hdc, 2);
        if (!ok) {
          return null;
        }
      } finally {
        graphics.ReleaseHdc(hdc);
      }
    }
    return bitmap;
  }

  public static int GetWindowArea(IntPtr hWnd) {
    RECT rect;
    bool hasRect = GetWindowRect(hWnd, out rect);
    if (!hasRect) {
      return 0;
    }
    int width = Math.Max(0, rect.Right - rect.Left);
    int height = Math.Max(0, rect.Bottom - rect.Top);
    return width * height;
  }
}
"@

New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($Output)) | Out-Null
Remove-Item $Output -Force -ErrorAction SilentlyContinue

$edgePaths = @(
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$edge = $edgePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) {
  throw "Microsoft Edge not found"
}

$knownHandles = @{}
Get-Process msedge -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
  $knownHandles[[string]$_.MainWindowHandle] = $true
}

$process = Start-Process -FilePath $edge -ArgumentList @(
  "--new-window",
  "--window-position=0,0",
  "--window-size=$Width,$Height",
  $Url
) -PassThru

try {
  Start-Sleep -Seconds $WaitSeconds
  $edgeProcess = $null
  $windowCandidates = @()
  $windowDeadline = (Get-Date).AddSeconds(8)
  while ((Get-Date) -lt $windowDeadline -and $edgeProcess -eq $null) {
    $visibleWindows = Get-Process msedge -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object {
      [pscustomobject]@{
        Process = $_
        Area = [NativeWindowTools]::GetWindowArea($_.MainWindowHandle)
        Title = $_.MainWindowTitle
      }
    } | Where-Object { $_.Area -gt 0 }
    $windowCandidates = $visibleWindows
    $preferredWindows = $visibleWindows
    if ($TitleHint) {
      $titleMatched = $preferredWindows | Where-Object { $_.Title -like "*$TitleHint*" }
      if ($titleMatched) {
        $preferredWindows = $titleMatched
      }
    }
    $edgeProcess = $preferredWindows | Where-Object { -not $knownHandles.ContainsKey([string]$_.Process.MainWindowHandle) } | Sort-Object -Property @{Expression = { $_.Area }; Descending = $true}, @{Expression = { $_.Process.StartTime }; Descending = $true} | Select-Object -First 1
    if ($edgeProcess -eq $null) {
      $edgeProcess = $preferredWindows | Sort-Object -Property @{Expression = { $_.Area }; Descending = $true}, @{Expression = { $_.Process.StartTime }; Descending = $true} | Select-Object -First 1
    }
    if ($edgeProcess -eq $null) {
      Start-Sleep -Milliseconds 500
    }
  }
  $edgeWindowTitle = ""
  $edgeWindowArea = 0
  if ($edgeProcess -and $edgeProcess.Process.MainWindowHandle -ne 0) {
    $edgeWindowTitle = $edgeProcess.Title
    $edgeWindowArea = $edgeProcess.Area
    [NativeWindowTools]::ShowWindow($edgeProcess.Process.MainWindowHandle, 9) | Out-Null
    [NativeWindowTools]::SetForegroundWindow($edgeProcess.Process.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 1500
  }

  $bitmap = $null
  $captureMethod = "screen-fallback"
  if ($edgeProcess -and $edgeProcess.Process.MainWindowHandle -ne 0) {
    $bitmap = [NativeWindowTools]::CaptureWindow($edgeProcess.Process.MainWindowHandle, $Width, $Height)
    if ($bitmap -ne $null) {
      $captureMethod = "window-print"
    }
  }
  if ($bitmap -eq $null) {
    $bitmap = New-Object System.Drawing.Bitmap($Width, $Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen(0, 0, 0, 0, $bitmap.Size)
    $graphics.Dispose()
  }
  $bitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
  $bitmap.Dispose()
} finally {
  Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  if ($edgeProcess -and $edgeProcess.Process.Id -ne $process.Id) {
    Stop-Process -Id $edgeProcess.Process.Id -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Test-Path $Output)) {
  throw "Screenshot was not created"
}

Write-Output "CAPTURE_METHOD=$captureMethod"
if ($edgeWindowTitle) {
  Write-Output "WINDOW_TITLE=$edgeWindowTitle"
}
if ($edgeWindowArea -gt 0) {
  Write-Output "WINDOW_AREA=$edgeWindowArea"
}
if ($windowCandidates.Count -gt 0) {
  $candidateSummary = ($windowCandidates | Select-Object -First 5 | ForEach-Object { "$($_.Title)|$($_.Area)" }) -join "; "
  Write-Output "WINDOW_CANDIDATES=$candidateSummary"
}
Write-Output $Output

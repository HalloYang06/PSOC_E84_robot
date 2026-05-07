param(
  [Parameter(Mandatory = $true)]
  [string]$Url,
  [Parameter(Mandatory = $true)]
  [string]$Output,
  [int]$Width = 1680,
  [int]$Height = 1260,
  [int]$WaitMs = 12000
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($Output)) | Out-Null
Remove-Item $Output -Force -ErrorAction SilentlyContinue

$form = New-Object System.Windows.Forms.Form
$form.Width = $Width
$form.Height = $Height
$form.StartPosition = "Manual"
$form.Location = New-Object System.Drawing.Point(-32000, -32000)
$form.ShowInTaskbar = $false
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None

$browser = New-Object System.Windows.Forms.WebBrowser
$browser.ScriptErrorsSuppressed = $true
$browser.ScrollBarsEnabled = $false
$browser.Dock = [System.Windows.Forms.DockStyle]::Fill
$form.Controls.Add($browser)

$completed = $false
$browser.add_DocumentCompleted({
  if ($browser.ReadyState -eq [System.Windows.Forms.WebBrowserReadyState]::Complete) {
    $script:completed = $true
  }
})

$null = $form.Show()
$browser.Navigate($Url)

$deadline = [DateTime]::UtcNow.AddMilliseconds($WaitMs)
while ([DateTime]::UtcNow -lt $deadline) {
  [System.Windows.Forms.Application]::DoEvents()
  Start-Sleep -Milliseconds 100
  if ($script:completed) {
    Start-Sleep -Milliseconds 1200
    [System.Windows.Forms.Application]::DoEvents()
    break
  }
}

$bitmap = New-Object System.Drawing.Bitmap($Width, $Height)
$form.DrawToBitmap($bitmap, [System.Drawing.Rectangle]::FromLTRB(0, 0, $Width, $Height))
$bitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
$bitmap.Dispose()
$browser.Dispose()
$form.Close()
$form.Dispose()

if (-not (Test-Path $Output)) {
  throw "Screenshot was not created"
}

Write-Output $Output

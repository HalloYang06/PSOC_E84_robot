param(
    [string]$PortName = "COM26",
    [int]$BaudRate = 115200,
    [string]$TokenFile,
    [int]$ChunkSize = 56,
    [int]$CommandDelayMs = 250,
    [int]$FinalWaitMs = 3000,
    [switch]$ReconnectOnly,
    [switch]$Clear
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Send-ShellCommand {
    param(
        [System.IO.Ports.SerialPort]$Port,
        [string]$Command,
        [int]$DelayMs
    )

    if ($Command.StartsWith("m55qa_xz_token_part ")) {
        $chunk = $Command.Substring("m55qa_xz_token_part ".Length)
        Write-Host ">> m55qa_xz_token_part <masked chunk, len=$($chunk.Length)>"
    }
    else {
        Write-Host ">> $Command"
    }
    $Port.Write("$Command`r`n")
    Start-Sleep -Milliseconds $DelayMs
    $text = $Port.ReadExisting()
    if ($text.Length -gt 0) {
        $text = [regex]::Replace(
            $text,
            'm55qa_xz_token_part\s+\S+',
            'm55qa_xz_token_part <masked chunk>'
        )
        Write-Host $text
    }
}

function Split-Token {
    param(
        [string]$Token,
        [int]$Size
    )

    if ($Size -lt 16 -or $Size -gt 96) {
        throw "ChunkSize must be between 16 and 96 characters."
    }

    $chunks = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $Token.Length; $i += $Size) {
        $len = [Math]::Min($Size, $Token.Length - $i)
        $chunks.Add($Token.Substring($i, $len))
    }
    return $chunks
}

$token = ""
if (-not $Clear -and -not $ReconnectOnly) {
    if ([string]::IsNullOrWhiteSpace($TokenFile)) {
        throw "TokenFile is required unless -Clear or -ReconnectOnly is used."
    }
    if (-not (Test-Path -LiteralPath $TokenFile)) {
        throw "Token file not found: $TokenFile"
    }

    $token = (Get-Content -LiteralPath $TokenFile -Raw).Trim()
    if ($token.Length -eq 0) {
        throw "Token file is empty."
    }

    if (-not $token.StartsWith("rehab-relay.v1.")) {
        throw "Token should start with 'rehab-relay.v1.'. Do not use a vendor LLM API key here."
    }
}

$port = [System.IO.Ports.SerialPort]::new($PortName, $BaudRate, "None", 8, "One")
$port.ReadTimeout = 500
$port.WriteTimeout = 1000

try {
    $port.Open()
    Start-Sleep -Milliseconds 200
    $null = $port.ReadExisting()

    Send-ShellCommand -Port $port -Command "m55qa_status" -DelayMs $CommandDelayMs

    if ($Clear) {
        Send-ShellCommand -Port $port -Command "m55qa_xz_token_clear" -DelayMs $FinalWaitMs
        Send-ShellCommand -Port $port -Command "m55qa_status" -DelayMs $CommandDelayMs
        return
    }

    if ($ReconnectOnly) {
        Send-ShellCommand -Port $port -Command "m55qa_xz_reconnect" -DelayMs $FinalWaitMs
        Send-ShellCommand -Port $port -Command "m55qa_status" -DelayMs $CommandDelayMs
        return
    }

    $chunks = Split-Token -Token $token -Size $ChunkSize
    Write-Host "Token length: $($token.Length), chunks: $($chunks.Count), chunk size: $ChunkSize"

    Send-ShellCommand -Port $port -Command "m55qa_xz_token_begin" -DelayMs $CommandDelayMs
    foreach ($chunk in $chunks) {
        Send-ShellCommand -Port $port -Command "m55qa_xz_token_part $chunk" -DelayMs $CommandDelayMs
    }
    Send-ShellCommand -Port $port -Command "m55qa_xz_token_commit" -DelayMs $FinalWaitMs
    Send-ShellCommand -Port $port -Command "m55qa_status" -DelayMs $CommandDelayMs
}
finally {
    if ($port.IsOpen) {
        $port.Close()
    }
}

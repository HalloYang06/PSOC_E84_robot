param(
    [string]$Url = "ws://106.55.62.122:8011/api/rehab-arm/v1/projects/fd6a55ed-a63c-44b3-b123-96fb3c154966/devices/nanopi-m5/xiaozhi/ws?robot_id=rehab-arm-alpha",
    [Parameter(Mandatory = $true)]
    [string]$TokenFile,
    [string]$SessionId = "pc-smoke-session-001",
    [int]$Frames = 30,
    [int]$ToneHz = 440,
    [int]$ReceiveTimeoutMs = 3000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $TokenFile)) {
    throw "Token file not found: $TokenFile"
}

$token = (Get-Content -LiteralPath $TokenFile -Raw).Trim()
if (-not $token.StartsWith("rehab-relay.v1.")) {
    throw "Token must be a platform scoped rehab-relay.v1 token, not a vendor API key."
}

function ConvertTo-Utf8Bytes {
    param([string]$Text)
    return [System.Text.Encoding]::UTF8.GetBytes($Text)
}

function Send-TextFrame {
    param(
        [System.Net.WebSockets.ClientWebSocket]$Socket,
        [string]$Text
    )

    Write-Host ">> $Text"
    $bytes = ConvertTo-Utf8Bytes -Text $Text
    $segment = [System.ArraySegment[byte]]::new($bytes)
    $Socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
}

function Send-BinaryFrame {
    param(
        [System.Net.WebSockets.ClientWebSocket]$Socket,
        [byte[]]$Bytes
    )

    $segment = [System.ArraySegment[byte]]::new($Bytes)
    $Socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Binary, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
}

function Receive-AvailableFrames {
    param(
        [System.Net.WebSockets.ClientWebSocket]$Socket,
        [int]$TimeoutMs
    )

    while ($Socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
        $buffer = New-Object byte[] 4096
        $segment = [System.ArraySegment[byte]]::new($buffer)
        $cts = [Threading.CancellationTokenSource]::new($TimeoutMs)
        try {
            $result = $Socket.ReceiveAsync($segment, $cts.Token).GetAwaiter().GetResult()
        }
        catch [System.OperationCanceledException] {
            break
        }
        finally {
            $cts.Dispose()
        }

        if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
            Write-Host "<< <close>"
            break
        }

        $payload = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count)
        Write-Host "<< $payload"

        if ($result.EndOfMessage -and $payload.Contains('"type":"chat"')) {
            continue
        }
    }
}

function New-PcmFrame {
    param(
        [int]$FrameIndex,
        [int]$ToneHz
    )

    $sampleRate = 16000
    $samplesPerFrame = 320
    $bytes = New-Object byte[] 640

    for ($i = 0; $i -lt $samplesPerFrame; $i++) {
        if ($ToneHz -le 0) {
            $sample = 0
        }
        else {
            $t = (($FrameIndex * $samplesPerFrame) + $i) / $sampleRate
            $sample = [int16]([Math]::Sin(2.0 * [Math]::PI * $ToneHz * $t) * 2000)
        }
        $pair = [BitConverter]::GetBytes([int16]$sample)
        $bytes[$i * 2] = $pair[0]
        $bytes[($i * 2) + 1] = $pair[1]
    }

    return $bytes
}

$hello = '{"type":"hello","version":3,"features":{"mcp":true},"transport":"websocket","audio_params":{"format":"pcm_s16le","sample_rate":16000,"channels":1,"bits_per_sample":16,"frame_duration":20}}'
$listenStart = '{"session_id":"' + $SessionId + '","type":"listen","state":"start","mode":"auto_stop"}'
$listenStop = '{"session_id":"' + $SessionId + '","type":"listen","state":"stop"}'

$socket = [System.Net.WebSockets.ClientWebSocket]::new()
$socket.Options.SetRequestHeader("Authorization", "Bearer $token")

try {
    Write-Host "Connecting $Url"
    $socket.ConnectAsync([Uri]$Url, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    Write-Host "Connected: $($socket.State)"

    Send-TextFrame -Socket $socket -Text $hello
    Receive-AvailableFrames -Socket $socket -TimeoutMs $ReceiveTimeoutMs

    Send-TextFrame -Socket $socket -Text $listenStart
    Receive-AvailableFrames -Socket $socket -TimeoutMs $ReceiveTimeoutMs

    for ($i = 0; $i -lt $Frames; $i++) {
        $frame = New-PcmFrame -FrameIndex $i -ToneHz $ToneHz
        Send-BinaryFrame -Socket $socket -Bytes $frame
        Start-Sleep -Milliseconds 20
    }
    Write-Host ">> <binary pcm frames=$Frames bytes_per_frame=640>"

    Send-TextFrame -Socket $socket -Text $listenStop
    Receive-AvailableFrames -Socket $socket -TimeoutMs ($ReceiveTimeoutMs * 2)
}
finally {
    if ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
        $socket.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    }
    $socket.Dispose()
}

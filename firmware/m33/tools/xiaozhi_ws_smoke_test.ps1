param(
    [string]$Url = "ws://106.55.62.122:8011/api/rehab-arm/v1/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/devices/nanopi-m5/xiaozhi/ws?robot_id=rehab-arm-alpha",
    [Parameter(Mandatory = $true)]
    [string]$TokenFile,
    [string]$SessionId = "pc-smoke-session-001",
    [string]$DeviceId = "nanopi-m5",
    [string]$ClientId = "pc-smoke-client",
    [int]$Frames = 30,
    [int]$ToneHz = 440,
    [ValidateSet("pcm_s16le", "opus")]
    [string]$AudioFormat = "pcm_s16le",
    [string]$OpusPacketFile,
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

function Receive-ExpectedFrame {
    param(
        [System.Net.WebSockets.ClientWebSocket]$Socket,
        [int]$TimeoutMs,
        [string]$Step
    )

    if ($Socket.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
        throw "WebSocket is not open before receiving $Step; state=$($Socket.State)"
    }

    $buffer = New-Object byte[] 4096
    $segment = [System.ArraySegment[byte]]::new($buffer)
    $cts = [Threading.CancellationTokenSource]::new($TimeoutMs)
    try {
        $result = $Socket.ReceiveAsync($segment, $cts.Token).GetAwaiter().GetResult()
    }
    catch {
        throw "Timed out or failed while receiving $Step; state=$($Socket.State); error=$($_.Exception.Message)"
    }
    finally {
        $cts.Dispose()
    }

    if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
        throw "WebSocket closed while receiving $Step"
    }

    $payload = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count)
    Write-Host "<< $payload"
    return $payload
}

function New-PcmFrame {
    param(
        [int]$FrameIndex,
        [int]$ToneHz
    )

    $sampleRate = 16000
    $samplesPerFrame = 960
    $bytes = New-Object byte[] 1920

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

if ($AudioFormat -eq "opus" -and [string]::IsNullOrWhiteSpace($OpusPacketFile)) {
    throw "AudioFormat=opus requires OpusPacketFile. This script does not encode PCM into Opus on the PC."
}

$opusPackets = @()
if ($AudioFormat -eq "opus") {
    if (-not (Test-Path -LiteralPath $OpusPacketFile)) {
        throw "Opus packet file not found: $OpusPacketFile"
    }
    $raw = [System.IO.File]::ReadAllBytes($OpusPacketFile)
    if ($raw.Length -lt 2) {
        throw "Opus packet file is empty or invalid."
    }
    $offset = 0
    while ($offset + 2 -le $raw.Length) {
        $packetLen = [BitConverter]::ToUInt16($raw, $offset)
        $offset += 2
        if ($packetLen -eq 0 -or $offset + $packetLen -gt $raw.Length) {
            throw "Invalid Opus packet file at offset $offset."
        }
        $packet = New-Object byte[] $packetLen
        [System.Array]::Copy($raw, $offset, $packet, 0, $packetLen)
        $opusPackets += ,$packet
        $offset += $packetLen
    }
    if ($opusPackets.Count -eq 0) {
        throw "Opus packet file did not contain any packets."
    }
}

$hello = '{"type":"hello","version":1,"features":{"mcp":true},"transport":"websocket","audio_params":{"format":"' + $AudioFormat + '","sample_rate":16000,"channels":1,"frame_duration":60}}'
$listenStart = '{"session_id":"' + $SessionId + '","type":"listen","state":"start","mode":"auto"}'
$listenStop = '{"session_id":"' + $SessionId + '","type":"listen","state":"stop"}'

$socket = [System.Net.WebSockets.ClientWebSocket]::new()
$socket.Options.SetRequestHeader("Authorization", "Bearer $token")
$socket.Options.SetRequestHeader("Protocol-Version", "1")
$socket.Options.SetRequestHeader("Device-Id", $DeviceId)
$socket.Options.SetRequestHeader("Client-Id", $ClientId)

try {
    Write-Host "Connecting $Url"
    $null = $socket.ConnectAsync([Uri]$Url, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    Write-Host "Connected: $($socket.State)"

    Send-TextFrame -Socket $socket -Text $hello
    $null = Receive-ExpectedFrame -Socket $socket -TimeoutMs $ReceiveTimeoutMs -Step "hello ack"

    Send-TextFrame -Socket $socket -Text $listenStart
    $null = Receive-ExpectedFrame -Socket $socket -TimeoutMs $ReceiveTimeoutMs -Step "listen start ack"

    if ($AudioFormat -eq "opus") {
        for ($i = 0; $i -lt $opusPackets.Count; $i++) {
            Send-BinaryFrame -Socket $socket -Bytes $opusPackets[$i]
            Start-Sleep -Milliseconds 60
        }
        Write-Host ">> <binary opus_packets=$($opusPackets.Count)>"
    }
    else {
        for ($i = 0; $i -lt $Frames; $i++) {
            $frame = New-PcmFrame -FrameIndex $i -ToneHz $ToneHz
            Send-BinaryFrame -Socket $socket -Bytes $frame
            Start-Sleep -Milliseconds 60
        }
        Write-Host ">> <binary frames=$Frames bytes_per_frame=1920 declared_format=pcm_s16le>"
    }

    Send-TextFrame -Socket $socket -Text $listenStop
    $null = Receive-ExpectedFrame -Socket $socket -TimeoutMs ($ReceiveTimeoutMs * 2) -Step "listen stop/chat reply"
}
finally {
    if ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
        $socket.Abort()
    }
    $socket.Dispose()
}

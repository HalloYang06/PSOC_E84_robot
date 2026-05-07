param(
  [Parameter(Mandatory = $true)]
  [string]$SeatName,

  [Parameter(Mandatory = $true)]
  [string]$SessionId,

  [string]$InboxPath,
  [string]$OutboxPath,
  [string]$Model = "sonnet",
  [int]$PollIntervalSeconds = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# 初始化路径
if (-not $InboxPath) {
  $projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
  $InboxPath = Join-Path $projectRoot "artifacts\claude-messages\$SeatName\inbox"
}
if (-not $OutboxPath) {
  $projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
  $OutboxPath = Join-Path $projectRoot "artifacts\claude-messages\$SeatName\outbox"
}

# 确保目录存在
New-Item -ItemType Directory -Path $InboxPath -Force | Out-Null
New-Item -ItemType Directory -Path $OutboxPath -Force | Out-Null

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Claude NPC 消息桥接器已启动" -ForegroundColor Green
Write-Host "席位名称: $SeatName" -ForegroundColor Yellow
Write-Host "会话ID: $SessionId" -ForegroundColor Yellow
Write-Host "收件箱: $InboxPath" -ForegroundColor Gray
Write-Host "发件箱: $OutboxPath" -ForegroundColor Gray
Write-Host "轮询间隔: ${PollIntervalSeconds}秒" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "等待平台消息..." -ForegroundColor Yellow
Write-Host ""

$processedMessages = @{}

while ($true) {
  try {
    # 扫描inbox目录
    $messageFiles = Get-ChildItem -Path $InboxPath -Filter "*.json" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime

    foreach ($file in $messageFiles) {
      $messageId = $file.BaseName

      # 跳过已处理的消息
      if ($processedMessages.ContainsKey($messageId)) {
        continue
      }

      try {
        # 读取消息
        $messageJson = Get-Content -Path $file.FullName -Raw -Encoding UTF8
        $message = $messageJson | ConvertFrom-Json

        $title = if ($message.title) { $message.title } else { "协作指令" }
        $body = if ($message.body) { $message.body } else { if ($message.content) { $message.content } else { "" } }

        if (-not $body) {
          Write-Host "[警告] 消息 $messageId 内容为空，跳过" -ForegroundColor Yellow
          $processedMessages[$messageId] = $true
          continue
        }

        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "[收到平台消息] $title" -ForegroundColor Green
        Write-Host "消息ID: $messageId" -ForegroundColor Gray
        Write-Host "时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
        Write-Host "----------------------------------------" -ForegroundColor Cyan
        Write-Host $body -ForegroundColor White
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "[正在调用 Claude...]" -ForegroundColor Yellow
        Write-Host ""

        # 调用Claude CLI
        $claudeArgs = @(
          "--bare",
          "--session-id", $SessionId,
          "--model", $Model,
          "--output-format", "json",
          $body
        )

        $claudeOutput = & claude $claudeArgs 2>&1
        $exitCode = $LASTEXITCODE

        # 显示Claude的回复
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "[Claude 回复]" -ForegroundColor Green
        Write-Host "----------------------------------------" -ForegroundColor Cyan

        $replyText = ""
        $success = $true

        if ($exitCode -ne 0) {
          $replyText = "[错误] Claude 执行失败 (退出码: $exitCode)`n$($claudeOutput | Out-String)"
          Write-Host $replyText -ForegroundColor Red
          $success = $false
        } elseif ($claudeOutput) {
          try {
            $claudeJson = $claudeOutput | ConvertFrom-Json
            if ($claudeJson.content) {
              $replyText = $claudeJson.content
            } else {
              $replyText = $claudeOutput | Out-String
            }
          } catch {
            $replyText = $claudeOutput | Out-String
          }
          Write-Host $replyText -ForegroundColor White
        } else {
          $replyText = "(Claude 未返回内容)"
          Write-Host $replyText -ForegroundColor Yellow
        }

        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""

        # 写入回复到outbox
        $replyFile = Join-Path $OutboxPath "$messageId-reply.json"
        $reply = @{
          message_id = $messageId
          seat_name = $SeatName
          session_id = $SessionId
          reply_at = (Get-Date).ToUniversalTime().ToString("o")
          content = $replyText
          success = $success
          exit_code = $exitCode
          raw_output = $claudeOutput | Out-String
        }
        $reply | ConvertTo-Json -Depth 5 | Set-Content -Path $replyFile -Encoding UTF8

        # 标记为已处理
        $processedMessages[$messageId] = $true

        # 移动消息到processed目录
        $processedDir = Join-Path (Split-Path $InboxPath -Parent) "processed"
        New-Item -ItemType Directory -Path $processedDir -Force | Out-Null
        Move-Item -Path $file.FullName -Destination (Join-Path $processedDir $file.Name) -Force

        Write-Host "[消息已处理完成]" -ForegroundColor Green
        Write-Host ""
        Write-Host "等待平台消息..." -ForegroundColor Yellow
        Write-Host ""

      } catch {
        Write-Host "[错误] 处理消息 $messageId 失败: $_" -ForegroundColor Red
        Write-Host $_.ScriptStackTrace -ForegroundColor Red
        Write-Host ""

        # 写入错误回复
        try {
          $errorReplyFile = Join-Path $OutboxPath "$messageId-reply.json"
          $errorReply = @{
            message_id = $messageId
            seat_name = $SeatName
            session_id = $SessionId
            reply_at = (Get-Date).ToUniversalTime().ToString("o")
            content = "[桥接器错误] $_"
            success = $false
            error = $_.ToString()
          }
          $errorReply | ConvertTo-Json -Depth 5 | Set-Content -Path $errorReplyFile -Encoding UTF8
        } catch {
          Write-Host "[严重错误] 无法写入错误回复: $_" -ForegroundColor Red
        }

        # 标记为已处理，避免重复处理
        $processedMessages[$messageId] = $true
      }
    }

  } catch {
    Write-Host "[错误] 扫描inbox失败: $_" -ForegroundColor Red
    Write-Host ""
  }

  # 等待下一次轮询
  Start-Sleep -Seconds $PollIntervalSeconds
}

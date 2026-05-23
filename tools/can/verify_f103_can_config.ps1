param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

$ErrorActionPreference = 'Stop'

function Read-ProjectFile {
    param([string]$RelativePath)
    return Get-Content -Raw -LiteralPath (Join-Path $Root $RelativePath)
}

function Assert-Contains {
    param(
        [string]$Name,
        [string]$Text,
        [string]$Needle
    )

    if (-not $Text.Contains($Needle)) {
        throw "$Name missing expected text: $Needle"
    }
}

$canC = Read-ProjectFile 'Core\Src\can.c'
$ioc = Read-ProjectFile 'SenorsCollect.ioc'
$transport = Read-ProjectFile 'app\src\can_transport.c'
$appService = Read-ProjectFile 'app\src\app_service.c'
$jointScript = Read-ProjectFile 'tools\can\phase4_joint_validation.sh'

Assert-Contains 'Core CAN bitrate prescaler' $canC 'hcan.Init.Prescaler = 3;'
Assert-Contains 'Core CAN bit segment 1' $canC 'hcan.Init.TimeSeg1 = CAN_BS1_9TQ;'
Assert-Contains 'Core CAN bit segment 2' $canC 'hcan.Init.TimeSeg2 = CAN_BS2_2TQ;'
Assert-Contains 'IOC CAN bitrate' $ioc 'CAN.CalculateBaudRate=1000000'
Assert-Contains 'IOC CAN prescaler' $ioc 'CAN.Prescaler=3'
Assert-Contains 'IOC CAN bit segment 1' $ioc 'CAN.BS1=CAN_BS1_9TQ'
Assert-Contains 'IOC CAN bit segment 2' $ioc 'CAN.BS2=CAN_BS2_2TQ'

Assert-Contains 'CAN filter id' $transport 'filter.FilterIdHigh = (uint16_t)(F103_CAN_ID_CTRL_RX << 5U);'
Assert-Contains 'CAN filter id low' $transport 'filter.FilterIdLow = 0U;'
Assert-Contains 'CAN filter mask high' $transport 'filter.FilterMaskIdHigh = (uint16_t)(0x7FFU << 5U);'
Assert-Contains 'CAN filter mask low' $transport 'filter.FilterMaskIdLow = (uint16_t)(CAN_ID_EXT | CAN_RTR_REMOTE);'

Assert-Contains 'CAN transport debug default' $transport '#define CAN_TRANSPORT_DEBUG_UART 0'
Assert-Contains 'App CAN debug default' $appService '#define APP_CAN_DEBUG_UART 0'
Assert-Contains 'Joint validation starts stream' $jointScript 'cansend "${CAN_IF}" 7C0#0302000000000000'

Write-Host 'F103 CAN configuration checks passed.'

$ErrorActionPreference = "Stop"

$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$output = Join-Path $env:TEMP "app_ble_protocol_test.exe"

& gcc -std=c11 -Wall -Wextra -Werror `
    -I (Join-Path $repo "applications\m33") `
    (Join-Path $repo "applications\m33\app_ble_protocol.c") `
    (Join-Path $repo "tests\host\app_ble_protocol_test.c") `
    -o $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $output
exit $LASTEXITCODE

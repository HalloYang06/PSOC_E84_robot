$ErrorActionPreference = "Stop"

$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$output = Join-Path $env:TEMP "rehab_scurve_test.exe"

& gcc -std=c11 -Wall -Wextra -Werror `
    -I (Join-Path $repo "tests\host") `
    -I (Join-Path $repo "applications\control") `
    (Join-Path $repo "applications\control\rehab_scurve.c") `
    (Join-Path $repo "tests\host\rehab_scurve_test.c") `
    -lm `
    -o $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $output
exit $LASTEXITCODE

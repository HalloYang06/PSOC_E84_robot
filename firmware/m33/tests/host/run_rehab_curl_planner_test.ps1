$ErrorActionPreference = "Stop"

$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$output = Join-Path $env:TEMP "rehab_curl_planner_test.exe"

& gcc -std=c11 -Wall -Wextra -Werror `
    -I (Join-Path $repo "tests\host") `
    -I (Join-Path $repo "applications\control") `
    (Join-Path $repo "applications\control\rehab_curl_planner.c") `
    (Join-Path $repo "tests\host\rehab_curl_planner_test.c") `
    -o $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $output
exit $LASTEXITCODE

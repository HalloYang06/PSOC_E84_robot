$ErrorActionPreference = "Stop"
$env:INTERNAL_API_BASE_URL = "http://127.0.0.1:8010"
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8010"
$env:NEXT_PUBLIC_SUPERTOKENS_API_DOMAIN = "http://127.0.0.1:8010"
Set-Location (Split-Path -Parent $PSScriptRoot)
& npm.cmd --workspace apps/web run start -- --hostname 127.0.0.1 --port 3000

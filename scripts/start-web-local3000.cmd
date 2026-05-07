@echo off
set INTERNAL_API_BASE_URL=http://127.0.0.1:8010
set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010
set NEXT_PUBLIC_SUPERTOKENS_API_DOMAIN=http://127.0.0.1:8010
set REPO_ROOT=%~dp0..
cd /d %REPO_ROOT%
npm --workspace apps/web run dev -- --hostname 127.0.0.1 --port 3000 > "%REPO_ROOT%\apps\web\web-live3000-current.out.log" 2> "%REPO_ROOT%\apps\web\web-live3000-current.err.log"

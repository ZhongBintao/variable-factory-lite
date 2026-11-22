# 一键打开变量库工厂（单人版）：打开 OpenCode 后台和工厂服务，用浏览器打开。和双击桌面快捷方式一样。
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$env:PYTHONUTF8 = '1'
# 刚用 winget 装的 Python / Git / Node.js / OpenCode：旧窗口（包括 AI 助手的终端）还不认，从系统设置里把最新的 PATH 补进来
$env:Path = (@($env:Path -split ';') + @([Environment]::GetEnvironmentVariable('Path', 'Machine') -split ';') +
  @([Environment]::GetEnvironmentVariable('Path', 'User') -split ';') | Where-Object { $_ } | Select-Object -Unique) -join ';'
Set-Location -LiteralPath $PSScriptRoot
$VPY = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VPY)) { Write-Host '还没安装：先双击 install.cmd' -ForegroundColor Red; exit 1 }
& $VPY -X utf8 -m lite start @args
exit $LASTEXITCODE

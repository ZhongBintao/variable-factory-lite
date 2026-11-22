# 更新到新版：拉取最新代码 → 关掉旧的工厂服务 → 重新安装（依赖、自检、桌面快捷方式）。
# 你的论文和数据在 %USERPROFILE%\变量库工厂单人版\，更新不会动它们。
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$env:PYTHONUTF8 = '1'
# 刚用 winget 装的 Python / Git / Node.js / OpenCode：旧窗口（包括 AI 助手的终端）还不认，从系统设置里把最新的 PATH 补进来
$env:Path = (@($env:Path -split ';') + @([Environment]::GetEnvironmentVariable('Path', 'Machine') -split ';') +
  @([Environment]::GetEnvironmentVariable('Path', 'User') -split ';') | Where-Object { $_ } | Select-Object -Unique) -join ';'
Set-Location -LiteralPath $PSScriptRoot
$changes = git status --porcelain -- . ':!.venv' 2>$null
if ($changes) {
  Write-Host '仓库里有你改过的文件，先不更新（免得覆盖）。改动列表：' -ForegroundColor Yellow
  git status --short
  exit 1
}
$old = git describe --tags --always 2>$null
git pull --ff-only --tags
if ($LASTEXITCODE -ne 0) { Write-Host '拉取新版没成功（多半是网络问题），检查网络后再运行 update.cmd。' -ForegroundColor Red; exit 1 }
$new = git describe --tags --always 2>$null
$VPY = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path $VPY) { & $VPY -X utf8 -m lite stop | Out-Null }
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "已从 $(if ($old) { $old } else { '旧版' }) 更新到 $(if ($new) { $new } else { '新版' })。双击桌面快捷方式打开新版。"

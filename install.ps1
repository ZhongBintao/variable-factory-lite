# 变量库工厂（单人版）Windows 一键安装：检查环境 → 建 Python 虚拟环境、装依赖 → 自检 → 生成示例论文和数据 → 在桌面放快捷方式。
# 用法：双击仓库文件夹里的 install.cmd；或在 PowerShell 里运行  powershell -ExecutionPolicy Bypass -File .\install.ps1
# 可以重复运行（更新后再跑一次也行），不会删你的论文和数据（它们在 %USERPROFILE%\变量库工厂单人版\）。
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$env:PYTHONUTF8 = '1'
# 刚用 winget 装的 Python / Git / Node.js / OpenCode：旧窗口（包括 AI 助手的终端）还不认，从系统设置里把最新的 PATH 补进来
$env:Path = (@($env:Path -split ';') + @([Environment]::GetEnvironmentVariable('Path', 'Machine') -split ';') +
  @([Environment]::GetEnvironmentVariable('Path', 'User') -split ';') | Where-Object { $_ } | Select-Object -Unique) -join ';'
Set-Location -LiteralPath $PSScriptRoot
$HERE = (Get-Location).Path

function Ok($m)   { Write-Host "  √ $m" -ForegroundColor Green }
function Step($m) { Write-Host ''; Write-Host $m -ForegroundColor Cyan }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Fail($m, $how) {
  Write-Host ''; Write-Host "× $m" -ForegroundColor Red
  if ($how) { Write-Host "  怎么办：$how" }
  Write-Host '  （更多见 docs\常见问题.md）'
  exit 1
}
function Test-Py($exe, [string[]]$pre) {
  try {
    $out = & $exe @pre -c "import sys; print(sys.executable if sys.version_info >= (3, 12) else '')" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { $p = ([string]($out | Select-Object -Last 1)).Trim(); if ($p) { return $p } }
  } catch {}
  return $null
}

Step '1/6 检查电脑'
$v = [Environment]::OSVersion.Version
if ($v.Major -lt 10) { Fail "Windows 版本太旧（$v），需要 Windows 10 或 11。" '升级系统，或换一台电脑。' }
$name = if ($v.Build -ge 22000) { 'Windows 11' } else { 'Windows 10' }
Ok "$name（版本号 $($v.Build)，$env:PROCESSOR_ARCHITECTURE）"
if ($HERE -match 'OneDrive') {
  Warn '仓库放在 OneDrive 同步的文件夹里：同步时可能锁住文件、让安装或更新失败。'
  Write-Host "    建议挪到 $env:USERPROFILE\variable-factory-lite 再运行 install.cmd。"
}

Step '2/6 找 Python（要 3.12 或更新）'
$PY = $null
foreach ($c in @(@('py', '-3.13'), @('py', '-3.12'), @('py', '-3.14'), @('python'), @('python3'))) {
  $exe = $c[0]; $pre = @($c | Select-Object -Skip 1)
  if (Get-Command $exe -ErrorAction SilentlyContinue) { $PY = Test-Py $exe $pre; if ($PY) { break } }
}
if (-not $PY) {
  foreach ($d in @('Python313', 'Python312', 'Python314')) {
    $p = Join-Path $env:LOCALAPPDATA "Programs\Python\$d\python.exe"
    if (Test-Path $p) { $PY = Test-Py $p @(); if ($PY) { break } }
  }
}
if (-not $PY) {
  Fail '没找到 Python 3.12 或更新的版本。' ('运行：winget install --id Python.Python.3.13 -e ；或到 https://www.python.org/downloads/windows/ 下载安装包（安装时勾选“Add python.exe to PATH”）。' +
    '装好后关掉这个窗口，重新打开再运行 install.cmd')
}
Ok "Python $((& $PY --version 2>&1) -replace 'Python ', '')（$PY）"

Step '3/6 检查 Git 和 OpenCode（AI 对话靠它）'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  foreach ($p in @("$env:ProgramFiles\Git\cmd", "$env:LOCALAPPDATA\Programs\Git\cmd")) {
    if (Test-Path (Join-Path $p 'git.exe')) { $env:Path = "$p;$env:Path" }
  }
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Fail '没装 Git。' '运行：winget install --id Git.Git -e ；装好后关掉这个窗口，重新打开再运行 install.cmd'
}
Ok "$(git --version)"
$env:LITE_REPO = $HERE
$OC = & $PY -c "import os, sys; sys.path.insert(0, os.environ['LITE_REPO']); from lite import opencode; print(opencode.which() or '')"
$OC = ([string]($OC | Select-Object -Last 1)).Trim()
if (-not $OC) {
  Fail '没装 OpenCode。' ('先装 Node.js：winget install --id OpenJS.NodeJS.LTS -e ；关掉这个窗口、重新打开，再运行：npm install -g @opencode/cli ' +
    '（用 Scoop 的也可以 scoop install opencode）。装好后再运行 install.cmd')
}
$OCV = ''
$m = [regex]::Match([string](& $OC --version 2>$null), '(\d+)\.(\d+)\.(\d+)')
if ($m.Success) { $OCV = $m.Value }
if (-not $OCV -or [int]$m.Groups[1].Value -lt 2 -or ([int]$m.Groups[1].Value -eq 2 -and [int]$m.Groups[2].Value -lt 2)) {
  Fail "OpenCode 版本太旧（$(if ($OCV) { $OCV } else { '读不出版本' })），需要 2.2 或更新。" '运行：npm install -g @opencode/cli@latest （Scoop 装的运行 scoop update opencode），再运行 install.cmd'
}
Ok "OpenCode $OCV（$OC）"
if ([int]$m.Groups[1].Value -gt 2) { Warn '这个工具在 OpenCode 2.2.7 上测过；你的版本更新，大多能用，遇到问题见 docs\常见问题.md。' }

Step '4/6 建虚拟环境、装依赖（第一次要几分钟）'
$VPY = Join-Path $HERE '.venv\Scripts\python.exe'
if (-not (Test-Path $VPY) -or -not (Test-Py $VPY @())) {
  if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
  & $PY -m venv .venv
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VPY)) { Fail '虚拟环境没建成。' '把上面的报错发给帮你安装的 AI 或作者。' }
}
& $VPY -m pip install -q --disable-pip-version-check --upgrade pip
& $VPY -m pip install -q --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail '依赖没装上（多半是网络问题）。' '检查网络后再运行 install.cmd；公司或学校网络可能要先连 VPN。' }
Ok '依赖装好了（.venv\）'

Step '5/6 自检'
$log = Join-Path $env:TEMP 'variable-factory-lite-selftest.log'
$p = Start-Process -FilePath $VPY -ArgumentList @('-X', 'utf8', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests') -NoNewWindow -Wait -PassThru `
  -RedirectStandardOutput $log -RedirectStandardError "$log.err"
if ($p.ExitCode -ne 0) { Fail "自检没通过，日志在 $log" '把日志最后几十行发给帮你安装的 AI 或作者。' }
Ok '自检通过'
& $VPY -X utf8 -m lite sample-data | ForEach-Object { "  $_" }

Step '6/6 在桌面放快捷方式'
& $VPY -X utf8 -m lite install | ForEach-Object { "  $_" }

Write-Host ''
Write-Host '装好了。' -ForegroundColor Green -NoNewline
Write-Host ' 双击桌面上的“变量库工厂（单人版）”打开（或双击这里的 start.cmd）。'
Write-Host '第一次打开可能要等十几秒；浏览器里左边是和 AI 的对话，右边是工厂栏。用法见 README.md。'
exit 0

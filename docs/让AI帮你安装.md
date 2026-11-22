# 让 AI 帮你安装（复制提示词，发给你的 AI 编程助手）

适用于能在你电脑上运行命令的 AI 助手：Claude Code、Codex、Cursor、Trae、通义灵码等。
把下面**整段**复制给它，它会一步一步装好、打开，过程中用大白话告诉你在做什么。
装 Python、Git、Node.js、OpenCode 这几样是提示词里你同意过的；别的东西它会先问你。系统弹出的权限、防火墙窗口由你自己点。

## Windows

````text
请帮我在这台 Windows 电脑上安装并打开“变量库工厂（单人版）”。
仓库：https://github.com/ZhongBintao/variable-factory-lite （安装细节见仓库里的 AGENTS.md）
我没有编程经验：请一步一步做，每一步先用一句大白话告诉我在做什么；遇到报错先自己按提示处理，处理不了再问我。

【我同意的事】
- 缺什么就用 winget 装什么（只装缺的）：Python 3.13、Git、Node.js LTS；再用 npm 装 OpenCode（@opencode/cli）。
- 除了这几样，装别的软件之前先问我。

【规矩】
- 不要改 PowerShell 执行策略（Set-ExecutionPolicy）或任何系统设置；脚本一律用 powershell -ExecutionPolicy Bypass -File 运行。
- 不要向我要任何 API key，也不要读取、打印我电脑上的 key 或口令。
- 不要删除 %USERPROFILE%\变量库工厂单人版\ 里的东西（那是我的论文和数据）。
- 系统弹出的权限、防火墙、“是否允许”窗口：告诉我，由我自己点，你不要替我点。
- 命令都用 PowerShell 运行。如果你的终端是 bash（比如 Git Bash），就写成 powershell -NoProfile -ExecutionPolicy Bypass -Command '<命令>'，
  用单引号包住，免得 bash 把 $env: 这类写法吃掉。

【步骤】
1. 检查已经有什么（报错就说明没装）：
   git --version
   py -3.13 --version   （没有就试 python --version，要 3.12 或更新；弹出微软商店说明没装，关掉即可）
   node --version
   opencode --version   （要 2.2 或更新）
   winget --version
2. 只装缺的（winget 不存在：请我到微软商店安装“应用安装程序 / App Installer”后再继续）：
   winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements
   winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
   winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
   装完后，当前终端还认不出新命令，先刷新一下 PATH 再继续：
   $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
   然后装 OpenCode（已有但版本低于 2.2 就加 @latest 重装）：
   npm install -g @opencode/cli
   如果 npm 报错说找不到命令，刷新 PATH 后再试；还不行请我关掉终端重新打开。
3. 下载仓库到 %USERPROFILE%\variable-factory-lite（不要放进 OneDrive 同步的文件夹）：
   - 文件夹不存在：git clone https://github.com/ZhongBintao/variable-factory-lite.git "$env:USERPROFILE\variable-factory-lite"
   - 已经存在（以前装过）：运行 powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\variable-factory-lite\update.ps1"
     更新完直接跳到第 5 步。
4. 安装（第一次要几分钟）：
   powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\variable-factory-lite\install.ps1"
   它会检查环境、装依赖、自检、生成示例论文和练习数据、在桌面放快捷方式，最后显示“装好了”。
   中途停下时它会写“怎么办”：照做后重跑这一步。还不行看仓库里的 docs\常见问题.md。
5. 打开：
   powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\variable-factory-lite\start.ps1"
   浏览器会打开：左边是和 AI 的对话，右边是“工厂栏”。再确认一下状态：
   & "$env:USERPROFILE\variable-factory-lite\.venv\Scripts\python.exe" -X utf8 -m lite status
   应该看到“工厂服务（8797）：开着”和“OpenCode 后台：http://127.0.0.1:…”。
6. 最后用大白话告诉我：
   - 以后双击桌面上的“变量库工厂（单人版）”打开；
   - 练习材料在 %USERPROFILE%\变量库工厂单人版\示例数据\（一篇虚构的示例论文和几份练习数据），在工厂栏上传示例论文就能试；
   - 用法看仓库首页 README 的“五个核心功能怎么点”；以后更新就双击仓库文件夹里的 update.cmd；
   - 默认用 OpenCode 自带的免费模型，不用填 key；想换自己的模型，我自己在 PowerShell 里运行 opencode auth login。
````

## Mac

````text
请帮我在这台 Mac 上安装并打开“变量库工厂（单人版）”。
仓库：https://github.com/ZhongBintao/variable-factory-lite （安装细节见仓库里的 AGENTS.md）
我没有编程经验：请一步一步做，每一步先用一句大白话告诉我在做什么；遇到报错先自己按提示处理，处理不了再问我。

【我同意的事】缺什么就用 Homebrew 装什么（只装缺的）：python@3.13、opencode。没有 Homebrew 先问我要不要装。装别的软件之前先问我。
【规矩】不要向我要任何 API key，也不要读取、打印我电脑上的 key；不要删除 ~/变量库工厂单人版/ 里的东西；系统弹窗由我自己点。

【步骤】
1. 检查：sw_vers -productVersion（要 13 或更新）、python3 --version（要 3.12 或更新）、opencode --version（要 2.2 或更新）、brew --version。
2. 只装缺的：brew install python@3.13 ；brew install opencode （版本旧：brew upgrade opencode）。
3. 下载：~/variable-factory-lite 不存在就 git clone https://github.com/ZhongBintao/variable-factory-lite.git ~/variable-factory-lite ；
   已经存在就运行 ~/variable-factory-lite/update.sh，然后跳到第 5 步。
4. 安装：cd ~/variable-factory-lite && ./install.sh ，直到显示“装好了”；中途停下就照它写的“怎么办”处理后重跑。
5. 打开：~/variable-factory-lite/start.sh ；再运行 ~/variable-factory-lite/.venv/bin/python -m lite status 确认工厂服务开着。
6. 最后告诉我：以后双击桌面上的“变量库工厂（单人版）”打开；练习材料在 ~/变量库工厂单人版/示例数据/；用法看 README；更新运行 ./update.sh。
````

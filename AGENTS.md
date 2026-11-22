# 给 AI 助手的说明：帮用户装好、用起来“变量库工厂（单人版）”

用户把这个仓库交给你，多半是想让你帮他在 **macOS 或 Windows** 上装好并打开这个工具。用户可能没有编程经验：用大白话、一步一步说清在做什么。

用户可能直接贴给你一段安装提示词（`docs/让AI帮你安装.md`）：照它做；它和下面的步骤一致。

## 这是什么

一个本机运行的论文指标工具：OpenCode 网页（左边 AI 对话）+ 本工具插进去的“工厂栏”（右边）。
代码在 `lite/`（Python 3.12+，标准库 HTTP 服务 + MCP 工具 + 一个网页脚本），测试在 `tests/`。
用户的数据在 `~/变量库工厂单人版/`（Windows：`%USERPROFILE%\变量库工厂单人版\`），**不在仓库里**。

## 帮用户安装：macOS（照这个顺序）

1. 确认是 macOS 13+：`sw_vers -productVersion`。不是 Mac 就告诉用户不支持。
2. 建议把仓库放在家目录下，如 `~/variable-factory-lite`（放在桌面、文稿、下载里也能用，只是第一次打开时 macOS 会弹窗要用户点“允许”）。
3. 运行 `./install.sh`。它会检查 Python 3.12+ 和 OpenCode 2.2+，缺什么会停下并给出命令：
   - 缺 Python：`brew install python@3.13`（没有 Homebrew 先问用户是否要装 Homebrew，安装命令见 https://brew.sh ）。
   - 缺 OpenCode：`brew install opencode`；版本旧：`brew upgrade opencode`。
   - 装 Homebrew、Python、OpenCode 这类会改系统的步骤，**先征得用户同意**再运行。
   - 补好后再运行 `./install.sh`，直到最后显示“装好了”。
4. 告诉用户：双击桌面上的“变量库工厂（单人版）”打开（或运行 `./start.sh`）。如果 macOS 弹出“是否允许访问文件夹”，**请用户自己点“允许”**，你不要替用户点系统安全弹窗。
5. 浏览器打开后：左边是 AI 对话，右边是工厂栏。可以让用户用 `~/变量库工厂单人版/示例数据/` 里的虚构示例论文和练习数据试一遍（用法见 README.md“五个核心功能怎么点”）。

## 帮用户安装：Windows（照这个顺序）

1. 确认是 Windows 10 或 11（PowerShell：`[Environment]::OSVersion.Version`，Build ≥ 10240）。
2. 建议把仓库放在 `%USERPROFILE%\variable-factory-lite`，**不要放进 OneDrive 同步的文件夹**（同步会锁文件）。
3. 运行安装脚本。**你（AI）来运行时用这条**（不会停在“按任意键继续”）：
   `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1`
   （用户自己装就双击 `install.cmd`。Windows 默认不让运行 `.ps1`，`.cmd` 只给这一个脚本放行，不改系统设置。）
   它会检查 Python 3.12+、Git、OpenCode 2.2+，缺什么会停下并给出命令：
   - 缺 Python：`winget install --id Python.Python.3.13 -e`
   - 缺 Git：`winget install --id Git.Git -e`
   - 缺 OpenCode：先 `winget install --id OpenJS.NodeJS.LTS -e`，再 `npm install -g @opencode/cli`；版本旧：`npm install -g @opencode/cli@latest`
   - 这些会改系统的步骤，**先征得用户同意**再运行。winget 装完后新开的窗口才认新命令：你的终端可能要重开，或把装好的路径临时加进 `$env:Path`。
   - 补好后再运行安装脚本，直到最后显示“装好了”。
4. 告诉用户：双击桌面上的“变量库工厂（单人版）”快捷方式打开（或双击仓库里的 `start.cmd`）。Windows 防火墙如果弹窗，**请用户自己选**（点“取消”也不影响，工厂只在本机用）。
5. 浏览器打开后的用法和 macOS 一样（见 README.md“五个核心功能怎么点”）。
6. 不要改执行策略（`Set-ExecutionPolicy`）之类的系统设置；`.cmd` 已经够用。

## 模型和 key

- 不填 key 也能用：OpenCode 自带免费模型。
- 用户想用自己的模型：请**用户自己**在终端（Windows 是 PowerShell）运行 `opencode auth login` 并粘贴 key。
- **不要**向用户索要 key，不要把 key 打印出来、写进文件、贴进对话或提交进 Git。本工具也不读、不存 key。

## 排查

先看 `docs/常见问题.md`（按现象查）。常用命令：

```bash
./.venv/bin/python -m lite status                    # 各部分开着没有、数据在哪
tail -n 30 ~/变量库工厂单人版/日志/launcher.log       # 双击入口的过程
tail -n 30 ~/变量库工厂单人版/日志/server.log         # 工厂服务
./.venv/bin/python -m pytest -q tests                # 自检（不需要 OpenCode、不碰用户数据）
./.venv/bin/python -m lite stop                      # 关掉工厂服务（OpenCode 后台不动）
```

Windows（PowerShell，在仓库文件夹里）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m lite status
Get-Content -Tail 30 -Encoding utf8 "$env:USERPROFILE\变量库工厂单人版\日志\launcher.log"
Get-Content -Tail 30 -Encoding utf8 "$env:USERPROFILE\变量库工厂单人版\日志\server.log"
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests
.\.venv\Scripts\python.exe -X utf8 -m lite stop
```

## 规矩

- 不要删除或改动 `~/变量库工厂单人版/` 里的东西，除非用户明确要求（“恢复出厂”会彻底删除，删前跟用户确认）。
- 不要改用户的 OpenCode 全局配置（`~/.config/opencode/`）；本工具只在自己的工作区里放配置。
- 用户的论文和数据可能有版权或授权限制，不要上传到别处。
- 更新到新版用 `./update.sh`（Windows：`update.cmd`；你来运行时用 `powershell -NoProfile -ExecutionPolicy Bypass -File .\update.ps1`）。它会先检查仓库里有没有用户改过的文件。
- 这个仓库是从作者的私有仓库自动发布的，请不要在这里直接改代码再提交；有问题请到 GitHub 提 Issue。

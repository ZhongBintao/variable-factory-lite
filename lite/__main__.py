# -*- coding: utf-8 -*-
"""python -m lite <命令>

  start          一键打开（准备 → OpenCode 后台 → 工厂服务 → 浏览器）；加 --no-browser 不开浏览器
  stop           关掉工厂服务
  status         看看各部分开着没有
  install        在桌面放“变量库工厂（单人版）”
  launch         桌面入口调它（Windows 快捷方式）：打不开就弹窗说原因
  reset --yes    恢复出厂：彻底删掉全部论文、指标、数据和工厂对话（导出、示例数据不动）
  sample-data    生成练习用的虚构论文和合成数据（~/变量库工厂单人版/示例数据/，数值是随机造的）
  import-cards   重新带进旧库的变量定义（登记卡）
  import-data [文件夹]  把旧库变量的数据文件也带进来（人自己决定带不带）
  serve          前台跑工厂服务（start 会在后台调它）
  mcp            跑工厂工具（OpenCode 调它）
"""
import sys


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:]) or ["start"]
    if "--home" in a:                       # Windows 快捷方式带不了环境变量：试用目录从参数传
        i = a.index("--home")
        import os
        os.environ["LITE_HOME"] = a[i + 1]
        del a[i:i + 2]
    cmd = a[0]
    if cmd == "start":
        from . import app
        return app.start(browser="--no-browser" not in a)
    if cmd == "launch":
        from . import app
        return app.launch(browser="--no-browser" not in a)
    if cmd in ("stop", "status", "install"):
        from . import app
        return getattr(app, cmd)()
    if cmd == "reset":
        if "--yes" not in a:
            raise SystemExit("会彻底删掉全部论文、指标、数据和工厂对话，确定就加 --yes")
        from . import app
        r = app.reset()
        print("恢复出厂了：删掉 %d 个对话，重新带进旧库定义 %d 个" % (r["deleted_sessions"], r["oldlib"]))
        return
    if cmd == "serve":
        from . import server
        return server.serve()
    if cmd == "mcp":
        from . import mcp_server
        return mcp_server.main()
    if cmd == "sample-data":
        from . import sample
        print("练习数据放在：%s" % sample.make())
        print("示例论文：%s" % sample.make_paper())
        return
    if cmd == "import-cards":
        from . import library
        print("带进 %d 个旧库变量的定义" % library.import_cards())
        return
    if cmd == "import-data":
        from . import library
        print("带进 %d 个旧库变量的数据文件" % library.import_data(a[1] if len(a) > 1 else None))
        return
    print(__doc__)
    raise SystemExit(2)


if __name__ == "__main__":
    main()

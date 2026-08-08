# 资源管控中心-k8s日志采集工具

作者：SunZH

PySide6 + paramiko 实现的 K8S 工具（Windows / macOS）。

## 四页面

1. **① 主机配置**：SSH 主机增删改、测试连接；密码 base64 存储
2. **② 日志抓取**：选主机→自动连→命名空间→默认全不选，全选/取消全选，部署名可多选（勾选即选中该部署全部 Pod），支持单 Pod 勾选，搜索框在已选基础上过滤 → 日志类别（ALL/hycommon/hyframework）＋日志目录（默认 `/opt/logs`，可改，去该目录取日志）＋日志名（非空时匹配包含该名的 `.log`）→ 并发采集 → zip + manifest；输出框逐 Pod 显示文件数与总大小，结束时汇总
3. **③ 查询分析**：2 条条件过滤（等于/包含）/ 分组统计（文本结果）/ 关键字全字段模糊搜索 / 双击明细查看（含中文字段说明）/ 结果导出 HTML
4. **④ SSH 运维**：顶部选主机→自动连→命名空间后，任选预置日常运维命令（集群/节点/应用/存储四大类）或输入自定义命令，一键 SSH 到 MASTER 执行并回显结果；「管理运维项」支持新增/编辑/删除/停用（停用不下拉显示）/恢复默认，持久化到 config.json；结果支持导出 Excel（每命令一个工作表 + 汇总表）或导出 HTML；含停止按钮中断长命令

## 运行

```bash
python -m pip install -r requirements.txt
python main.py
```

## 测试

```bash
python -m pytest -v
```

## 说明

- 日志默认存 `./output/<日期>/<命名空间>/<部署名>/<Pod>/`，可在页面②选择存储目录
- 采集用 `tar czf -` 流式下载 + 4 线程并发，输出含 `pods_manifest.json`（完整 Pod JSON + 摘要）
- 配置存 `~/.k8s_log_getter/config.json`，软件自身日志存 `~/.k8s_log_getter/logs/app.log`

## 打包

- 打包说明见 [`docs/PACKAGING.md`](docs/PACKAGING.md)
- Windows：运行 `build.bat`；macOS：运行 `./build.sh`
- 打包产物在 `build/`、`dist/`（不入 git）

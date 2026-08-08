# 资源管控中心-k8s日志采集工具

作者：SunZH

PySide6 + paramiko 实现的 K8S 日志工具（Windows / macOS）。

## 三页面

1. **① 主机配置**：SSH 主机增删改、测试连接；密码 base64 存储
2. **② 日志抓取**：选主机→自动连→命名空间→按部署名/全部/勾选选 Pod × 日志类别（ALL/hycommon/hyframework）→ 并发采集 → zip + manifest；输出框逐 Pod 显示文件数与总大小，结束时汇总（总数/成功/失败/跳过/日志总大小）
3. **③ 查询分析**：Pod 元数据条件过滤（等于/包含）/ 分组统计（含 QtCharts 条形图）/ 关键字全字段模糊搜索 / 双击明细查看（含中文字段说明）

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

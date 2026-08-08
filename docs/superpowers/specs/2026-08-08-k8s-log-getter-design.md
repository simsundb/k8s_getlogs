# K8S 日志采集与分析工具 —— 设计文档

- 日期：2026-08-08
- 状态：已批准（头脑风暴确认）
- 运行平台：Windows / macOS（跨平台）

## 1. 概述

将原先手工 SSH 到 K8S Master 机执行 bash 脚本收集 Pod 日志的流程，改造成一个本地 Python 图形界面工具。工具通过 SSH 连接 K8S Master，自动执行 kubectl 命令，实现 **Pod 元数据查询分析** 与 **日志抓取打包** 两大功能。

## 2. 技术栈与环境

| 项 | 选择 | 说明 |
|----|------|------|
| GUI | PySide6 | 与用户既有 log_analyze 项目一致 |
| SSH | paramiko | 纯 Python，跨平台 |
| 打包 | 标准库 tarfile / zipfile / shutil | 无额外依赖 |
| 配置 | JSON 文件 + base64 | 跨平台，见 §9 |
| 路径 | pathlib | Windows / macOS 通用 |

跨平台约束：代码不得依赖任何平台专属库；SSH 密码用 base64 混淆存储（非真加密，仅防肉眼直读，用户明确要求简单方案）。

## 3. 页面结构

单主窗口，三个页面（向导式切换 / 左侧页签）：

| 页面 | 定位 | 内容 |
|------|------|------|
| ① SSH 主机配置 | 配置 | 主机增删改、测试连接 |
| ② 日志抓取 | 主功能 | 选主机→连→命名空间→Pod→类别→采集→打包 |
| ③ Pod 查询分析 | 主功能 | 选主机→连→命名空间→Pod 元数据查询/分析 |

页面 ② 与 ③ 共用「选主机→自动连接→命名空间下拉」逻辑，抽为共享组件 `HostNamespaceSelector`（§7）。

## 4. 页面 ①：SSH 主机配置

- 已保存主机表格：IP、端口、账号、备注（密码不显示明文）
- 按钮：新增 / 编辑 / 删除
- 表单字段：IP、端口（默认 22）、账号、密码、备注
- **测试连接**按钮：发起 SSH 连接验证连通性；可进一步验证 `kubectl` 命令可用（返回 kubectl 版本号），失败红字提示
- 配置持久化到本地 JSON（默认 `~/.k8s_log_getter/config.json`）

## 5. 页面 ②：日志抓取

流程：

```
选择 SSH 主机（下拉）
  → 自动 SSH 连接（失败红字提示，停留本页）
  → 自动执行 kubectl get namespaces → 命名空间下拉（可刷新）
  → 选择命名空间
  → 自动加载该命名空间下所有 Pod（一条 kubectl get pods -o json）
  → Pod 选择：全部 / 手动勾选
     勾选列表每行显示 [deployName] Pod名，带关键字搜索（按部署名/Pod名过滤）
  → 日志类别下拉：ALL / hycommon / hyframework
  → 开始采集 / 取消
  → 进度条 + 日志面板（每 Pod 一行状态）
  → 全部完成：打包 zip + 元数据 manifest → 自动打开输出目录
```

### Pod 选择 × 日志类别（两个组合维度）

| Pod 维度 | 取值 | 含义 |
|----------|------|------|
| Pod 范围 | 全部 Pod | 命名空间下所有 Pod |
| Pod 范围 | 手动勾选 | 只采集勾选的 Pod |

| 类别维度 | 取值 | 对应文件过滤（/opt/logs 顶层） |
|----------|------|-------------------------------|
| 日志类别 | ALL | `*.log` |
| 日志类别 | hycommon | `hycommon*.log` |
| 日志类别 | hyframework | `hyframework*.log` |

两维度正交组合，例如：全部 Pod × hycommon、勾选 Pod × ALL 等。

### 采集核心（每 Pod 一次往返）

```
kubectl exec <pod> -- sh -c "cd /opt/logs && tar czf - <pattern>"
  → stdout 流式写入本地 <pod>.tar.gz（边下边写，不占内存）
  → 解压到输出目录 → 删除临时 tar.gz
```

- 任务队列 + 4 个工作线程并发，每 worker 持有独立 SSH 连接
- 单 Pod 无匹配日志 / exec 失败 → 警告并跳过，不中断其它 Pod
- 取消 → 停止派发新任务，当前 Pod 完成后退出

### 输出目录结构（按部署名分组）

```
<存储目录>/               # 默认 = 软件当前目录下 output/，可在页面②点「选择存储目录」自定义
  <日期>/                # 例：2026-08-08
    <命名空间>/
      <部署名>/          # deployName 注解缺失时用 Pod 名
        <pod>/
          hycommon.xxx.log
      pods_manifest.json
  <日期>-<命名空间>-<类别>.zip   ← 最终压缩包（含 manifest）
```

- **存储目录**：默认 `软件当前目录/output/`；页面② 提供「选择存储目录」按钮，可用目录选择框改为任意本地目录，选择结果随配置保存
- 完成后自动打开存储目录
- 每次运行生成带日期目录，不覆盖历史

## 6. 页面 ③：Pod 查询分析

流程：

```
选择 SSH 主机（下拉）
  → 自动 SSH 连接
  → kubectl get namespaces → 命名空间下拉
  → 选择命名空间 → 一条 kubectl get pods -n <ns> -o json 加载全部 Pod 完整元数据
  → 查询 / 分析 / 搜索
  → 结果表格（可排序，点击行查看该 Pod 完整 JSON）
```

### 查询分析能力

**条件过滤**（多条件 AND 组合）：字段 + 操作符（等于 / 包含）+ 值
- 过滤字段：deployName、project、namespace、node、image、pipelineName、uuid/deploy、podIP、src、pod-template-hash

**分组统计**：选分组字段 → 计数
- 分组字段：project、node（节点负载分布）、deployName、image（版本分布）、status/ready

**排序/数值分析**
- restartCount（崩溃循环检测，降序查看反复重启的 Pod）
- startTime（部署时间线）

**关键字搜索**：对 deployName / image / node / project 等做包含式搜索

**明细查看**：点击结果行，弹出该 Pod 的完整 JSON（labels、annotations、containers、环境变量等）

## 7. 共享组件：HostNamespaceSelector

- 页面 ②③ 复用
- 组成：SSH 主机下拉 + 「连接并加载」/自动连接 + 命名空间下拉 + 「刷新」
- 行为：选中主机 → 自动建立 SSH 连接 → `kubectl get namespaces` 填充下拉
- 两页各自独立维护连接会话，互不干扰
- 连接失败：红字提示，不崩溃，可重试

## 8. Pod 元数据加载与 Manifest

**加载**：一条 `kubectl get pods -n <ns> -o json` 获取全部 Pod 对象，避免逐 Pod describe。

**deployName 获取**：优先读 `metadata.annotations.deployName`；缺失时以 Pod 名作为部署名（展示与目录分组均如此）。

**Manifest（pods_manifest.json）**：对每个采集到的 Pod 保存：
1. **完整 Pod JSON**（含 name、node、startTime、labels 全量、annotations 全量、containers 的 image/环境变量/restartCount/state、status、QoS、tolerations 等，等价于 describe 全部信息）
2. **精简摘要**，便于快速扫读：
   ```json
   {
     "pod": "ppl2-2078-...-s62cb",
     "deployName": "gbc-ai-assistant-service",
     "project": "k251182",
     "image": "devops.harbor.cn:.../gbc-ai-assistant-service:1.0.0",
     "node": "node-k251182-15f12e",
     "startTime": "2026-08-07 23:34:46 +0800",
     "podIP": "10.244.20.85",
     "restartCount": 0
   }
   ```

Manifest 打包进 zip 一并带走，供后续按 deployName / uuid / project 追溯分析。

## 9. 配置存储

- 路径：`~/.k8s_log_getter/config.json`（不进入代码仓库）
- 结构：`{"hosts": [{"ip","port","username","password_b64","remark"}]}`
- 密码 base64 编码存储（跨平台简单方案，非加密）
- 读取时 base64 解码回明文用于 SSH

## 10. 软件自身日志

工具自身运行日志，用于错误定位与调试。采用 Python 标准库 `logging`。

### 10.1 日志去向与轮转

| 项 | 值 |
|----|-----|
| 文件路径 | `~/.k8s_log_getter/logs/app.log` |
| 轮转 | `RotatingFileHandler`，单文件 1MB，保留最近 5 个（app.log.1~.5） |
| 控制台 | 开发模式可加 StreamHandler 输出到 stderr |
| 编码 | UTF-8（跨平台兼容，Windows 中文不乱码） |

### 10.2 日志级别使用约定

| 级别 | 场景 |
|------|------|
| DEBUG | SSH 命令执行明细、kubectl 命令与返回码、各 Pod 采集过程 |
| INFO | 应用启动/退出、连接成功、采集开始/结束汇总、打包完成 |
| WARNING | 单 Pod exec 失败、无匹配日志、命名空间加载失败但可重试 |
| ERROR | SSH 连接失败、配置读取损坏、未捕获异常 |

### 10.3 记录内容

- 时间戳 + 级别 + 模块名 + 消息
- **执行的 kubectl / SSH 命令**（便于复现调试），含退出码；stderr 截断到合理长度（如 2KB）防止日志爆涨
- **SSH 连接结果**：目标 IP、账号、成功/失败原因 —— **绝不记录密码/明文凭据**
- 每个 Pod 采集结果（成功/跳过/失败 + 文件数）
- 未捕获异常带完整 traceback（`logger.exception`）
- 采集会话维度：起止时间、主机、命名空间、Pod 数量、类别、输出目录

### 10.4 「其余日志」考虑

| 类型 | 说明 |
|------|------|
| 操作/审计日志 | 每次采集/查询的操作记录（谁/何时/哪台主机/哪个命名空间/结果），独立于 DEBUG 明细，便于回查历史操作。存 `~/.k8s_log_getter/logs/operations.jsonl` |
| 采集历史索引 | 已生成的 zip 及其输出目录、Pod 数、时间，供后续「加载历史采集结果」用（页面③ 分析可复用历史 manifest） |

> 安全约定：任何日志文件中均不得出现 SSH 密码、令牌等敏感明文。

## 11. 错误处理

| 场景 | 处理 |
|------|------|
| SSH 连接失败 / 密码错 | 页面红字提示，留在当前页可重试；记 ERROR 日志 |
| kubectl 不存在 / 无权限 | 日志面板显示 stderr；记 ERROR |
| 命名空间加载失败 | 红字提示，下拉清空；记 WARNING |
| 单 Pod exec 失败 / 无匹配日志 | 警告并跳过，继续其它 Pod；记 WARNING |
| 采集结束 | 汇总：成功 X / 跳过 Y / 失败 Z；记 INFO |
| 取消采集 | 停止派发新任务，当前 Pod 完成后退出；记 INFO |

## 12. 代码结构

```
main.py
src/
  config.py          # 配置读写 + base64 编解码
  logger.py          # 日志初始化（RotatingFileHandler + 级别约定 + 脱敏）
  ssh_client.py      # paramiko 封装：连接、流式执行命令、拉取 stdout 字节流
  k8s_client.py      # kubectl 封装：列命名空间、列 Pod(完整JSON)、tar 流式拉日志
  collector.py       # 任务队列 + 线程池（4 worker）并发采集
  models.py          # 数据类：HostConfig / CollectTask / CollectResult / PodMeta
  ui/
    main_window.py     # 主窗口 + 页面切换
    host_page.py       # 页面①：主机管理
    collect_page.py    # 页面②：日志抓取
    analyze_page.py    # 页面③：查询分析
    host_ns_selector.py# 共享组件：主机 + 命名空间选择
    log_panel.py       # 滚动日志面板
requirements.txt   # PySide6、paramiko
```

## 13. 测试

- **单元测试**：
  - 配置读写 + base64 编解码往返
  - 日志类别 → 文件 pattern 映射（ALL/hycommon/hyframework）
  - 输出目录结构生成（部署名分组、无注解回退 Pod 名）
  - tar 流处理（本地 tar 模拟，验证解压与空结果处理）
  - manifest 生成（摘要字段提取、完整 JSON 保存）
  - 日志脱敏（确认日志中无密码明文）
- **集成测试**：连接真实集群跑最小用例（1 个命名空间、少量 Pod）
- **跨平台验证**：Windows 与 macOS 各跑一遍界面启动、配置读写、日志轮转

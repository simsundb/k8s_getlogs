# ============================================================
# collect_hycommon_logs.ps1
# 功能：递归搜索指定目录中所有 *hycommon*.log 文件，
#       汇聚到一个目标文件夹中，自动处理重名冲突。
# 用法：右键用 PowerShell 运行，或命令行执行
#       powershell -ExecutionPolicy Bypass -File collect_hycommon_logs.ps1
# ============================================================

# ==================== 配置区域 ====================
# 搜索根目录（改成你自己的路径）
$RootPath = "C:\Users\Administrator\Desktop\ai_project\k8sLogTools\output"

# 汇聚目标文件夹（改成你自己的路径）
$DestPath = "C:\Users\Administrator\Desktop\ai_project\k8sLogTools\hycommon_logs_collected"

# 文件名匹配模式
$Filter = "*hycommon*.log"

# 重名策略：
#   "rename"  -> 自动加父目录前缀，如  logs_hycommon_2025.log
#   "skip"    -> 跳过重复文件，记录日志
#   "overwrite"-> 后复制的覆盖先复制的
$RenameStrategy = "rename"
# ==================================================

# 检查根目录是否存在
if (-not (Test-Path -Path $RootPath -PathType Container)) {
    Write-Host "[错误] 根目录不存在: $RootPath" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

# 创建目标文件夹
if (-not (Test-Path -Path $DestPath -PathType Container)) {
    New-Item -ItemType Directory -Path $DestPath -Force | Out-Null
    Write-Host "[创建] 目标文件夹: $DestPath" -ForegroundColor Green
}

# 搜索所有匹配文件
Write-Host "[搜索] 正在递归搜索: $RootPath" -ForegroundColor Cyan
Write-Host "[匹配] 模式: $Filter" -ForegroundColor Cyan
Write-Host ""

$files = Get-ChildItem -Path $RootPath -Recurse -Filter $Filter -File -ErrorAction SilentlyContinue

if ($files.Count -eq 0) {
    Write-Host "[结果] 未找到任何匹配文件。" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 0
}

Write-Host "[找到] 共 $($files.Count) 个文件，开始复制..." -ForegroundColor Green
Write-Host ""

# 统计
$successCount = 0
$skipCount    = 0
$errorCount   = 0
$totalSize    = 0

# 记录操作日志
$logFile  = Join-Path $DestPath "_copy_log.txt"
$logLines = @()
$logLines += "复制时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$logLines += "源目录: $RootPath"
$logLines += "匹配模式: $Filter"
$logLines += "文件总数: $($files.Count)"
$logLines += "----------------------------------------"

foreach ($file in $files) {
    $sourcePath = $file.FullName

    if ($RenameStrategy -eq "rename") {
        # 用"父目录_文件名"避免重名
        $parentDir = $file.Directory.Name
        $newName   = "$parentDir" + "_" + $file.Name

        # 如果还冲突，再加一层祖父目录
        $counter = 1
        $finalName = $newName
        while (Test-Path (Join-Path $DestPath $finalName)) {
            $finalName = [System.IO.Path]::GetFileNameWithoutExtension($newName) + "_$counter" + [System.IO.Path]::GetExtension($newName)
            $counter++
        }
    }
    elseif ($RenameStrategy -eq "skip") {
        $finalName = $file.Name
        if (Test-Path (Join-Path $DestPath $finalName)) {
            Write-Host "  [跳过] 已存在: $($file.Name)  (来自: $sourcePath)" -ForegroundColor Yellow
            $skipCount++
            $logLines += "SKIP : $sourcePath -> 已存在"
            continue
        }
    }
    else {
        # overwrite
        $finalName = $file.Name
    }

    $destFilePath = Join-Path $DestPath $finalName

    try {
        Copy-Item -Path $sourcePath -Destination $destFilePath -Force
        $successCount++
        $totalSize += $file.Length
        Write-Host "  [复制] $finalName" -ForegroundColor Gray
        Write-Host "         <- $sourcePath" -ForegroundColor DarkGray
        $logLines += "OK   : $sourcePath -> $finalName"
    }
    catch {
        $errorCount++
        Write-Host "  [错误] 复制失败: $sourcePath  ($_)" -ForegroundColor Red
        $logLines += "FAIL : $sourcePath -> $_"
    }
}

# 汇总
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  复制完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  成功: $successCount" -ForegroundColor Green
Write-Host "  跳过: $skipCount" -ForegroundColor Yellow
Write-Host "  失败: $errorCount" -ForegroundColor Red
Write-Host "  总大小: $([math]::Round($totalSize / 1MB, 2)) MB" -ForegroundColor Cyan
Write-Host "  目标文件夹: $DestPath" -ForegroundColor Cyan
Write-Host "  操作日志: $logFile" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 保存日志
$logLines += "----------------------------------------"
$logLines += "成功: $successCount | 跳过: $skipCount | 失败: $errorCount"
$logLines | Out-File -FilePath $logFile -Encoding UTF8

Read-Host "按回车键退出"
# ============================================================
# collect_hycommon_logs.ps1
# 功能：递归搜索指定目录中所有 *hycommon*.log 文件，
#       汇聚到一个目标文件夹中，自动处理重名冲突。
# 用法：右键用 PowerShell 运行，或命令行执行
#       powershell -ExecutionPolicy Bypass -File collect_hycommon_logs.ps1
# ============================================================

# ==================== 配置区域 ====================
# 搜索根目录（改成你自己的路径）
$RootPath = "D:\你的根目录"

# 汇聚目标文件夹（改成你自己的路径）
$DestPath = "D:\hycommon_logs_collected"

# 文件名匹配模式
$Filter = "*hycommon*.log"

# 重名策略：
#   "rename"  -> 自动加父目录前缀，如  logs_hycommon_2025.log
#   "skip"    -> 跳过重复文件，记录日志
#   "overwrite"-> 后复制的覆盖先复制的
$RenameStrategy = "rename"
# ==================================================

# 检查根目录是否存在
if (-not (Test-Path -Path $RootPath -PathType Container)) {
    Write-Host "[错误] 根目录不存在: $RootPath" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

# 创建目标文件夹
if (-not (Test-Path -Path $DestPath -PathType Container)) {
    New-Item -ItemType Directory -Path $DestPath -Force | Out-Null
    Write-Host "[创建] 目标文件夹: $DestPath" -ForegroundColor Green
}

# 搜索所有匹配文件
Write-Host "[搜索] 正在递归搜索: $RootPath" -ForegroundColor Cyan
Write-Host "[匹配] 模式: $Filter" -ForegroundColor Cyan
Write-Host ""

$files = Get-ChildItem -Path $RootPath -Recurse -Filter $Filter -File -ErrorAction SilentlyContinue

if ($files.Count -eq 0) {
    Write-Host "[结果] 未找到任何匹配文件。" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 0
}

Write-Host "[找到] 共 $($files.Count) 个文件，开始复制..." -ForegroundColor Green
Write-Host ""

# 统计
$successCount = 0
$skipCount    = 0
$errorCount   = 0
$totalSize    = 0

# 记录操作日志
$logFile  = Join-Path $DestPath "_copy_log.txt"
$logLines = @()
$logLines += "复制时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$logLines += "源目录: $RootPath"
$logLines += "匹配模式: $Filter"
$logLines += "文件总数: $($files.Count)"
$logLines += "----------------------------------------"

foreach ($file in $files) {
    $sourcePath = $file.FullName

    if ($RenameStrategy -eq "rename") {
        # 用"父目录_文件名"避免重名
        $parentDir = $file.Directory.Name
        $newName   = "$parentDir" + "_" + $file.Name

        # 如果还冲突，再加一层祖父目录
        $counter = 1
        $finalName = $newName
        while (Test-Path (Join-Path $DestPath $finalName)) {
            $finalName = [System.IO.Path]::GetFileNameWithoutExtension($newName) + "_$counter" + [System.IO.Path]::GetExtension($newName)
            $counter++
        }
    }
    elseif ($RenameStrategy -eq "skip") {
        $finalName = $file.Name
        if (Test-Path (Join-Path $DestPath $finalName)) {
            Write-Host "  [跳过] 已存在: $($file.Name)  (来自: $sourcePath)" -ForegroundColor Yellow
            $skipCount++
            $logLines += "SKIP : $sourcePath -> 已存在"
            continue
        }
    }
    else {
        # overwrite
        $finalName = $file.Name
    }

    $destFilePath = Join-Path $DestPath $finalName

    try {
        Copy-Item -Path $sourcePath -Destination $destFilePath -Force
        $successCount++
        $totalSize += $file.Length
        Write-Host "  [复制] $finalName" -ForegroundColor Gray
        Write-Host "         <- $sourcePath" -ForegroundColor DarkGray
        $logLines += "OK   : $sourcePath -> $finalName"
    }
    catch {
        $errorCount++
        Write-Host "  [错误] 复制失败: $sourcePath  ($_)" -ForegroundColor Red
        $logLines += "FAIL : $sourcePath -> $_"
    }
}

# 汇总
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  复制完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  成功: $successCount" -ForegroundColor Green
Write-Host "  跳过: $skipCount" -ForegroundColor Yellow
Write-Host "  失败: $errorCount" -ForegroundColor Red
Write-Host "  总大小: $([math]::Round($totalSize / 1MB, 2)) MB" -ForegroundColor Cyan
Write-Host "  目标文件夹: $DestPath" -ForegroundColor Cyan
Write-Host "  操作日志: $logFile" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 保存日志
$logLines += "----------------------------------------"
$logLines += "成功: $successCount | 跳过: $skipCount | 失败: $errorCount"
$logLines | Out-File -FilePath $logFile -Encoding UTF8

Read-Host "按回车键退出"

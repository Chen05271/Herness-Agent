# 启动 Dreaming 离线记忆合成 Worker（Python 3.11）
# 用法: .\run-dreaming.ps1
# 需配置 POSTGRES_DSN（持久化）与 REDIS_URL（队列）；至少其一可用
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
py -3.11 -m herness.dreaming.app

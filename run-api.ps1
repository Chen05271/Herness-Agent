# 启动 HTTP API 服务（Python 3.11）
# 用法: .\run-api.ps1
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
py -3.11 -m herness.api.app

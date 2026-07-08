# 启动 Herness 前端开发服务器
Set-Location $PSScriptRoot\web
if (-not (Test-Path node_modules)) {
    npm install
}
npm run dev

# 使用 Python 3.11 运行（项目要求 >=3.11，默认 python 可能是 3.8）
# 用法: .\run.ps1 "你的问题"
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if ($Args.Count -eq 0) {
    py -3.11 -m herness.main
} else {
    py -3.11 -m herness.main @Args
}

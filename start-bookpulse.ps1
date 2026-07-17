$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\pawel.urzyczyn\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
Set-Location -LiteralPath $project
& $python (Join-Path $project "app.py")

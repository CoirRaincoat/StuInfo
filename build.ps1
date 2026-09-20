$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm Friendbook.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item -LiteralPath README.md -Destination dist\Friendbook\README.md -Force
Copy-Item -LiteralPath demo -Destination dist\Friendbook -Recurse -Force
Copy-Item -LiteralPath docs -Destination dist\Friendbook -Recurse -Force
Write-Host 'Ready: dist\Friendbook\Friendbook.exe (distribute the entire folder)'

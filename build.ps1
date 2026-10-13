$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
$originalPath = $env:PATH
try {
    # PyInstaller resolves Qt's native dependencies through PATH while scanning.
    # A developer machine may put unrelated ICU/OpenSSL DLLs (for example from
    # Poppler) ahead of the Windows and PySide runtimes, producing a broken app.
    $env:PATH = @(
        "$env:SystemRoot\System32",
        $env:SystemRoot,
        "$PSScriptRoot\.venv\Scripts",
        "$PSScriptRoot\.venv\Lib\site-packages\PySide6",
        "$PSScriptRoot\.venv\Lib\site-packages\shiboken6"
    ) -join ';'
    & .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm Friendbook.spec
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
} finally {
    $env:PATH = $originalPath
}
Copy-Item -LiteralPath README.md -Destination dist\Friendbook\README.md -Force
Copy-Item -LiteralPath demo -Destination dist\Friendbook -Recurse -Force
Copy-Item -LiteralPath docs -Destination dist\Friendbook -Recurse -Force
Write-Host 'Ready: dist\Friendbook\Friendbook.exe (distribute the entire folder)'

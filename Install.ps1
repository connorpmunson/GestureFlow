[CmdletBinding()]
param([switch]$NoShortcut)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
        throw 'This build requires Windows on an Intel or AMD 64-bit processor. Native Windows ARM is not validated.'
    }
    foreach ($required in @('main.py', 'requirements-lock.txt', 'models\hand_landmarker.task', 'Start-GestureFlow.cmd', 'scripts\verify_install.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $required))) {
            throw "Missing $required. Extract the complete GestureFlow ZIP before running setup."
        }
    }
    $python = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate = & py -3.13 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $candidate }
    }
    if (-not $python -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $candidate = & python -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $candidate }
    }
    if (-not $python) { throw 'Install Python 3.13 (64-bit) from python.org first, then run Install.cmd again.' }
    & $python -c "import sys,struct,platform; assert sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8 and platform.machine().lower() in ('amd64','x86_64')"
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.13 (64-bit), then run setup again.' }
    $venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host 'Creating the local Python environment...'
        & $python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }
    & $venvPython -c "import sys,struct,platform; assert sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8 and platform.machine().lower() in ('amd64','x86_64')"
    if ($LASTEXITCODE -ne 0) { throw 'The existing .venv is incompatible. Use a freshly extracted project folder.' }
    Write-Host 'Installing pinned dependencies (internet required on first setup)...'
    & $venvPython -m pip install --only-binary=:all: -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection and rerun setup.' }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependencies are inconsistent.' }
    & $venvPython scripts\verify_install.py
    if ($LASTEXITCODE -ne 0) { throw 'Installation verification failed; see the details above.' }
    if (-not $NoShortcut) {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $wsh = New-Object -ComObject WScript.Shell
        $link = $wsh.CreateShortcut((Join-Path $desktop 'GestureFlow.lnk'))
        $link.TargetPath = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
        $link.Arguments = '"' + (Join-Path $PSScriptRoot 'main.py') + '"'
        $link.WorkingDirectory = $PSScriptRoot
        $link.IconLocation = Join-Path $PSScriptRoot 'gestureflow.ico'
        $link.Save()
    }
    Write-Host 'Setup verified. Open Start-GestureFlow.cmd or the GestureFlow desktop shortcut.' -ForegroundColor Green
    Write-Host 'Use Locate to select FlowSpeak on this laptop, and calibrate your hand range again.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

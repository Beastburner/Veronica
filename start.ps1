# VERONICA -- install dependencies (first run) then start all services
# Usage:
#   .\start.ps1              -- auto-install if needed, then launch
#   .\start.ps1 -install     -- force reinstall all dependencies, then launch
#   .\start.ps1 -dev         -- launch frontend in dev mode

param([switch]$dev, [switch]$install)

$root = $PSScriptRoot

function Write-Step($msg) { Write-Host "[VERONICA] $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  ERR $msg" -ForegroundColor Red }

# -- Verify prerequisites --------------------------------------------------

function Find-RealPython {
    # "py" is the Windows Python Launcher — installed to C:\Windows\ by winget/installer,
    # always wins over the Microsoft Store stub, most reliable on fresh Windows machines.
    foreach ($c in @("py", "python", "python3")) {
        if (Get-Command $c -ErrorAction SilentlyContinue) {
            $ver = & $c --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$ver" -match "Python 3") {
                return $c
            }
        }
    }
    # Fallback: check known install paths directly (winget silent install, no PATH update)
    $knownPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe"
    )
    foreach ($p in $knownPaths) {
        if (Test-Path $p) {
            $ver = & $p --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$ver" -match "Python 3") {
                return $p
            }
        }
    }
    return $null
}

$pythonCmd = Find-RealPython
if (-not $pythonCmd) {
    Write-Warn "Python not found -- attempting automatic install via winget..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 -e --silent --accept-source-agreements --accept-package-agreements
        # Refresh PATH so the new Python is visible in this session
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $pythonCmd = Find-RealPython
        if ($pythonCmd) {
            Write-OK "Python installed successfully"
        }
    } else {
        Write-Warn "winget not available on this machine."
    }
    if (-not $pythonCmd) {
        Write-Fail "Python install failed. Download Python 3.12 from https://python.org, run the installer (check 'Add to PATH'), then re-run this script."
        exit 1
    }
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Warn "Node.js not found -- attempting automatic install via winget..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id OpenJS.NodeJS.LTS -e --silent --accept-source-agreements --accept-package-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Fail "Node.js install failed. Download Node 18+ from https://nodejs.org, run the installer, then re-run this script."
        exit 1
    }
    Write-OK "Node.js installed successfully"
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Fail "npm not found. It ships with Node.js -- reinstall Node 18+ from https://nodejs.org"
    exit 1
}

Write-Step "Checking dependencies..."

# -- Python venv + API requirements ----------------------------------------

$venvPath = "$root\apps\api\.venv"
$reqPath  = "$root\apps\api\requirements.txt"

if ((-not (Test-Path $venvPath)) -or $install) {
    Write-Step "Creating Python virtual environment..."
    & $pythonCmd -m venv "$venvPath"
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to create venv."
        exit 1
    }
    Write-OK "Virtual environment created"
}

$pipExe = "$venvPath\Scripts\pip.exe"
if (-not (Test-Path $pipExe)) {
    Write-Fail "pip not found inside venv. Try deleting apps\api\.venv and re-running."
    exit 1
}

$stampFile = "$venvPath\.install_stamp"
$reqChanged = $true
if ((Test-Path $stampFile) -and (-not $install)) {
    $stampTime = (Get-Item $stampFile).LastWriteTime
    $reqTime   = (Get-Item $reqPath).LastWriteTime
    if ($stampTime -ge $reqTime) {
        $reqChanged = $false
    }
}

if ($reqChanged -or $install) {
    Write-Step "Installing Python packages (this may take a minute on first run)..."
    & $pipExe install -r "$reqPath"
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install failed."
        exit 1
    }
    New-Item -ItemType File -Path $stampFile -Force | Out-Null
    Write-OK "Python packages ready"
} else {
    Write-OK "Python packages up to date"
}

# -- WhatsApp bridge (Node) ------------------------------------------------

$waNM = "$root\apps\whatsapp\node_modules"
if ((-not (Test-Path $waNM)) -or $install) {
    Write-Step "Installing WhatsApp bridge dependencies..."
    Push-Location "$root\apps\whatsapp"
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "npm install failed for WhatsApp bridge."
        Pop-Location
        exit 1
    }
    Pop-Location
    Write-OK "WhatsApp bridge ready"
} else {
    Write-OK "WhatsApp bridge up to date"
}

# -- Frontend (Next.js) ----------------------------------------------------

$webNM = "$root\apps\web\node_modules"
if ((-not (Test-Path $webNM)) -or $install) {
    Write-Step "Installing frontend dependencies..."
    Push-Location "$root\apps\web"
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "npm install failed for frontend."
        Pop-Location
        exit 1
    }
    Pop-Location
    Write-OK "Frontend ready"
} else {
    Write-OK "Frontend up to date"
}

# -- Launch all services ---------------------------------------------------

function Start-Service {
    param($title, $dir, $cmd)
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$dir'; `$host.UI.RawUI.WindowTitle = '$title'; $cmd"
}

Write-Host ""
Write-Step "Starting all services..."

Start-Service -title "VERONICA - API" -dir "$root\apps\api" `
    -cmd "& .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"

Start-Service -title "VERONICA - WhatsApp" -dir "$root\apps\whatsapp" `
    -cmd "node index.js"

if ($dev) {
    Start-Service -title "VERONICA - Web (dev)" -dir "$root\apps\web" -cmd "npm run dev"
} else {
    Start-Service -title "VERONICA - Web" -dir "$root\apps\web" -cmd "npm run dev"
}

Write-Host ""
Write-Host "[VERONICA] All services launched." -ForegroundColor Green
Write-Host "  API       -> http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend  -> http://localhost:3000" -ForegroundColor White
Write-Host "  WhatsApp  -> http://localhost:3001" -ForegroundColor White
Write-Host ""
Write-Host "  Tip: run '.\start.ps1 -install' to force-reinstall all dependencies." -ForegroundColor DarkGray

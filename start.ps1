# VERONICA — start all services in separate windows
# Usage: .\start.ps1
# Optional: .\start.ps1 -dev   (Next.js in dev mode instead of prod)

param([switch]$dev)

$root = $PSScriptRoot

function Start-Service($title, $dir, $cmd) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$dir'; `$host.UI.RawUI.WindowTitle = '$title'; $cmd"
}

Write-Host "[VERONICA] Starting all services..." -ForegroundColor Cyan

# 1 — FastAPI backend
Start-Service "VERONICA · API" "$root\apps\api" `
    "& .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"

# 2 — WhatsApp bridge (API auto-starts it too, but running standalone gives visible logs)
Start-Service "VERONICA · WhatsApp" "$root\apps\whatsapp" `
    "node index.js"

# 3 — Next.js frontend
if ($dev) {
    Start-Service "VERONICA · Web (dev)" "$root\apps\web" "npm run dev"
} else {
    Start-Service "VERONICA · Web" "$root\apps\web" "npm run dev"
}

Write-Host "[VERONICA] All services launching in separate windows." -ForegroundColor Green
Write-Host "  API       → http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend  → http://localhost:3000" -ForegroundColor White
Write-Host "  WhatsApp  → http://localhost:3001" -ForegroundColor White

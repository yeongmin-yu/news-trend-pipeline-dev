[CmdletBinding()]
param(
    [switch]$BuildImages
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "docker-compose.yml"
$runtimeRoot = Join-Path $projectRoot "runtime"

function Assert-ProjectRoot {
    if (-not (Test-Path -LiteralPath $composeFile)) {
        throw "docker-compose.yml not found: $composeFile"
    }
}

function Clear-RuntimeDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }

    Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
}

function Restore-GitKeep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }

    $gitkeep = Join-Path $Path ".gitkeep"
    New-Item -ItemType File -Path $gitkeep -Force | Out-Null
}

Assert-ProjectRoot

$composeUpArgs = @("compose", "up", "-d")
if ($BuildImages) {
    $composeUpArgs += "--build"
}

Write-Host "[1/4] docker compose down -v --remove-orphans"
Push-Location $projectRoot
try {
    docker compose down -v --remove-orphans

    Write-Host "[2/4] runtime directory cleanup"
    $runtimeDirs = @(
        (Join-Path $runtimeRoot "checkpoints"),
        (Join-Path $runtimeRoot "state"),
        (Join-Path $runtimeRoot "spark-events"),
        (Join-Path $runtimeRoot "logs")
    )

    foreach ($dir in $runtimeDirs) {
        Clear-RuntimeDirectory -Path $dir
        Restore-GitKeep -Path $dir
    }

    Write-Host "[3/4] docker compose up -d$(if ($BuildImages) { ' --build' })"
    & docker @composeUpArgs

    Write-Host "[4/4] docker compose ps"
    docker compose ps
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Full reset complete."
Write-Host "Note: app-postgres and airflow-postgres volumes were removed, so dictionary tables were also reset."
if (-not $BuildImages) {
    Write-Host "Tip: use -BuildImages when Dockerfile or requirements changed."
}

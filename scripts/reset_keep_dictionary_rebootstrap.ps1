[CmdletBinding()]
param(
    [switch]$BuildImages
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "docker-compose.yml"
$runtimeRoot = Join-Path $projectRoot "runtime"
$composeProjectName = "news-trend-develop"
$airflowVolumeName = "${composeProjectName}_airflow-postgres-data"
$appPostgresService = "app-postgres"
$airflowPostgresService = "airflow-postgres"

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

function Remove-DockerVolumeIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VolumeName
    )

    $existing = docker volume ls --format "{{.Name}}" | Where-Object { $_ -eq $VolumeName }
    if ($existing) {
        docker volume rm $VolumeName | Out-Null
    }
}

function Wait-ForContainerHealthy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ServiceName,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $containerId = docker compose ps -q $ServiceName
        if ($containerId) {
            $status = docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $containerId
            if ($status -eq "healthy" -or $status -eq "running") {
                return
            }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "Timed out waiting for service '$ServiceName' to become healthy."
}

Assert-ProjectRoot

$composeUpArgs = @("compose", "up", "-d")
if ($BuildImages) {
    $composeUpArgs += "--build"
}

Write-Host "[1/6] docker compose down --remove-orphans"
Push-Location $projectRoot
try {
    docker compose down --remove-orphans

    Write-Host "[2/6] remove Airflow metadata volume only"
    Remove-DockerVolumeIfExists -VolumeName $airflowVolumeName

    Write-Host "[3/6] runtime directory cleanup"
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

    $dbUpArgs = @("compose", "up", "-d")
    if ($BuildImages) {
        $dbUpArgs += "--build"
    }
    $dbUpArgs += @($appPostgresService, $airflowPostgresService)

    Write-Host "[4/6] start PostgreSQL services$(if ($BuildImages) { ' --build' })"
    & docker @dbUpArgs
    Wait-ForContainerHealthy -ServiceName $appPostgresService

    Write-Host "[5/6] truncate article and aggregate tables, preserve dictionaries"
    $truncateSql = @"
TRUNCATE TABLE
    stg_keyword_relations,
    stg_keyword_trends,
    stg_keywords,
    stg_news_raw,
    keyword_relations,
    keyword_trends,
    keywords,
    news_raw
RESTART IDENTITY;
"@
    $truncateSql | docker compose exec -T $appPostgresService psql -U postgres -d news_pipeline

    Write-Host "[6/6] docker compose up -d$(if ($BuildImages) { ' --build' })"
    & docker @composeUpArgs

    Write-Host "[done] docker compose ps"
    docker compose ps
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Reset complete."
Write-Host "Note: dictionary tables were preserved, but article/aggregate tables and Airflow metadata were reset."
if (-not $BuildImages) {
    Write-Host "Tip: use -BuildImages when Dockerfile or requirements changed."
}

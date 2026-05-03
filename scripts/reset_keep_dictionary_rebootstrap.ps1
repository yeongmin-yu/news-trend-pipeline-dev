[CmdletBinding()]
param(
    [switch]$BuildImages
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "docker-compose.yml"
$runtimeRoot = Join-Path $projectRoot "runtime"
$appPostgresService = "app-postgres"

# This script resets only collected/processed data so ingestion can be replayed from scratch.
# It intentionally preserves configuration and dictionary tables, including:
# - domain_catalog
# - query_keywords and query_keyword_audit_logs
# - compound_noun_dict and compound_noun_candidates
# - stopword_dict and stopword_candidates
# - dictionary_versions and dictionary_audit_logs
# - RSS catalog files and application source/configuration files
# - Airflow metadata DB/volume

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

function Invoke-Docker {
    param([string[]]$DockerArgs)
    $cmdLine = "docker " + ($DockerArgs -join ' ')
    cmd /c "$cmdLine 2>nul"
    if ($LASTEXITCODE -ne 0) {
        throw "$cmdLine failed with exit code $LASTEXITCODE"
    }
}

Assert-ProjectRoot

$composeUpArgs = @("compose", "up", "-d")
if ($BuildImages) {
    $composeUpArgs += "--build"
}

Write-Host "[1/5] docker compose down --remove-orphans"
Push-Location $projectRoot
try {
    Invoke-Docker @("compose", "down", "--remove-orphans")

    Write-Host "[2/5] runtime collection state cleanup"
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
    $dbUpArgs += @($appPostgresService)

    Write-Host "[3/5] start application PostgreSQL$(if ($BuildImages) { ' --build' })"
    Invoke-Docker $dbUpArgs
    Wait-ForContainerHealthy -ServiceName $appPostgresService

    Write-Host "[4/5] truncate collected article and derived data only"
    $truncateSql = @"
TRUNCATE TABLE
    stg_keyword_relations,
    stg_keyword_trends,
    stg_keywords,
    stg_news_raw,
    keyword_relations,
    keyword_trends,
    keyword_events,
    collection_metrics,
    keywords,
    news_raw
RESTART IDENTITY;
"@
    $truncateSql | cmd /c "docker compose exec -T $appPostgresService psql -U postgres -d news_pipeline 2>nul"
    if ($LASTEXITCODE -ne 0) { throw "TRUNCATE failed" }

    Write-Host "[5/5] docker compose up -d$(if ($BuildImages) { ' --build' })"
    Invoke-Docker $composeUpArgs

    Write-Host "[done] docker compose ps"
    Invoke-Docker @("compose", "ps")
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Collection-data reset complete."
Write-Host "Preserved: domain/query settings, dictionaries, dictionary candidates/audits, RSS catalog, Airflow metadata."
Write-Host "Reset: news_raw, keywords, keyword_trends, keyword_relations, keyword_events, collection_metrics, staging tables, producer state, Spark checkpoints/events/logs."
if (-not $BuildImages) {
    Write-Host "Tip: use -BuildImages when Dockerfile or requirements changed."
}

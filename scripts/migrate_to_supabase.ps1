param(
    [Parameter(Mandatory = $false)]
    [string]$SupabaseUrl = $env:SUPABASE_DATABASE_URL,

    [Parameter(Mandatory = $false)]
    [string]$SqliteUrl = "sqlite:///./database.db",

    [Parameter(Mandatory = $false)]
    [int]$BatchSize = 500
)

if (-not $SupabaseUrl) {
    Write-Error "SUPABASE_DATABASE_URL not provided. Pass -SupabaseUrl or set env var."
    exit 1
}

if ($SupabaseUrl.StartsWith("postgresql://")) {
    $SupabaseUrl = "postgresql+asyncpg://" + $SupabaseUrl.Substring("postgresql://".Length)
} elseif ($SupabaseUrl.StartsWith("postgres://")) {
    $SupabaseUrl = "postgresql+asyncpg://" + $SupabaseUrl.Substring("postgres://".Length)
}

$env:DATABASE_URL = $SupabaseUrl

Write-Host "Running Alembic migrations on Supabase..."
uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Error "Alembic upgrade failed."
    exit $LASTEXITCODE
}

Write-Host "Migrating data from SQLite to Supabase..."
uv run python scripts/migrate_sqlite_to_supabase.py `
    --sqlite-url $SqliteUrl `
    --postgres-url $SupabaseUrl `
    --batch-size $BatchSize

if ($LASTEXITCODE -ne 0) {
    Write-Error "Data migration failed."
    exit $LASTEXITCODE
}

Write-Host "Supabase migration completed."

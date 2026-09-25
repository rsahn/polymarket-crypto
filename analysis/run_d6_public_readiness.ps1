# Explicit public-provider diagnostic. No .env edit and no monetary runner.
$ErrorActionPreference = 'Stop'
$previousRpc = $env:POLYGON_ARCHIVE_RPC_URL
$runExitCode = 1
try {
    $env:REAL_ORDERS_ENABLED = 'false'
    $env:LIVE_EXECUTION_ARMED = 'false'
    $env:POLYGON_ARCHIVE_RPC_URL = 'https://polygon.drpc.org'
    & python (Join-Path $PSScriptRoot 'qualify_post_genesis.py') --target-machine --health-contract --diagnostics
    $runExitCode = $LASTEXITCODE
}
finally {
    $env:POLYGON_ARCHIVE_RPC_URL = $previousRpc
}
exit $runExitCode

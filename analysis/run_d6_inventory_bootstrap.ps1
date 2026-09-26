# One public-only bootstrap. No qualification, WS, credentials or monetary runner.
$ErrorActionPreference = 'Stop'
$previousRpc = $env:POLYGON_ARCHIVE_RPC_URL
$previousOrders = $env:REAL_ORDERS_ENABLED
$previousArmed = $env:LIVE_EXECUTION_ARMED
$runExitCode = 1
try {
    $env:REAL_ORDERS_ENABLED = 'false'
    $env:LIVE_EXECUTION_ARMED = 'false'
    # Same explicit public endpoint as run_d6_public_readiness.ps1.
    $env:POLYGON_ARCHIVE_RPC_URL = 'https://polygon.drpc.org'
    & python -B (Join-Path $PSScriptRoot 'run_inventory_catchup.py') --bootstrap
    $runExitCode = $LASTEXITCODE
}
finally {
    $env:POLYGON_ARCHIVE_RPC_URL = $previousRpc
    $env:REAL_ORDERS_ENABLED = $previousOrders
    $env:LIVE_EXECUTION_ARMED = $previousArmed
}
exit $runExitCode

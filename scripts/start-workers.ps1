[CmdletBinding()]
param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "start",

    [string]$ProjectRoot = "",

    [string]$WorkerTarget = "backend.workers.arq_worker.WorkerSettings",

    [string[]]$Queues = @("light", "default", "heavy"),

    [int]$DefaultConcurrency = 1,

    [switch]$ShowWindows,

    [hashtable]$ConcurrencyByQueue = @{
        light    = 8
        default  = 3
        heavy    = 1
    }
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
}
else {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
}

$pidDir = Join-Path $ProjectRoot ".run\workers"
$logDir = Join-Path $ProjectRoot "logs\workers"

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-PidFilePath {
    param([Parameter(Mandatory = $true)][string]$Queue)
    return Join-Path $pidDir ("worker-" + $Queue + ".pid")
}

function Get-LogFilePath {
    param([Parameter(Mandatory = $true)][string]$Queue)
    return Join-Path $logDir ($Queue + ".log")
}

function Get-RunningProcessByQueue {
    param([Parameter(Mandatory = $true)][string]$Queue)
    $pidFile = Get-PidFilePath -Queue $Queue
    if (-not (Test-Path -LiteralPath $pidFile)) {
        return $null
    }

    $pidText = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($pidText)) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $processId = 0
    if (-not [int]::TryParse($pidText, [ref]$processId)) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        return $null
    }
    return $proc
}

function Stop-QueueWorker {
    param([Parameter(Mandatory = $true)][string]$Queue)

    $proc = Get-RunningProcessByQueue -Queue $Queue
    if ($null -eq $proc) {
        Write-Host ("[{0}] worker not running" -f $Queue)
        return
    }

    try {
        Stop-Process -Id $proc.Id -Force -ErrorAction Stop
        Write-Host ("[{0}] stopped pid={1}" -f $Queue, $proc.Id)
    }
    catch {
        Write-Warning ("[{0}] failed to stop pid={1}: {2}" -f $Queue, $proc.Id, $_.Exception.Message)
    }

    $pidFile = Get-PidFilePath -Queue $Queue
    if (Test-Path -LiteralPath $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }
}

function Start-QueueWorker {
    param(
        [Parameter(Mandatory = $true)][string]$Queue,
        [Parameter(Mandatory = $true)][int]$Concurrency
    )

    $existing = Get-RunningProcessByQueue -Queue $Queue
    if ($null -ne $existing) {
        Write-Host ("[{0}] already running pid={1} (skip)" -f $Queue, $existing.Id)
        return
    }

    $logFile = Get-LogFilePath -Queue $Queue
    $pidFile = Get-PidFilePath -Queue $Queue
    $queueName = if ($Queue -eq "default") { "driver:jobs" } else { "driver:jobs:$Queue" }

    $commandChain = @(
        "set ""WORKER_QUEUE_NAME=$queueName""",
        "set ""WORKER_CONCURRENCY=$Concurrency""",
        "uv run arq $WorkerTarget"
    ) -join " && "

    $cmdExpression = $commandChain + " >> """ + $logFile + """ 2>&1"
    $startParams = @{
        FilePath         = "cmd.exe"
        ArgumentList     = @("/c", $cmdExpression)
        WorkingDirectory = $ProjectRoot
        PassThru         = $true
    }
    if (-not $ShowWindows.IsPresent) {
        $startParams["WindowStyle"] = "Hidden"
    }
    $proc = Start-Process @startParams

    Set-Content -LiteralPath $pidFile -Value $proc.Id -Encoding ascii
    Write-Host ("[{0}] started pid={1} concurrency={2} log={3}" -f $Queue, $proc.Id, $Concurrency, $logFile)
}

function Show-Status {
    param([Parameter(Mandatory = $true)][string[]]$QueueList)
    foreach ($queue in $QueueList) {
        $proc = Get-RunningProcessByQueue -Queue $queue
        if ($null -eq $proc) {
            Write-Host ("[{0}] stopped" -f $queue)
        }
        else {
            Write-Host ("[{0}] running pid={1}" -f $queue, $proc.Id)
        }
    }
}

Ensure-Directory -Path $pidDir
Ensure-Directory -Path $logDir

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uvCommand) {
    throw "uv not found in PATH."
}

switch ($Action) {
    "start" {
        foreach ($queue in $Queues) {
            $concurrency = $DefaultConcurrency
            if ($ConcurrencyByQueue.ContainsKey($queue)) {
                $concurrency = [int]$ConcurrencyByQueue[$queue]
            }
            if ($concurrency -le 0) {
                $concurrency = 1
            }
            Start-QueueWorker -Queue $queue -Concurrency $concurrency
        }
    }
    "stop" {
        foreach ($queue in $Queues) {
            Stop-QueueWorker -Queue $queue
        }
    }
    "restart" {
        foreach ($queue in $Queues) {
            Stop-QueueWorker -Queue $queue
        }
        foreach ($queue in $Queues) {
            $concurrency = $DefaultConcurrency
            if ($ConcurrencyByQueue.ContainsKey($queue)) {
                $concurrency = [int]$ConcurrencyByQueue[$queue]
            }
            if ($concurrency -le 0) {
                $concurrency = 1
            }
            Start-QueueWorker -Queue $queue -Concurrency $concurrency
        }
    }
    "status" {
        Show-Status -QueueList $Queues
    }
}

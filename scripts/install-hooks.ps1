# Install the shipwright pre-commit gates on Windows / PowerShell hosts.
# Mirrors scripts/install-hooks.sh.  Idempotent + non-destructive.
#
# Usage:
#   .\scripts\install-hooks.ps1           # install / verify
#   .\scripts\install-hooks.ps1 -Force    # override existing path

[CmdletBinding()]
param(
    [switch] $Force
)

$ErrorActionPreference = 'Stop'

$targetPath = 'scripts/hooks'

$repoRoot = (& git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

$current = ''
try {
    $current = (& git config --local --default '' core.hooksPath).Trim()
} catch {
    $current = ''
}

if ($current -eq $targetPath) {
    Write-Host "install-hooks: core.hooksPath already set to '$targetPath' - ok"
    exit 0
}

if ($current -and -not $Force) {
    Write-Error @"
install-hooks: refused to overwrite existing core.hooksPath.

  current value:    $current
  shipwright wants: $targetPath

To replace it run:
  .\scripts\install-hooks.ps1 -Force

To restore the previous value later:
  git config --local core.hooksPath '$current'
"@
    exit 1
}

& git config --local core.hooksPath $targetPath
Write-Host "install-hooks: core.hooksPath -> $targetPath"

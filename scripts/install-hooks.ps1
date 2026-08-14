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
# -LiteralPath: a clone under a directory containing [ or ] (legal on Windows)
# would otherwise be treated as a wildcard pattern and resolve wrongly.
Set-Location -LiteralPath $repoRoot

# `--get` rather than `--default ''`: --default was added in Git 2.18, and on an
# older git the unknown option makes git error out with no stdout. Captured in
# parens that yields $null, and $null.Trim() throws — caught below, which sets
# $current = '' regardless of whether the key was actually set. That skips the
# refuse-to-clobber branch and silently overwrites a foreign hooksPath — the one
# thing this script must never do. `--get` exits 1 with no output when the key is
# simply unset, which is the case we want to treat as empty, and it works on
# every git version.
$current = ''
try {
    $current = (& git config --local --get core.hooksPath).Trim()
} catch {
    $current = ''
}

if ($current -eq $targetPath) {
    Write-Host "install-hooks: core.hooksPath already set to '$targetPath' - ok"
    exit 0
}

if ($current -and -not $Force) {
    # NOT Write-Error: under $ErrorActionPreference='Stop' it raises a
    # terminating error, which aborts the script before the `exit 1` below can
    # run. A caller that dot-sources this script wrapped in try/catch (a normal
    # defensive pattern) swallows that error and continues with a stale, likely
    # zero, $LASTEXITCODE — reading success where the install was refused.
    # Writing to stderr directly and exiting explicitly makes the failure signal
    # reliable regardless of how the caller invokes the script.
    [Console]::Error.WriteLine(@"
install-hooks: refused to overwrite existing core.hooksPath.

  current value:    $current
  shipwright wants: $targetPath

To replace it run:
  .\scripts\install-hooks.ps1 -Force

To restore the previous value later:
  git config --local core.hooksPath '$current'
"@)
    exit 1
}

& git config --local core.hooksPath $targetPath
# $ErrorActionPreference='Stop' does NOT promote a native executable's non-zero
# exit into a terminating error (that needs $PSNativeCommandUseErrorActionPreference,
# PS 7.3+, which is not set here). Unchecked, a failed git config write — e.g. a
# read-only config file — would fall through to the success message below and
# exit 0 having installed nothing, so it is checked explicitly.
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("install-hooks: 'git config core.hooksPath' failed with exit $LASTEXITCODE")
    exit 1
}

Write-Host "install-hooks: core.hooksPath -> $targetPath"

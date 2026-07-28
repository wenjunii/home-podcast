[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [double]$MaxCredits
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$jobsPath = Join-Path $projectRoot "work\sfx\2013-12.01-scene-jobs.jsonl"
$secretPath = Join-Path (
    [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
) "RecoveredHomes\secrets\elevenlabs.dpapi"

$temporaryCredential = $false
$secretPointer = [IntPtr]::Zero
try {
    Push-Location $projectRoot
    try {
        Write-Host "Dry run: checking the resumable cache and paid-call ceiling."
        & python -m home_podcast generate-sfx --jobs $jobsPath
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }

    if (-not (Test-Path Env:ELEVENLABS_API_KEY)) {
        if (-not (Test-Path -LiteralPath $secretPath)) {
            throw (
                "No ElevenLabs credential is available. Run " +
                ".\scripts\save_elevenlabs_key.ps1 once."
            )
        }
        $encrypted = [System.IO.File]::ReadAllText($secretPath)
        $secureKey = ConvertTo-SecureString $encrypted
        $secretPointer = (
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        )
        $env:ELEVENLABS_API_KEY = (
            [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
        )
        $temporaryCredential = $true
    }

    Push-Location $projectRoot
    try {
        & python -m home_podcast generate-sfx `
            --jobs $jobsPath `
            --execute `
            --max-credits $MaxCredits
        $processExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    if ($temporaryCredential) {
        Remove-Item Env:ELEVENLABS_API_KEY -ErrorAction SilentlyContinue
    }
    if ($secretPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
    }
    Remove-Variable encrypted, secureKey -ErrorAction SilentlyContinue
}

exit $processExitCode

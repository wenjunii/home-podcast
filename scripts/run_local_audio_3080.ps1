param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "Doctor",
        "DoctorQwen",
        "DoctorAmbient",
        "PrepareAudition",
        "AuditionDryRun",
        "RunAudition",
        "PlanSpeech",
        "PrepareSpeech",
        "SpeechDryRun",
        "RunSpeech",
        "AuditSpeech",
        "CheckSpeech",
        "AssembleSpeech",
        "VerifySpeech",
        "ApproveSpeech",
        "PrepareAmbient",
        "AmbientDryRun",
        "RunAmbient",
        "AssembleSoundscape",
        "PrepareAmbientBatch",
        "AmbientBatchDryRun",
        "RunAmbientBatch",
        "CheckAmbientBatch",
        "AuditAmbientBatch",
        "PackageAmbientBatch",
        "VerifyAmbientBatch"
    )]
    [string]$Stage,
    [int]$MaxCalls = 0,
    [int]$NarrationLimit = 0,
    [string]$Profile = "3080_offline_production",
    [string]$Brief = "",
    [string]$ProductionIndex = "",
    [string]$Reviewer = "",
    [string]$ApprovalNote = "",
    [switch]$AllowModelDownload,
    [switch]$AllowConservativeEditions,
    [string]$CorePython = "py",
    [string]$QwenPython = ".venv-qwen\Scripts\python.exe",
    [string]$StableAudioPython = ".venv-stable-audio\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectConfig = Join-Path $ProjectRoot "storytelling.real-december.json"
$WorkRoot = Join-Path $ProjectRoot "work\storytelling-real-december\local-audio"
$AuditionPlan = Join-Path $WorkRoot "voice-audition-plan.json"
$SpeechJobs = Join-Path $WorkRoot "production-speech-jobs.jsonl"
$AmbientJobs = Join-Path $WorkRoot "ambient-jobs.jsonl"

function Invoke-ProjectPython {
    param([string]$PythonCommand, [string[]]$Arguments)
    Push-Location $ProjectRoot
    try {
        if ($PythonCommand -eq "py") {
            & py -3.10 -m home_podcast --config $ProjectConfig @Arguments
        }
        else {
            if (-not (Test-Path -LiteralPath $PythonCommand -PathType Leaf)) {
                throw "Python runtime not found: $PythonCommand"
            }
            & $PythonCommand -m home_podcast --config $ProjectConfig @Arguments
        }
        if ($LASTEXITCODE -ne 0) {
            throw "home-podcast exited with code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Assert-OfflineGpuPhase {
    $touchDesigner = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match "TouchDesigner" }
    if ($touchDesigner) {
        throw "Close TouchDesigner and stop StreamDiffusionTD before local audio generation."
    }
    if ($MaxCalls -le 0) {
        throw "Executed generation requires -MaxCalls set to the dry-run pending-call ceiling."
    }
}

function Add-LimitArgument {
    param([System.Collections.Generic.List[string]]$Arguments)
    if ($NarrationLimit -gt 0) {
        $Arguments.Add("--narration-limit")
        $Arguments.Add([string]$NarrationLimit)
    }
}

$AmbientBatchStages = @{
    PrepareAmbientBatch = "prepare"; AmbientBatchDryRun = "dry-run"
    RunAmbientBatch = "render"; CheckAmbientBatch = "quality"
    AuditAmbientBatch = "audit"; PackageAmbientBatch = "package"; VerifyAmbientBatch = "verify"
}
if ($AmbientBatchStages.ContainsKey($Stage)) {
    if (-not $Brief) { throw "$Stage requires -Brief with reviewed sound choices and speech approval." }
    if ($AllowModelDownload) { throw "Ambient batches use the already installed pinned runtime; downloads are disabled." }
    $arguments = [System.Collections.Generic.List[string]]@("ambient-batch", $AmbientBatchStages[$Stage], "--brief", $Brief)
    if ($Stage -eq "RunAmbientBatch") {
        Assert-OfflineGpuPhase
        $arguments.Add("--execute"); $arguments.Add("--max-calls"); $arguments.Add([string]$MaxCalls)
    }
    $pythonCommand = if ($Stage -in @("PackageAmbientBatch", "VerifyAmbientBatch", "AuditAmbientBatch")) { $QwenPython } else { $CorePython }
    Invoke-ProjectPython -PythonCommand $pythonCommand -Arguments $arguments.ToArray()
    exit
}

$WholeStoryStages = @{
    PlanSpeech = "queue"; PrepareSpeech = "prepare"; SpeechDryRun = "render"
    RunSpeech = "render"; AuditSpeech = "audit"; CheckSpeech = "quality"
    AssembleSpeech = "package"; VerifySpeech = "verify"; ApproveSpeech = "approve"
}
if ($WholeStoryStages.ContainsKey($Stage) -and $Profile -ne "3080_legacy_voice_clone") {
    if ($AllowModelDownload) {
        throw "Whole-story production uses the already cached pinned model; automatic downloads are disabled."
    }
    $arguments = [System.Collections.Generic.List[string]]@(
        "story-audio", $WholeStoryStages[$Stage], "--profile", $Profile
    )
    if ($Stage -eq "PlanSpeech") {
        if (-not $ProductionIndex) { throw "PlanSpeech requires -ProductionIndex for the reviewed collection." }
        $arguments.Add("--production-index"); $arguments.Add($ProductionIndex)
        if ($NarrationLimit -gt 0) { $arguments.Add("--limit"); $arguments.Add([string]$NarrationLimit) }
    }
    else {
        if (-not $Brief) { throw "$Stage requires -Brief with reviewed per-story casting and delivery." }
        $arguments.Add("--brief"); $arguments.Add($Brief)
    }
    if ($Stage -eq "RunSpeech") {
        Assert-OfflineGpuPhase
        $arguments.Add("--execute"); $arguments.Add("--max-calls"); $arguments.Add([string]$MaxCalls)
    }
    if ($Stage -eq "ApproveSpeech") {
        if (-not $Reviewer -or -not $ApprovalNote) { throw "ApproveSpeech requires -Reviewer and -ApprovalNote from the human decision." }
        $arguments.Add("--reviewer"); $arguments.Add($Reviewer)
        $arguments.Add("--approval-note"); $arguments.Add($ApprovalNote)
    }
    $runtime = if ($Stage -in @("RunSpeech", "AuditSpeech", "CheckSpeech", "AssembleSpeech")) { $QwenPython } else { $CorePython }
    Invoke-ProjectPython $runtime $arguments
    return
}
if ($Stage -in @("PlanSpeech", "AuditSpeech", "CheckSpeech", "VerifySpeech", "ApproveSpeech")) {
    throw "$Stage is available only for whole-story production, not legacy section cloning."
}

switch ($Stage) {
    "Doctor" {
        Invoke-ProjectPython $CorePython @("local-audio-doctor", "--profile", $Profile)
    }
    "DoctorQwen" {
        Invoke-ProjectPython $QwenPython @(
            "local-audio-doctor", "--profile", $Profile, "--component", "qwen"
        )
    }
    "DoctorAmbient" {
        Invoke-ProjectPython $StableAudioPython @(
            "local-audio-doctor", "--profile", $Profile, "--component", "ambient"
        )
    }
    "PrepareAudition" {
        $arguments = [System.Collections.Generic.List[string]]@(
            "prepare-local-voice-audition", "--profile", $Profile
        )
        if ($NarrationLimit -gt 0) {
            $arguments.Add("--voice-limit")
            $arguments.Add([string]$NarrationLimit)
        }
        Invoke-ProjectPython $CorePython $arguments
    }
    "AuditionDryRun" {
        Invoke-ProjectPython $CorePython @("generate-local-voice-audition", "--plan", $AuditionPlan)
    }
    "RunAudition" {
        Assert-OfflineGpuPhase
        $arguments = [System.Collections.Generic.List[string]]@(
            "generate-local-voice-audition", "--plan", $AuditionPlan,
            "--execute", "--max-calls", [string]$MaxCalls
        )
        if ($AllowModelDownload) { $arguments.Add("--allow-model-download") }
        Invoke-ProjectPython $QwenPython $arguments
    }
    "PrepareSpeech" {
        $arguments = [System.Collections.Generic.List[string]]@(
            "prepare-local-speech", "--profile", $Profile
        )
        Add-LimitArgument $arguments
        if ($AllowConservativeEditions) {
            $arguments.Add("--allow-conservative-editions")
        }
        Invoke-ProjectPython $CorePython $arguments
    }
    "SpeechDryRun" {
        Invoke-ProjectPython $CorePython @(
            "generate-local-speech", "--jobs", $SpeechJobs, "--profile", $Profile
        )
    }
    "RunSpeech" {
        Assert-OfflineGpuPhase
        $arguments = [System.Collections.Generic.List[string]]@(
            "generate-local-speech", "--jobs", $SpeechJobs,
            "--profile", $Profile, "--execute", "--max-calls", [string]$MaxCalls
        )
        if ($AllowModelDownload) { $arguments.Add("--allow-model-download") }
        Invoke-ProjectPython $QwenPython $arguments
    }
    "AssembleSpeech" {
        $arguments = [System.Collections.Generic.List[string]]@(
            "assemble-local-speech-collection", "--jobs", $SpeechJobs
        )
        Add-LimitArgument $arguments
        Invoke-ProjectPython $CorePython $arguments
    }
    "PrepareAmbient" {
        $arguments = [System.Collections.Generic.List[string]]@(
            "prepare-local-ambient-collection", "--profile", $Profile
        )
        Add-LimitArgument $arguments
        Invoke-ProjectPython $CorePython $arguments
    }
    "AmbientDryRun" {
        Invoke-ProjectPython $CorePython @(
            "generate-local-ambient", "--jobs", $AmbientJobs, "--profile", $Profile
        )
    }
    "RunAmbient" {
        Assert-OfflineGpuPhase
        $arguments = [System.Collections.Generic.List[string]]@(
            "generate-local-ambient", "--jobs", $AmbientJobs,
            "--profile", $Profile, "--execute", "--max-calls", [string]$MaxCalls
        )
        if ($AllowModelDownload) { $arguments.Add("--allow-model-download") }
        Invoke-ProjectPython $StableAudioPython $arguments
    }
    "AssembleSoundscape" {
        $arguments = [System.Collections.Generic.List[string]]@(
            "assemble-local-soundscape-collection"
        )
        Add-LimitArgument $arguments
        Invoke-ProjectPython $CorePython $arguments
    }
}

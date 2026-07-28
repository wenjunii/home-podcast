[CmdletBinding()]
param()

$secretRoot = Join-Path (
    [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
) "RecoveredHomes\secrets"
$secretPath = Join-Path $secretRoot "elevenlabs.dpapi"
New-Item -ItemType Directory -Path $secretRoot -Force | Out-Null

$secureKey = Read-Host "ElevenLabs API key" -AsSecureString
if ($secureKey.Length -eq 0) {
    throw "No API key was entered."
}

# ConvertFrom-SecureString uses Windows DPAPI when no explicit encryption key
# is supplied. Only this Windows user on this PC can decrypt the stored value.
$encrypted = ConvertFrom-SecureString -SecureString $secureKey
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($secretPath, $encrypted, $utf8NoBom)

Remove-Variable secureKey, encrypted
Write-Host "Saved an encrypted ElevenLabs credential for this Windows user."
Write-Host "It is outside the repository and cannot be moved to another PC."

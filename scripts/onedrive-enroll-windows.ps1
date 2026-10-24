$ErrorActionPreference = "Stop"

$Version = "1.75.2"
$ArchiveName = "rclone-v$Version-windows-amd64.zip"
$DownloadRoot = "https://downloads.rclone.org/v$Version"
$WorkRoot = Join-Path $env:TEMP "gm-studio-rclone-$Version"
$ArchivePath = Join-Path $WorkRoot $ArchiveName
$ChecksumsPath = Join-Path $WorkRoot "SHA256SUMS"
$ExtractPath = Join-Path $WorkRoot "extracted"
$OutputPath = Join-Path (Get-Location) "gm-studio-rclone.conf"

New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
Invoke-WebRequest "$DownloadRoot/$ArchiveName" -OutFile $ArchivePath
Invoke-WebRequest "$DownloadRoot/SHA256SUMS" -OutFile $ChecksumsPath

$ChecksumLine = Get-Content $ChecksumsPath | Where-Object { $_ -match "\s$([regex]::Escape($ArchiveName))$" }
if (-not $ChecksumLine) {
    throw "The official checksum list does not contain $ArchiveName."
}
$ExpectedHash = ($ChecksumLine -split "\s+")[0].ToUpperInvariant()
$ActualHash = (Get-FileHash -Algorithm SHA256 $ArchivePath).Hash.ToUpperInvariant()
if ($ExpectedHash -ne $ActualHash) {
    throw "The downloaded rclone archive failed SHA-256 verification."
}

if (Test-Path $ExtractPath) { Remove-Item -Recurse -Force $ExtractPath }
Expand-Archive -Path $ArchivePath -DestinationPath $ExtractPath
$Rclone = Get-ChildItem -Path $ExtractPath -Filter "rclone.exe" -Recurse | Select-Object -First 1
if (-not $Rclone) { throw "rclone.exe was not found after extraction." }

if (Test-Path $OutputPath) {
    $ExistingRemotes = & $Rclone.FullName --config $OutputPath listremotes
    if ($LASTEXITCODE -ne 0 -or $ExistingRemotes -notcontains "gm-onedrive:") {
        throw "The existing transfer file does not contain gm-onedrive. Move it aside and rerun."
    }
    Write-Host "Reconnecting the existing gm-onedrive drive. A Microsoft browser window will open."
    & $Rclone.FullName --config $OutputPath config reconnect gm-onedrive:
    if ($LASTEXITCODE -ne 0) { throw "OneDrive reconnection did not complete." }
} else {
    Write-Host "Interactive OneDrive setup is starting. Use these answers:"
    Write-Host "  n = new remote; name = gm-onedrive; storage = onedrive"
    Write-Host "  Leave client_id, client_secret, region, and tenant at their defaults."
    Write-Host "  Advanced config = n; browser authentication = y; connection type = 1."
    Write-Host "  IMPORTANT: at the drive list, choose the normal entry named OneDrive (personal or business)."
    Write-Host "  Do not choose Bundles, ODCMetadataArchive, Personal Vault, or another app/shortcut drive."
    Write-Host "  Confirm the drive, keep the remote, then enter q to leave configuration."
    & $Rclone.FullName --config $OutputPath config
    if ($LASTEXITCODE -ne 0) { throw "OneDrive authorization did not complete." }
}

$Remotes = & $Rclone.FullName --config $OutputPath listremotes
if ($LASTEXITCODE -ne 0 -or $Remotes -notcontains "gm-onedrive:") {
    throw "The gm-onedrive remote was not created."
}
& $Rclone.FullName --config $OutputPath mkdir "gm-onedrive:GM Studio Backups"
if ($LASTEXITCODE -ne 0) { throw "The new configuration could not create the GM Studio Backups folder." }
& $Rclone.FullName --config $OutputPath lsd "gm-onedrive:GM Studio Backups" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "The new configuration could not open the GM Studio Backups folder." }

Write-Host "Saved protected transfer file: $OutputPath"
Write-Host "Copy it to /tmp/gm-studio-rclone.conf on the Lenovo, then delete this Windows copy after the server import succeeds."
Write-Host "Do not open, email, or paste this file into chat; it contains a renewable OneDrive token."

# Export Telethon session for Railway (stop main.py first).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$session = Join-Path $root "session\group_automation.session"
if (-not (Test-Path $session)) {
    Write-Error "Missing $session. Run login_telethon.py first."
}
$procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'main\.py' }
if ($procs) {
    Write-Error "Stop main.py first (session file is locked). Found $($procs.Count) process(es)."
}
$raw = [IO.File]::ReadAllBytes($session)
$plainB64 = [Convert]::ToBase64String($raw)
$ms = New-Object IO.MemoryStream
$gz = New-Object IO.Compression.GZipStream($ms, [IO.Compression.CompressionMode]::Compress)
$gz.Write($raw, 0, $raw.Length)
$gz.Close()
$gzB64 = [Convert]::ToBase64String($ms.ToArray())

$gzOut = Join-Path $root "session_b64_gz.txt"
$gzB64 | Set-Content -NoNewline $gzOut
Write-Host "Railway variable: TELETHON_SESSION_BASE64_GZ"
Write-Host "Copy from: $gzOut"
Write-Host "Length: $($gzB64.Length) (Railway max 32768)"
if ($plainB64.Length -gt 32768) {
    Write-Host "Plain TELETHON_SESSION_BASE64 is $($plainB64.Length) chars; use _GZ only."
}

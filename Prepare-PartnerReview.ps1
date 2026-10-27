param(
    [string]$OutputPath = (Join-Path $PSScriptRoot 'AMIGA-Partner-Review.zip'),
    [switch]$ListOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$allowed = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($folder in @('backend','frontend/portal','frontend/scripts','frontend/tests','tests/backend','tests/fixtures','migrations','deploy/ec2')) {
    $folderPath = Join-Path $projectRoot $folder
    if (-not (Test-Path -LiteralPath $folderPath)) { continue }
    foreach ($file in Get-ChildItem -LiteralPath $folderPath -File -Recurse) {
        $relative = $file.FullName.Substring($projectRoot.Length + 1).Replace([char]92,[char]47)
        if ($relative -match '(^|/)(storage|__pycache__|node_modules|\.venv|\.git|dist)(/|$)') { continue }
        if ($file.Name -like '.env*' -and $file.Name -ne '.env.example') { continue }
        if ($file.Extension -in @('.db','.sqlite3','.log','.pyc','.zip','.wal','.shm')) { continue }
        if ($relative.StartsWith('backend/') -and $file.Extension -notin @('.py','.html') -and $relative -notin @('backend/requirements.txt','backend/.env.example','backend/source_manifest.json')) { continue }
        [void]$allowed.Add($relative)
    }
}
foreach ($name in @('.gitignore','.gitattributes','package.json','AGENTS.md','README.md','API_TERBARU.md','DEPLOY_EC2.md','PARTNER_REVIEW.md','Prepare-PartnerReview.ps1','AMIGA_KONTRAK_API.md','CARA_KERJA_AMIGA.md','INTEGRATION_STATUS.md','INTEGRASI_BACKEND_UTAMA.md','FRONTEND_STATUS.md','TIPOGRAFI_AMIGA.md','PERBAIKAN_EKSTRAKSI_INVOICE.md','Start-AMIGA.cmd','Start-Backend.cmd','Setup-Backend.cmd','Setup-Admin-AMIGA.cmd')) {
    if (Test-Path -LiteralPath (Join-Path $projectRoot $name)) { [void]$allowed.Add($name) }
}
if (Test-Path -LiteralPath (Join-Path $projectRoot 'CATATAN_DEMO_LOKAL.md')) { [void]$allowed.Add('CATATAN_DEMO_LOKAL.md') }
$files = @($allowed | Sort-Object)
if ($files -match '(^|/)(\.env|\.env.source|storage|\.runtime-temp)(/|$)') { throw 'Private files detected in review manifest.' }
if ($ListOnly) { $files; Write-Output ('Review files: ' + $files.Count); exit 0 }
$destination = [IO.Path]::GetFullPath($OutputPath)
if (-not $destination.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Choose an output ZIP inside the project folder.' }
if ([IO.Path]::GetExtension($destination) -ne '.zip') { throw 'Output must be a .zip file.' }
if (Test-Path -LiteralPath $destination) { throw 'ZIP already exists; choose another OutputPath. Existing files are preserved.' }
$parent = [IO.Path]::GetDirectoryName($destination)
[void][IO.Directory]::CreateDirectory($parent)
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($destination,[IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($relative in $files) {
        $sourcePath = [IO.Path]::GetFullPath((Join-Path $projectRoot $relative))
        if (-not $sourcePath.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Review path escaped project root.' }
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive,$sourcePath,$relative,[IO.Compression.CompressionLevel]::Optimal)
    }
} finally { $archive.Dispose() }
Write-Output ('Review ZIP created: ' + $destination)

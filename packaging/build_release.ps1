[CmdletBinding()]
param(
    [string]$Python = "C:\Users\ampar\AppData\Local\Programs\Python\Python314\python.exe",
    [string]$Spec = "GENERADOR DE HOJAS 4.1.spec",
    [string]$ReleaseRoot = "release",
    [string]$SigningCertificateThumbprint = "",
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [switch]$AllowUnsigned,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = Split-Path -Parent $PSScriptRoot
$pythonPath = [System.IO.Path]::GetFullPath($Python)
$specPath = [System.IO.Path]::GetFullPath((Join-Path $repo $Spec))
$updaterSpecPath = [System.IO.Path]::GetFullPath((Join-Path $repo "ACTUALIZADOR.spec"))
$lockPath = Join-Path $repo "requirements.lock"
$assetManifest = Join-Path $PSScriptRoot "assets.sha256"
$exeName = "GENERADOR DE HOJAS 4.1.exe"
$releaseName = "GENERADOR_DE_HOJAS_4.1.8"

function Assert-PathInsideRepo([string]$Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $repoPrefix = $repo.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the repository: $full"
    }
}

function Invoke-Checked([scriptblock]$Command, [string]$Description) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Python executable not found: $pythonPath"
}
if (-not (Test-Path -LiteralPath $specPath -PathType Leaf)) {
    throw "PyInstaller spec not found: $specPath"
}
if (-not (Test-Path -LiteralPath $updaterSpecPath -PathType Leaf)) {
    throw "Updater spec not found: $updaterSpecPath"
}

$pythonVersion = & $pythonPath -c "import platform; print(platform.python_version())"
if ($LASTEXITCODE -ne 0 -or $pythonVersion.Trim() -ne "3.14.3") {
    throw "The release requires Python 3.14.3; found '$pythonVersion'."
}

Write-Host "[1/6] Verifying locked Python environment..."
$verifyLock = @'
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re
import sys

errors = []
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line)
    if not match:
        errors.append(f"invalid lock entry: {line}")
        continue
    name, expected = match.groups()
    try:
        actual = version(name)
    except PackageNotFoundError:
        errors.append(f"missing: {name}=={expected}")
        continue
    if actual != expected:
        errors.append(f"version mismatch: {name} expected {expected}, found {actual}")
if errors:
    raise SystemExit("\n".join(errors))
'@
$verifyLock | & $pythonPath - $lockPath
if ($LASTEXITCODE -ne 0) {
    throw "The Python environment does not match requirements.lock."
}
Invoke-Checked { & $pythonPath -m pip check } "pip dependency check"

Write-Host "[2/6] Verifying distributable assets..."
foreach ($line in Get-Content -LiteralPath $assetManifest) {
    if ($line -notmatch "^([A-Fa-f0-9]{64})\s+\*(.+)$") {
        throw "Invalid asset manifest line: $line"
    }
    $expectedHash = $Matches[1].ToUpperInvariant()
    $relativePath = $Matches[2].Replace("/", [System.IO.Path]::DirectorySeparatorChar)
    $assetPath = Join-Path $repo $relativePath
    if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
        throw "Required asset not found: $relativePath"
    }
    $actualHash = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "Asset hash mismatch: $relativePath"
    }
}
$sumatraPath = Join-Path $repo "SumatraPDF.exe"
$sumatraVersion = (Get-Item -LiteralPath $sumatraPath).VersionInfo.FileVersion
if ($sumatraVersion -ne "3.6.1") {
    throw "Unexpected SumatraPDF version: $sumatraVersion"
}
$sumatraSignature = Get-AuthenticodeSignature -FilePath $sumatraPath
if ($sumatraSignature.Status -ne "Valid") {
    throw "The bundled SumatraPDF signature is not valid: $($sumatraSignature.StatusMessage)"
}

Write-Host "[3/6] Compiling sources and running tests..."
$sources = @(
    (Join-Path $repo "facturacion_tabs (1).py"),
    (Join-Path $repo "actualizador.py")
) + @(Get-ChildItem -LiteralPath (Join-Path $repo "emergency_core") -Filter "*.py" -File | ForEach-Object FullName)
Invoke-Checked { & $pythonPath -m py_compile @sources } "source compilation"
$testsPath = Join-Path $repo "tests"
if ((Test-Path -LiteralPath $testsPath -PathType Container) -and
    (Get-ChildItem -LiteralPath $testsPath -Filter "test_*.py" -File)) {
    Invoke-Checked { & $pythonPath -m pytest $testsPath } "test suite"
}

if ($ValidateOnly) {
    Write-Host "Validation completed. No executable was built."
    return
}

Write-Host "[4/6] Building clean application and external updater..."
$buildPath = Join-Path $repo "build"
$distPath = Join-Path $repo "dist"
foreach ($path in @($buildPath, $distPath)) {
    Assert-PathInsideRepo $path
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}
Push-Location $repo
try {
    Invoke-Checked { & $pythonPath -m PyInstaller --noconfirm --clean $updaterSpecPath } "updater PyInstaller build"
    Invoke-Checked { & $pythonPath -m PyInstaller --noconfirm --clean $specPath } "PyInstaller build"
}
finally {
    Pop-Location
}

$builtExe = Join-Path $distPath $exeName
$builtUpdater = Join-Path $distPath "ACTUALIZADOR.exe"
if (-not (Test-Path -LiteralPath $builtExe -PathType Leaf)) {
    throw "Expected executable was not produced: $builtExe"
}
if (-not (Test-Path -LiteralPath $builtUpdater -PathType Leaf)) {
    throw "Expected updater was not produced: $builtUpdater"
}
$selfTest = Start-Process -FilePath $builtExe -ArgumentList "--self-test" -Wait -PassThru -WindowStyle Hidden
if ($selfTest.ExitCode -ne 0) {
    throw "Packaged executable self-test failed with exit code $($selfTest.ExitCode)."
}

Write-Host "[5/6] Applying or validating Authenticode signature..."
if ($SigningCertificateThumbprint) {
    $thumbprint = $SigningCertificateThumbprint.Replace(" ", "").ToUpperInvariant()
    $certificate = Get-ChildItem -Path "Cert:\CurrentUser\My\$thumbprint" -ErrorAction Stop
    $signature = Set-AuthenticodeSignature `
        -FilePath $builtExe `
        -Certificate $certificate `
        -HashAlgorithm SHA256 `
        -TimestampServer $TimestampServer
    if ($signature.Status -ne "Valid") {
        throw "Authenticode signing failed: $($signature.StatusMessage)"
    }
    $updaterSignature = Set-AuthenticodeSignature `
        -FilePath $builtUpdater `
        -Certificate $certificate `
        -HashAlgorithm SHA256 `
        -TimestampServer $TimestampServer
    if ($updaterSignature.Status -ne "Valid") {
        throw "Updater Authenticode signing failed: $($updaterSignature.StatusMessage)"
    }
}
else {
    $signature = Get-AuthenticodeSignature -FilePath $builtExe
    $updaterSignature = Get-AuthenticodeSignature -FilePath $builtUpdater
    if (($signature.Status -ne "Valid" -or $updaterSignature.Status -ne "Valid") -and -not $AllowUnsigned) {
        throw "A release executable is unsigned. Supply -SigningCertificateThumbprint or explicitly use -AllowUnsigned."
    }
}

Write-Host "[6/6] Assembling PHI-free release package..."
$releaseRootPath = [System.IO.Path]::GetFullPath((Join-Path $repo $ReleaseRoot))
$stagingPath = Join-Path $releaseRootPath $releaseName
Assert-PathInsideRepo $releaseRootPath
Assert-PathInsideRepo $stagingPath
if (Test-Path -LiteralPath $stagingPath) {
    Remove-Item -LiteralPath $stagingPath -Recurse -Force
}
New-Item -ItemType Directory -Path $stagingPath -Force | Out-Null
Copy-Item -LiteralPath $builtExe -Destination (Join-Path $stagingPath $exeName)
Copy-Item -LiteralPath $builtUpdater -Destination (Join-Path $stagingPath "ACTUALIZADOR.exe")
Copy-Item -LiteralPath (Join-Path $repo "RELEASE_NOTES_4.1.md") -Destination $stagingPath
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "THIRD_PARTY_NOTICES.txt") -Destination $stagingPath
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "LICENSES") -Destination $stagingPath -Recurse

$hashLines = Get-ChildItem -LiteralPath $stagingPath -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($stagingPath.Length + 1).Replace("\", "/")
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        "$hash *$relative"
    }
$hashLines | Set-Content -LiteralPath (Join-Path $stagingPath "SHA256SUMS.txt") -Encoding ascii

$allowedFiles = @(
    $exeName,
    "ACTUALIZADOR.exe",
    "RELEASE_NOTES_4.1.md",
    "THIRD_PARTY_NOTICES.txt",
    "SHA256SUMS.txt"
)
$allowedLicenseFiles = @(
    "charset-normalizer-3.4.5.txt",
    "et_xmlfile-2.0.0-Python.txt",
    "et_xmlfile-2.0.0.txt",
    "openpyxl-3.1.5.txt",
    "Pillow-12.1.1.txt",
    "PyPDF2-3.0.1.txt",
    "Python-3.14.3.txt",
    "ReportLab-4.4.10.txt",
    "SumatraPDF-3.6.1-AGPLv3.txt",
    "SumatraPDF-3.6.1-BSD.txt",
    "ttkbootstrap-1.20.2.txt"
)
$unexpectedTopLevelFiles = Get-ChildItem -LiteralPath $stagingPath -File | Where-Object { $_.Name -notin $allowedFiles }
$unexpectedTopLevelDirs = Get-ChildItem -LiteralPath $stagingPath -Directory | Where-Object { $_.Name -ne "LICENSES" }
$unexpectedLicenseFiles = Get-ChildItem -LiteralPath (Join-Path $stagingPath "LICENSES") -File |
    Where-Object { $_.Name -notin $allowedLicenseFiles }
$unexpectedLicenseDirs = Get-ChildItem -LiteralPath (Join-Path $stagingPath "LICENSES") -Directory
$missingLicenseFiles = $allowedLicenseFiles | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $stagingPath "LICENSES\$_") -PathType Leaf)
}
$forbiddenData = Get-ChildItem -LiteralPath $stagingPath -Recurse -File | Where-Object {
    $_.Name -match "(?i)(pacientes\.db|turnos_config|app_settings|representantes|resumen_turno|debug_impresion)" -or
    $_.Extension -match "(?i)^\.(db|sqlite|sqlite3|xls|xlsx|csv|json|log)$"
}
if ($unexpectedTopLevelFiles -or $unexpectedTopLevelDirs -or $unexpectedLicenseFiles -or
    $unexpectedLicenseDirs -or $missingLicenseFiles -or $forbiddenData) {
    throw "Release allowlist validation failed; operational or unexpected files were detected."
}

$zipPath = Join-Path $releaseRootPath "$releaseName.zip"
Assert-PathInsideRepo $zipPath
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $stagingPath -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
"$zipHash *$(Split-Path -Leaf $zipPath)" | Set-Content -LiteralPath "$zipPath.sha256" -Encoding ascii

Write-Host "Release ready: $stagingPath"
Write-Host "Archive: $zipPath"

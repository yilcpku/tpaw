param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [switch]$Run
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$cudaRoot = Join-Path $repoRoot 'packages\simulator-cuda'
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
if ($outputRoot.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose an output directory outside the source checkout.'
}
$nvccPath = (Get-Command nvcc.exe -ErrorAction Stop).Source
$vswherePath = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsRoot = & $vswherePath -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsRoot) { throw 'Existing MSVC C++ tools required; this script installs nothing.' }
$vcvarsPath = Join-Path $vsRoot 'VC\Auxiliary\Build\vcvars64.bat'
$meson = Get-Content (Join-Path $cudaRoot 'meson.build') -Raw
$sourceList = [regex]::Matches($meson, "'([^']+\.cu)'") | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -ne 'src/main_test.cu' }
$sourceList = @($sourceList) + @('src/main_test.cu')
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$testExe = Join-Path $outputRoot 'simulator-cuda-test.exe'
$commandFile = Join-Path $outputRoot 'build-tests.cmd'
$flags = '-std=c++20 -rdc=true --extended-lambda -diag-suppress=445 -Xcompiler=/Zc:preprocessor,/bigobj -DNOMINMAX --pre-include=Windows.h -gencode=arch=compute_89,code=sm_89 -I. '
$headerHashes = (Get-ChildItem -LiteralPath $cudaRoot -Filter '*.h' -Recurse | Sort-Object FullName | Get-FileHash -Algorithm SHA256).Hash -join ''
$toolchain = (& $nvccPath --version) -join ''
$sharedFingerprint = $headerHashes + $toolchain + $flags + $vsRoot
$commands = @('@echo off', ('call "' + $vcvarsPath + '"'), 'if errorlevel 1 exit /b 1')
$objects = @()
for ($i = 0; $i -lt $sourceList.Count; $i++) {
    $source = $sourceList[$i]
    $object = Join-Path $outputRoot ('source-' + $i + '.obj')
    $stamp = $object + '.sha256'
    $fingerprintBytes = [System.Text.Encoding]::UTF8.GetBytes($sharedFingerprint + (Get-FileHash (Join-Path $cudaRoot $source) -Algorithm SHA256).Hash)
    $fingerprint = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($fingerprintBytes))
    $objects += ('"' + $object + '"')
    if ((Test-Path -LiteralPath $object) -and (Test-Path -LiteralPath $stamp) -and ((Get-Content -LiteralPath $stamp -Raw).Trim() -eq $fingerprint)) { continue }
    $commands += ('"' + $nvccPath + '" ' + $flags + ' -dc "' + $source + '" -o "' + $object + '"')
    $commands += 'if errorlevel 1 exit /b 1'
    $commands += ('echo ' + $fingerprint + '>"' + $stamp + '"')
}
$commands += ('"' + $nvccPath + '" -rdc=true -gencode=arch=compute_89,code=sm_89 ' + ($objects -join ' ') + ' -lcublas -o "' + $testExe + '"')
$commands | Set-Content -LiteralPath $commandFile -Encoding ascii
Push-Location $cudaRoot
try {
    & $env:ComSpec /d /c $commandFile
    if ($LASTEXITCODE -ne 0) { throw 'CUDA test build failed. No financial scenario was run.' }
    if ($Run) {
        # Upstream benchmarks can allocate huge arrays; exclude every benchmark.
        & $testExe '--test-case-exclude=*bench*' '--no-skip'
        if ($LASTEXITCODE -ne 0) { throw 'CUDA correctness tests failed.' }
    }
} finally {
    Pop-Location
}

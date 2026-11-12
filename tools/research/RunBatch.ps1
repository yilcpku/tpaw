param(
  [Parameter(Mandatory)][string]$CasesDirectory,
  [Parameter(Mandatory)][string]$Presets,
  [Parameter(Mandatory)][string]$OutputDirectory,
  [Parameter(Mandatory)][string]$ReplayExecutable,
  [Parameter(Mandatory)][string]$RuntimeModules,
  [Parameter(Mandatory)][string]$CommonModules
)
$ErrorActionPreference='Stop'
# Toolchain/DLL paths must already be configured process-locally by the caller.
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new private output directory' }
$caseFiles=@(Get-ChildItem -LiteralPath $CasesDirectory -Filter '*.json' | Where-Object Name -ne 'manifest.json')
if ($caseFiles.Count -lt 1 -or $caseFiles.Count -gt 36) { throw 'Require 1..36 prepared cases' }
foreach ($file in $caseFiles) {
  $case=Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
  if (!$case.plan -or !$case.run -or !$case.id) { throw 'Unexpected case schema' }
}
$dest=& node (Join-Path $PSScriptRoot 'PrivateDestination.cjs') $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Private output path validation failed' }
New-Item -ItemType Directory -Path $dest | Out-Null
$oldModules=$env:NODE_PATH
$oldOptions=$env:TS_NODE_COMPILER_OPTIONS
try {
  $env:NODE_PATH="$RuntimeModules;$CommonModules"
  $env:TS_NODE_COMPILER_OPTIONS='{"module":"CommonJS","moduleResolution":"node","target":"es2020"}'
  $register=Join-Path $CommonModules 'ts-node/register/transpile-only'
  foreach ($file in $caseFiles) {
    $stem=$file.BaseName
    $casePath=Join-Path $dest "$stem-case.json"
    Copy-Item -LiteralPath $file.FullName -Destination $casePath
    $req=Join-Path $dest "$stem-request.pb"
    $res=Join-Path $dest "$stem-result.pb"
    & node -r $register (Join-Path $PSScriptRoot 'EncodeReplay.ts') $casePath $req
    if ($LASTEXITCODE) { throw 'Encoding failed' }
    & $ReplayExecutable --request $req --presets $Presets --output $res
    if ($LASTEXITCODE) { throw 'Offline engine failed' }
    & node -r $register (Join-Path $PSScriptRoot 'InspectReplay.ts') $req $res (Join-Path $dest "$stem-decoded.json")
    if ($LASTEXITCODE) { throw 'Inspection failed' }
  }
  & node -r $register (Join-Path $PSScriptRoot 'SummarizeReplay.ts') $dest (Join-Path $dest 'comparison')
  if ($LASTEXITCODE) { throw 'Summary failed' }
  @{status='completed';cases=$caseFiles.Count;presets_sha256=(Get-FileHash -LiteralPath $Presets -Algorithm SHA256).Hash;
    executable_sha256=(Get-FileHash -LiteralPath $ReplayExecutable -Algorithm SHA256).Hash} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dest 'batch-manifest.json')
} finally {
  $env:NODE_PATH=$oldModules
  $env:TS_NODE_COMPILER_OPTIONS=$oldOptions
}

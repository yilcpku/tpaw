param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$cudaRoot=Join-Path $repoRoot 'packages\simulator-cuda'
$outputRoot=[IO.Path]::GetFullPath($OutputDirectory)
if($outputRoot.StartsWith($repoRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Build outside the source checkout.'}
$nvcc=(Get-Command nvcc.exe).Source
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsRoot=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$vcvars=Join-Path $vsRoot 'VC\Auxiliary\Build\vcvars64.bat'
$sources=@([regex]::Matches((Get-Content (Join-Path $cudaRoot 'meson.build') -Raw),"'([^']+\.cu)'") | ForEach-Object {$_.Groups[1].Value} | Where-Object {$_ -ne 'src/main_test.cu'})
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$flags='-O2 -DDOCTEST_CONFIG_DISABLE -std=c++20 -rdc=true --extended-lambda -diag-suppress=445 -Xcompiler=/Zc:preprocessor,/bigobj -DNOMINMAX --pre-include=Windows.h -gencode=arch=compute_89,code=sm_89 -I. '
$headerHashes=(Get-ChildItem -LiteralPath $cudaRoot -Filter '*.h' -Recurse | Sort-Object FullName | Get-FileHash -Algorithm SHA256).Hash -join ''
$shared=$headerHashes + ((& $nvcc --version) -join '') + $flags + $vsRoot
$commands=@('@echo off',('call "'+$vcvars+'"'),'if errorlevel 1 exit /b 1')
$objects=@()
for($i=0;$i -lt $sources.Count;$i++){
    $obj=Join-Path $outputRoot ('source-'+$i+'.obj')
    $stamp=$obj+'.sha256'
    $bytes=[Text.Encoding]::UTF8.GetBytes($shared+(Get-FileHash (Join-Path $cudaRoot $sources[$i]) -Algorithm SHA256).Hash)
    $hash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))
    $objects+=('"'+$obj+'"')
    if((Test-Path -LiteralPath $obj) -and (Test-Path -LiteralPath $stamp) -and ((Get-Content -LiteralPath $stamp -Raw).Trim() -eq $hash)){continue}
    $commands+=('"'+$nvcc+'" '+$flags+' -dc "'+$sources[$i]+'" -o "'+$obj+'"')
    $commands+='if errorlevel 1 exit /b 1'
    $commands+=('echo '+$hash+'>"'+$stamp+'"')
}
$dll=Join-Path $outputRoot 'simulator-cuda.dll'
$lib=Join-Path $outputRoot 'simulator-cuda.lib'
$commands+=('"'+$nvcc+'" -shared -rdc=true -gencode=arch=compute_89,code=sm_89 '+($objects -join ' ')+' -lcublas -Xlinker /EXPORT:cuda_simulate,/EXPORT:cuda_research_horizon,/EXPORT:cuda_research_conditional,/EXPORT:cuda_research_conditional_notice,/EXPORT:cuda_get_empirical_annual_non_log_mean,/IMPLIB:"'+$lib+'" -o "'+$dll+'"')
$commandFile=Join-Path $outputRoot 'build-library.cmd'
$commands | Set-Content -LiteralPath $commandFile -Encoding ascii
Push-Location $cudaRoot
try { & $env:ComSpec /d /c $commandFile; if($LASTEXITCODE -ne 0){throw 'CUDA DLL build failed.'} } finally {Pop-Location}

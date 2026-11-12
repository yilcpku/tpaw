param([Parameter(Mandatory=$true)][string]$OutputDirectory, [int]$Year=2025)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$destination=[IO.Path]::GetFullPath($OutputDirectory)
if ($destination.StartsWith($repoRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Save snapshots outside Git.' }
$rawPath=Join-Path $destination ('hk-life-table-' + $Year + '-api.json')
$normalizedPath=Join-Path $destination ('hk-male-period-' + $Year + '.json')
if ((Test-Path -LiteralPath $rawPath) -or (Test-Path -LiteralPath $normalizedPath)) { throw 'Snapshot already exists; use a fresh destination.' }
$query=@{id='115-01021';lang='en';period=@{start=[string]$Year;end=[string]$Year};
    cv=@{SEX=@('M');AGE=@('zero') + @(1..99 | ForEach-Object {[string]$_}) + @('100_and_over')};
    sv=@{QX=@('Raw_8dp_idx_n');LX=@('Raw_idx_n');EX=@('Raw_2dp_idx_n');TX=@('Raw_idx_n');LLX=@('Raw_idx_n')}} | ConvertTo-Json -Depth 6 -Compress
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Invoke-WebRequest -Uri 'https://www.censtatd.gov.hk/api/post.php' -Method Post -Body @{query=$query} -OutFile $rawPath -TimeoutSec 45
$response=Get-Content -LiteralPath $rawPath -Raw | ConvertFrom-Json
if ($response.header.status.code -ne 0 -or $response.dataSet.Count -ne 505) { throw 'Official response incomplete; retain raw data for inspection.' }
$rows=@{}
$fields=@{QX='qx';LX='lx';EX='ex';TX='tx';LLX='person_years'}
foreach($record in $response.dataSet) {
    $age=if($record.AGE -eq 'zero'){0}elseif($record.AGE -eq '100_and_over'){100}else{[int]$record.AGE}
    if(-not $rows.ContainsKey($age)){$rows[$age]=@{age=$age}}
    if($record.SEX -ne 'M' -or [int]$record.period -ne $Year){throw 'Unexpected population/year.'}
    $rows[$age][$fields[$record.sv]]=$record.figure
}
if($rows.Count -ne 101 -or @($rows.Values | Where-Object {$_.Count -ne 6}).Count){throw 'Age/variable coverage incomplete.'}
$source=@{agency='Hong Kong Census and Statistics Department';table='115-01021';data_year=$Year;
    url='https://www.censtatd.gov.hk/en/web_table.html?id=115-01021';mortality_basis='period';sex='male';open_age_interval=100;
    api_raw_sha256=(Get-FileHash -LiteralPath $rawPath -Algorithm SHA256).Hash.ToLowerInvariant();
    retrieved_at_utc=[DateTime]::UtcNow.ToString('o');method_note='qx=1 at >=100 refers to the open interval, not death before 101'}
if($Year -eq 2025){$source.release_date='2026-10-02'}
@{source=$source;rows=@($rows.GetEnumerator() | Sort-Object Key | ForEach-Object {$_.Value})} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $normalizedPath -Encoding utf8
Write-Output 'Official male period life-table snapshot saved; no personal data sent.'

param($jsonl)
while ($true) {
  if ((Test-Path $jsonl) -and ((Get-Content $jsonl | Measure-Object -Line).Lines -ge 75)) { break }
  Start-Sleep 5
}
Start-Sleep 20
$p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'g13_is_busca\.py' -and $_.CommandLine -match 'roda.py' }
$ids = @($p | % ProcessId)
$kids = Get-CimInstance Win32_Process | Where-Object { $ids -contains $_.ParentProcessId } | % ProcessId
($ids + $kids) | % { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
"vigia: matou $($ids.Count + $kids.Count)"

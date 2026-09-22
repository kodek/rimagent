# Windows counterpart of restart-game.sh: kill RimWorld, relaunch through Steam so Workshop mods load.
$ErrorActionPreference = 'SilentlyContinue'
$procs = Get-Process -Name 'RimWorldWin64'
if ($procs) {
    Write-Host "killing RimWorld pid(s): $($procs.Id -join ' ')"
    $procs | Stop-Process
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-Process -Name 'RimWorldWin64')) { break }
    }
    Get-Process -Name 'RimWorldWin64' | Stop-Process -Force
    Start-Sleep -Seconds 1
}
Start-Process 'steam://rungameid/294100'
Write-Host 'relaunched via Steam'

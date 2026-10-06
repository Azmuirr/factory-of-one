# Installs the real Windows Scheduled Tasks that run Chief on the cadence docs/install.md describes, instead of
# leaving that cadence as copy-paste instructions. Each task's own ACTION calls python -m factory.chief directly
# (not this script again), so Task Scheduler is the only thing driving it once installed.
#
# Usage: powershell -File scripts/install_schedule.ps1 [-Scenario s01-calendar-gate] [-AsOfDate 2026-03-02] [-Uninstall]
#
# What each task does and how it connects to the rest of the factory:
# - Morning, midday, evening (Mon-Fri): python -m factory.chief --mode <mode>. Each run posts its urgent note to
#   the PM's own channel (outbox.jsonl) under the away-decision-rights limit (factory/loop/__main__.py: notify),
#   and reads company/tallybird/lessons/chief.yaml for every correction taught so far (factory/chief/correct.py).
#   A real, later scheduled run sees corrections an earlier one (scheduled or manual) produced: that is the loop
#   connection a cron entry by itself does not prove.
# - Weekly (Fri): python -m factory.chief --mode weekly. In a live (non-sandbox) install, this is naturally
#   followed by `python -m factory.retro run runs/loop/<run> runs/autopilot/<run>` (docs/install.md), which reads
#   the week's real runs. The sandbox demo here proves the four scheduled triggers themselves are real; Retro's
#   own real-vendor-adapter equivalent is future work, not claimed here.
#
# This sandbox demo reuses one scenario day (2026-03-02, the scenario's only populated day) for every trigger's
# --as-of, since the sandbox's world.db is a single fixed snapshot, not a live calendar/mailbox that actually
# advances day to day the way a real install's would. What's being proven is that Task Scheduler itself fires
# the command on schedule, not that the sandbox simulates five different calendar days.

param(
    [string]$Scenario = "s01-calendar-gate",
    [string]$AsOfDate = "2026-03-02",
    [switch]$Uninstall
)

$Root = (Resolve-Path "$PSScriptRoot\..").Path
$Wrapper = Join-Path $Root "scripts\run_chief.bat"
$LogDir = Join-Path $Root "runs\chief\scheduled"
$Tasks = @(
    @{ Name = "FactoryChiefMorning"; Mode = "morning"; Time = "07:30"; Days = "MON,TUE,WED,THU,FRI" },
    @{ Name = "FactoryChiefMidday";  Mode = "midday";  Time = "12:00"; Days = "MON,TUE,WED,THU,FRI" },
    @{ Name = "FactoryChiefEvening"; Mode = "evening"; Time = "18:00"; Days = "MON,TUE,WED,THU,FRI" },
    @{ Name = "FactoryChiefWeekly";  Mode = "weekly";  Time = "16:00"; Days = "FRI" }
)

if ($Uninstall) {
    foreach ($t in $Tasks) {
        schtasks /Delete /TN $t.Name /F 2>$null | Out-Null
        Write-Host "Removed $($t.Name)"
    }
    exit 0
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

foreach ($t in $Tasks) {
    $asOf = "$AsOfDate`T$($t.Time):00Z"
    $cmd = "`"$Wrapper`" $($t.Mode) $Scenario $asOf"
    & schtasks /Create /SC WEEKLY /D $t.Days /ST $t.Time /TN $t.Name /TR $cmd /F
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED to install $($t.Name) (exit $LASTEXITCODE)"
    } else {
        Write-Host "Installed $($t.Name): $($t.Mode) on $($t.Days) at $($t.Time), --as-of $asOf"
    }
}

Write-Host "`nVerify: schtasks /Query /TN FactoryChiefMorning /V /FO LIST"
Write-Host "Fire now: schtasks /Run /TN FactoryChiefMorning"
Write-Host "Remove all: powershell -File scripts/install_schedule.ps1 -Uninstall"

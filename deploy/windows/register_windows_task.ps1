# Windows Task Scheduler 등록 스크립트 (주간 + 월간)
# PowerShell에서 실행:
#   powershell -ExecutionPolicy Bypass -File .\register_windows_task.ps1
#
# 배포 경로 예시 (EXE + config.json 동일 폴더):
#   C:\LogReport

param(
    [string]$ExePath = "C:\LogReport\win_analyzer.exe",
    [string]$WeeklyTaskName = "LogReportWeekly",
    [string]$MonthlyTaskName = "LogReportMonthly",
    [string]$DayOfWeek = "Monday",
    [string]$Time = "08:00"
)

$ErrorActionPreference = "Stop"
$ExePath = (Resolve-Path $ExePath -ErrorAction Stop).Path
$WorkDir = Split-Path $ExePath -Parent

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

function Register-LogReportTask {
    param(
        [string]$Name,
        [string]$Argument,
        [object]$Trigger,
        [string]$Description
    )
    $action = New-ScheduledTaskAction `
        -Execute $ExePath `
        -Argument $Argument `
        -WorkingDirectory $WorkDir

    Register-ScheduledTask `
        -TaskName $Name `
        -Action $action `
        -Trigger $Trigger `
        -Settings $settings `
        -Description $Description `
        -Force
}

function Register-MonthlyTaskSchtasks {
    param([string]$Name, [string]$Argument)
    $st = $Time
    if ($st -notmatch ":") { $st = "08:00" }

    # 경로에 쉼표 있으면 schtasks /TR 파싱 깨짐 → bat 파일 사용
    $batPath = Join-Path $WorkDir "run_monthly.bat"
    if (-not (Test-Path $batPath)) {
        @"
@echo off
pushd "%~dp0"
win_analyzer.exe --auto monthly
"@ | Set-Content -Path $batPath -Encoding ASCII
        Write-Host "[알림] run_monthly.bat 생성됨: $batPath"
    }

    # /D 는 schtasks 월간 일자용 — TR 안에 cd /d 쓰면 충돌하므로 bat 직접 실행
    schtasks /Create /TN $Name /SC MONTHLY /D 1 /ST $st /TR $batPath /F | Out-Null
}

$weeklyOk = $false
$monthlyOk = $false

try {
    $weeklyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time
    Register-LogReportTask `
        -Name $WeeklyTaskName `
        -Argument "--auto weekly" `
        -Trigger $weeklyTrigger `
        -Description "주간 로그 HTML 리포트 + 메일 (직전 ISO 주)"
    $weeklyOk = $true
    Write-Host "[OK] $WeeklyTaskName 등록됨"
} catch {
    Write-Host "[실패] $WeeklyTaskName : $_" -ForegroundColor Red
}

try {
    $monthlyTrigger = New-ScheduledTaskTrigger -Monthly -DaysOfMonth 1 -At $Time -ErrorAction Stop
    Register-LogReportTask `
        -Name $MonthlyTaskName `
        -Argument "--auto monthly" `
        -Trigger $monthlyTrigger `
        -Description "월간 로그 HTML 리포트 + 메일 (직전 월)"
    $monthlyOk = $true
    Write-Host "[OK] $MonthlyTaskName 등록됨 (PowerShell 트리거)"
} catch {
    Write-Host "[알림] PowerShell 월간 트리거 미지원 → schtasks 로 재시도..."
    try {
        Register-MonthlyTaskSchtasks -Name $MonthlyTaskName -Argument "--auto monthly"
        $monthlyOk = $true
        Write-Host "[OK] $MonthlyTaskName 등록됨 (schtasks)"
    } catch {
        Write-Host "[실패] $MonthlyTaskName : $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "실행 파일: $ExePath"
Write-Host "작업 폴더: $WorkDir"
if ($weeklyOk) { Write-Host "  [$WeeklyTaskName] 매주 $DayOfWeek $Time  →  reports\weekly\" }
if ($monthlyOk) { Write-Host "  [$MonthlyTaskName] 매월 1일 $Time       →  reports\monthly\" }
Write-Host ""
if ($weeklyOk) { Write-Host "수동 실행: schtasks /Run /TN `"$WeeklyTaskName`"" }
if ($monthlyOk) { Write-Host "수동 실행: schtasks /Run /TN `"$MonthlyTaskName`"" }

if (-not $weeklyOk -and -not $monthlyOk) { exit 1 }

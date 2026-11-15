# PowerShell Script to register a daily Windows Task Scheduler task
$Action = New-ScheduledTaskAction -Execute "A:\ABP ananda\run_daily.bat"
$Trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "ABPNadiaPhotoMailer" -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily Instagram Photo Submission to ABP Nadia" -Force
Write-Host "Task 'ABPNadiaPhotoMailer' successfully scheduled for 9:00 AM daily!" -ForegroundColor Green

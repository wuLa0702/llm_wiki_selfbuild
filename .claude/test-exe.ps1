$exe = 'D:\gtiHub\llm_wiki_selfbuild\dist\LLM-Wiki.exe'
$err = 'C:\Users\Administrator\AppData\Local\Temp\wiki-err.txt'

Write-Host "Starting EXE..."
$p = Start-Process $exe -WindowStyle Hidden -PassThru -RedirectStandardError $err

Start-Sleep -Seconds 10

if ($p.HasExited) {
    Write-Host "PROCESS EXITED with code: $($p.ExitCode)"
    Write-Host "=== STDERR ==="
    if (Test-Path $err) {
        Get-Content $err
    } else {
        Write-Host "(no stderr file)"
    }
} else {
    Write-Host "PROCESS RUNNING (PID: $($p.Id))"
    # Check port
    $conn = Get-NetTCPConnection -LocalPort 8766 -ErrorAction SilentlyContinue
    if ($conn) {
        $conn | Format-Table State, OwningProcess, LocalAddress, LocalPort
        Write-Host "SUCCESS: App is listening on port 8766!"
        # Test response
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8766" -UseBasicParsing -TimeoutSec 5
            Write-Host "HTTP Response: $($resp.StatusCode)"
        } catch {
            Write-Host "HTTP check failed: $_"
        }
    } else {
        Write-Host "Port 8766 is NOT listening"
    }
}

# Check app log
$appDataLog = "$env:APPDATA\LLM-Wiki\logs\app.log"
if (Test-Path $appDataLog) {
    Write-Host "=== APP LOG ==="
    Get-Content $appDataLog
}

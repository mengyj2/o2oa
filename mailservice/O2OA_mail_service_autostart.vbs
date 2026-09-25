' O2OA mail verification-code service auto-start (runs hidden at logon)
' ASCII ONLY - WScript parses ANSI; do NOT save Chinese in this file.
' Launches mailservice\watchdog_mail_service.py:
'   - brings up the x_sms_assemble_control substitute on 0.0.0.0:8095
'   - health-check every 30s, auto-restart on failure (singleton lock inside)
' Logs: D:\O2OA\mailservice\watchdog.log  /  mailservice.log
' To disable autostart: delete this file.
Set sh = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
sh.CurrentDirectory = "D:\O2OA\mailservice"
' Kill stale watchdog + service from previous logon (by PID files) so that the
' singleton lock cannot make the new watchdog exit and leave the OLD one alive.
KillByPidFile "watchdog.pid"
KillByPidFile "mailservice.pid"
' wait for system ready before launching (Docker/other startup items may still be busy)
WScript.Sleep 15000
sh.Run """C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe"" ""D:\O2OA\mailservice\watchdog_mail_service.py""", 0, False

Sub KillByPidFile(name)
  Dim p, f, pid
  p = "D:\O2OA\mailservice\" & name
  If fs.FileExists(p) Then
    On Error Resume Next
    Set f = fs.OpenTextFile(p, 1)
    pid = Trim(f.ReadAll)
    f.Close
    If Err.Number = 0 And IsNumeric(pid) And pid <> "0" Then
      sh.Run "taskkill /PID " & pid & " /F /T", 0, True
    End If
    Err.Clear
    On Error Goto 0
    fs.DeleteFile p, True
  End If
End Sub

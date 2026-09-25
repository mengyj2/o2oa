' O2OA AI stack auto-start (runs hidden at logon)
' ASCII ONLY - WScript parses ANSI; do NOT save Chinese in this file.
' Launches watchdog_ai_stack.py:
'   - brings up embed(8089) + gateway(18790) + ocr(8091); chat via LM Studio 1234
'   - health-check every 30s, auto-restart on failure (singleton lock inside)
' Logs: D:\O2OA\gateway\watchdog.log / gateway.log / llama_*.log
' To disable autostart: delete this file.
Set sh = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
sh.CurrentDirectory = "D:\O2OA\gateway"
' Kill stale watchdog + components from previous logon (by PID files) so the
' singleton lock cannot make the new watchdog exit and leave the OLD one alive.
KillByPidFile "watchdog.pid"
KillByPidFile "gateway.pid"
KillByPidFile "ocr.pid"
KillByPidFile "embed.pid"
KillByPidFile "chat.pid"
KillByPidFile "rerank.pid"
' wait for system/GPU ready before launching
WScript.Sleep 20000
sh.Run """C:\Users\meng_\.workbuddy\binaries\python\envs\default\Scripts\python.exe"" ""D:\O2OA\gateway\watchdog_ai_stack.py""", 0, False

Sub KillByPidFile(name)
  Dim p, f, pid
  p = "D:\O2OA\gateway\" & name
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

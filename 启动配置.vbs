Option Explicit
Dim shell, fs, folder, scriptPath, pythonw, command, rc
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fs.BuildPath(folder, "configure.pyw")

If Not fs.FileExists(scriptPath) Then
    MsgBox "configure.pyw is missing. Extract the entire source ZIP first.", 48, "OpenASI Checkin"
    WScript.Quit 1
End If

pythonw = fs.BuildPath(folder, ".venv\Scripts\pythonw.exe")
If Not fs.FileExists(pythonw) Then pythonw = "pythonw.exe"
command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & scriptPath & Chr(34)
On Error Resume Next
rc = shell.Run(command, 0, False)
If Err.Number <> 0 Then
    Err.Clear
    command = "pyw.exe -3 " & Chr(34) & scriptPath & Chr(34)
    rc = shell.Run(command, 0, False)
    If Err.Number <> 0 Then
        MsgBox "Install Windows Python 3.10+ with Tcl/Tk and the Python launcher, then retry.", 48, "OpenASI Checkin"
        WScript.Quit 1
    End If
End If

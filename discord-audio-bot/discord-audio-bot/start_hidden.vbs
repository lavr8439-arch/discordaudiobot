Option Explicit

Dim shell, fso, folder, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder

command = "pythonw.exe """ & folder & "\audio_bot.py"""
On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then
    Err.Clear
    command = "pyw.exe -3 """ & folder & "\audio_bot.py"""
    shell.Run command, 0, False
End If
If Err.Number <> 0 Then
    MsgBox "Python was not found. Reinstall Python and enable Add Python to PATH.", vbCritical, "Discord Music Presence"
    WScript.Quit 1
End If

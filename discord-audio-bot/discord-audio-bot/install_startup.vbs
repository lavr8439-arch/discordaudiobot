Option Explicit

Dim shell, fso, folder, startup, shortcut, shortcutPath
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)

If Not fso.FileExists(folder & "\start_hidden.vbs") Then
    MsgBox "Could not find start_hidden.vbs in the program folder.", vbCritical, "Discord Music Presence"
    WScript.Quit 1
End If

startup = shell.SpecialFolders("Startup")
shortcutPath = startup & "\Discord Music Presence.lnk"
Set shortcut = shell.CreateShortcut(shortcutPath)
shortcut.TargetPath = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\wscript.exe")
shortcut.Arguments = "//B //Nologo """ & folder & "\start_hidden.vbs"""
shortcut.WorkingDirectory = folder
shortcut.Description = "Start Discord Music Presence in the background"
shortcut.WindowStyle = 7
shortcut.Save

MsgBox "Discord Music Presence will start in the background when you sign in to Windows.", vbInformation, "Discord Music Presence"

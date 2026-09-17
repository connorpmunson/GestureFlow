Option Explicit
Dim fs, root, python, shell
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
python = fs.BuildPath(root, ".venv\Scripts\pythonw.exe")
If Not fs.FileExists(python) Then
  MsgBox "Run Install.cmd in this folder first.", vbExclamation, "GestureFlow"
  WScript.Quit 1
End If
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = root
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & fs.BuildPath(root, "main.py") & Chr(34), 0, False

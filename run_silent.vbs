Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
baseFolder = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = baseFolder
WshShell.Run "python -m streamlit run app.py", 0, False

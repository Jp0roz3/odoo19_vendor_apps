' ==============================================================================
' VenPOS Fiscal Agent - Lanzador Silencioso (Invisible) para Windows
' Ejecuta el micro-agente fiscal en segundo plano SIN VENTANA de consola.
' ==============================================================================
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

WshShell.CurrentDirectory = scriptDir
agentScript = """" & scriptDir & "\fiscal_agent.py"""

' Ejecuta con pythonw.exe (sin consola) y ventana oculta (0)
WshShell.Run "pythonw.exe " & agentScript, 0, False

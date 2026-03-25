#NoEnv
SetTitleMatchMode, 2

; Wait for Claude window
WinWait, Claude Code

; Let UI initialize
Sleep, 1500

; Paste prompt
Send ^v

; Wait for paste + modal
Sleep, 2500

; Confirm modal (Paste anyway)
Send {Enter}

Sleep, 500

; í´¥ CRITICAL FIX: refocus input
Send {Esc}
Sleep, 300

; Now execute prompt
Send {Enter}

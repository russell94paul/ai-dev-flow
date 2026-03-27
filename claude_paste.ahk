#NoEnv
SetTitleMatchMode, 2

; Wait for a Claude window to become the active (focused) window.
; WinWaitActive ensures we paste into the newly launched window,
; not an existing one that was already open in the background.
WinWaitActive, Claude Code

; Let UI initialize
Sleep, 1500

; Paste prompt
Send ^v

; Wait for paste + modal
Sleep, 2500

; Confirm modal (Paste anyway)
Send {Enter}

Sleep, 500

; ��� CRITICAL FIX: refocus input
Send {Esc}
Sleep, 300

; Now execute prompt
Send {Enter}

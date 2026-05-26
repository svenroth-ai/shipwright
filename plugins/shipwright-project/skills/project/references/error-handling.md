# Error Handling

## Invalid Input File

```
Error: Cannot read requirements file

File: {path}
Reason: {file not found | not a .md file | empty file | permission denied}

Please provide a valid markdown requirements file.
```

## Session Conflict

If existing files conflict with current state:
```
AskUserQuestion:
  question: "Session state conflict detected. How should we proceed?"
  options:
    - label: "Start fresh"
      description: "Discard existing session and begin new analysis"
    - label: "Resume from Step {N}"
      description: "Continue from where the previous session stopped"
```

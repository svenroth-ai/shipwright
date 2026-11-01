Goal: The e2e harness no longer reloads the task page after the modal launched the task, and goes on without the Launch button when the task is already launched
Reason: The hard reload lost the pending auto-launch dispatch, the Launch button never appeared and runs 14 and 15 died after 2 minutes
Reference: operator brief (handed directly), runs 14 and 15

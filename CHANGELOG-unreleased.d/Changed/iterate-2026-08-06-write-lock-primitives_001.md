Windows file-lock waits now tell a real fault apart from ordinary contention: a genuine failure surfaces immediately instead of being retried for the full wait and then blamed on another process.

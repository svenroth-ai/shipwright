Durable reads now retry a byte-range-locked file on Windows even when Python reports only an errno (winerror=None), instead of raising immediately.

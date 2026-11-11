# Architecture Brief: lexer-based suite brace depth and unbound covers warning

## The problem
The test collector decides which tests sit inside a `describe` block by counting curly braces in raw text, so a brace inside a string, regex or comment makes a suite end early (tests lose their requirement tag) or never end (later tests inherit a stale tag). Separately, a requirement-covers comment that reaches no test is dropped without any message.

## What would newly, permanently exist
Nothing standing. This changes machinery that already exists: the brace count in the collector's suite-tag propagation now reads the shared TypeScript lexer already used by the collector and the gate, and the unreachable-comment case becomes a warning entry that the existing gate and audit route to a warning.

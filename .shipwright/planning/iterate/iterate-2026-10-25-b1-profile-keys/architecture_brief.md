# Architecture Brief: declare two optional profile keys

## The problem
A later brief-driven run needs to say, per stack profile, how the app is shaped for the user (for example chat-first) and where its UI is hosted. Today the profile schema does not name either key, so nobody can tell from the schema that they are meaningful.

## What would newly, permanently exist
Two optional string properties in the existing stack profile schema file, plus a docs row and a test. No new mechanism, no code reads them yet.

## Options on the table
- **A:** Declare both keys as plain optional strings in the schema.
- **B:** Declare them with a fixed list of allowed values in the schema.
- **C:** Do nothing; the schema already allows unknown keys.

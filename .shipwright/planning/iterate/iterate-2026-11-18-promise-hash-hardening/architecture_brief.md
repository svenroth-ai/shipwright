# Architecture Brief: hardening the promise lock's hashing before the lock is written

## The problem
The promise lock decides whether a change to a promise test is a decision or a reformat. Reviews of the first version
found ways to change what a locked test does while its hash stays the same (a swapped import, a rebound helper, an
autouse fixture or hook, a mark written another way), and several promise tests that check less than their sentence
claims. Once the lock exists, a weakened test can pass unnoticed.

## What already exists here
- A standard-library hashing helper that normalizes a test and the helpers, constants and fixtures it uses.
- Fifteen-plus promise tests, a promise list, and a meta-test over both.
- A freeze test that lists the files whose content the operator's lock will pin.

## What would newly, permanently exist
Nothing structural beyond one more small standard-library module (the lock's entry keys and its check) split off
because the helper reached its size limit. The rest changes machinery that already exists.

## Options on the table
- **A:** extend the hashing helper and the tests in place, as above.
- **B:** hash whole files instead of per-test closures.
- **C:** do nothing and rely on review at the stop.

## Constraints that are not negotiable
The skill and its scripts stay unchanged; the tests stay green against the unchanged skill; formatting, comments and
import order still must not move a hash.

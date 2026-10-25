# Mini-plan B1: declare ux_shape and ui_host in the stack profile schema

Spec: sub-iterates/B1-profile-keys.md (BRIEF D7, section 3/B1).

1. shared/schemas/stack_profile.schema.json: add optional `ux_shape` and `ui_host`, both `{"type": "string"}` with descriptions. No enum, not in `required`.
2. No resolver code, no edit to profile_resolver.py or any loader's PROFILE_KEYS_READ (the first reading unit adds its own).
3. docs/stack-profiles.md: one row in the "Minimum fields" table.
4. shared/tests/test_stack_profile_schema.py (tagged FR-01.06): test that both keys are optional plain strings (no enum), accepted as strings, rejected as non-strings, and that every bundled profile still validates.

Risk: bundled profiles unchanged; schema allows additional properties already, so behavior for existing profiles is identical.

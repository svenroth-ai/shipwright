A phase step with no validator (`security`) now records `gate_result: "not_checked"` in `validation_overrides[]` instead of `"pass"`, which had asserted that a gate was satisfied where no gate exists

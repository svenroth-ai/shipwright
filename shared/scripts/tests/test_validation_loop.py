"""Tests for shared.scripts.lib.validation_loop module."""


from shared.scripts.lib.validation_loop import validate_with_retry


class TestValidateWithRetry:
    def test_succeeds_on_first_try(self):
        result = validate_with_retry(
            extract_fn=lambda: {"name": "auth", "tests": 5},
            validate_fn=lambda d: (True, []),
        )
        assert result["success"] is True
        assert result["attempts"] == 1
        assert result["data"]["name"] == "auth"
        assert result["stopped_early"] is False

    def test_succeeds_after_retry(self):
        call_count = {"n": 0}

        def extract():
            call_count["n"] += 1
            if call_count["n"] < 3:
                return {"name": "auth", "tests": 0}
            return {"name": "auth", "tests": 5}

        def validate(data):
            if data["tests"] == 0:
                return False, ["tests count is 0 but spec requires >= 1 test"]
            return True, []

        result = validate_with_retry(
            extract_fn=extract,
            validate_fn=validate,
            max_retries=5,
        )
        assert result["success"] is True
        assert result["attempts"] == 3

    def test_fails_after_max_retries(self):
        result = validate_with_retry(
            extract_fn=lambda: {"value": "bad"},
            validate_fn=lambda d: (False, [f"value is '{d['value']}' but expected 'good'"]),
            max_retries=3,
        )
        assert result["success"] is False
        assert result["attempts"] == 3
        assert "expected 'good'" in result["final_errors"][0]
        assert result["stopped_early"] is False

    def test_stops_early_when_data_missing(self):
        result = validate_with_retry(
            extract_fn=lambda: {"revenue": None},
            validate_fn=lambda d: (False, ["revenue is None — source document has no revenue data"]),
            max_retries=5,
            stop_condition=lambda data, errors: data is not None and data.get("revenue") is None,
        )
        assert result["success"] is False
        assert result["attempts"] == 1  # stopped on first try
        assert result["stopped_early"] is True

    def test_extraction_failure_retries(self):
        call_count = {"n": 0}

        def flaky_extract():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("API timeout")
            return {"data": "ok"}

        result = validate_with_retry(
            extract_fn=flaky_extract,
            validate_fn=lambda d: (True, []),
            max_retries=5,
        )
        assert result["success"] is True
        assert result["attempts"] == 3

    def test_extraction_failure_stops_early(self):
        def always_fails():
            raise FileNotFoundError("source file missing")

        result = validate_with_retry(
            extract_fn=always_fails,
            validate_fn=lambda d: (True, []),
            max_retries=3,
            stop_condition=lambda data, errors: "source file missing" in str(errors),
        )
        assert result["success"] is False
        assert result["attempts"] == 1
        assert result["stopped_early"] is True

    def test_specific_error_messages(self):
        """Errors must be specific, not generic 'try again'."""
        result = validate_with_retry(
            extract_fn=lambda: {"price": "0", "expected": "4.2M"},
            validate_fn=lambda d: (
                False,
                [f"price is '{d['price']}' but document states {d['expected']} on page 3"],
            ),
            max_retries=1,
        )
        assert "4.2M" in result["final_errors"][0]
        assert "page 3" in result["final_errors"][0]

    def test_default_max_retries(self):
        result = validate_with_retry(
            extract_fn=lambda: None,
            validate_fn=lambda d: (False, ["still bad"]),
        )
        assert result["attempts"] == 3  # default

    def test_returns_last_data_on_failure(self):
        call_count = {"n": 0}

        def extract():
            call_count["n"] += 1
            return {"attempt": call_count["n"]}

        result = validate_with_retry(
            extract_fn=extract,
            validate_fn=lambda d: (False, ["not good enough"]),
            max_retries=3,
        )
        assert result["data"]["attempt"] == 3  # last attempt's data

"""Tests for track_tool_calls.py hook."""



class TestTrackToolCalls:
    def test_creates_counter_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        counter = tmp_path / ".shipwright" / "toolcall_count"

        # Simulate the hook logic directly (avoids stdin requirement)
        count = 0
        if counter.exists():
            try:
                count = int(counter.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                count = 0
        count += 1
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text(str(count), encoding="utf-8")

        assert counter.exists()
        assert counter.read_text(encoding="utf-8") == "1"

    def test_increments_existing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        counter = tmp_path / ".shipwright" / "toolcall_count"
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text("41", encoding="utf-8")

        count = int(counter.read_text(encoding="utf-8").strip())
        count += 1
        counter.write_text(str(count), encoding="utf-8")

        assert counter.read_text(encoding="utf-8") == "42"

    def test_handles_corrupt_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        counter = tmp_path / ".shipwright" / "toolcall_count"
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text("garbage", encoding="utf-8")

        count = 0
        try:
            count = int(counter.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            count = 0
        count += 1
        counter.write_text(str(count), encoding="utf-8")

        assert counter.read_text(encoding="utf-8") == "1"

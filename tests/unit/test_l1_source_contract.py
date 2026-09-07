import unittest

from memcarry.domain.l1_source import L1SourceFingerprint


class L1SourceFingerprintTest(unittest.TestCase):
    def test_identical_fingerprint_is_unchanged(self):
        previous = L1SourceFingerprint(
            source_id="claude-history",
            size=1024,
            mtime_ns=100,
            digest="abc",
            cursor="session-10",
        )
        current = L1SourceFingerprint(
            source_id="claude-history",
            size=1024,
            mtime_ns=100,
            digest="abc",
            cursor="session-10",
        )

        self.assertFalse(current.changed_from(previous))

    def test_size_or_mtime_change_marks_source_changed_without_hash_requirement(self):
        previous = L1SourceFingerprint(
            source_id="codex-history",
            size=1024,
            mtime_ns=100,
        )
        current = L1SourceFingerprint(
            source_id="codex-history",
            size=2048,
            mtime_ns=200,
        )

        self.assertTrue(current.changed_from(previous))

    def test_digest_change_marks_source_changed_when_metadata_matches(self):
        previous = L1SourceFingerprint(
            source_id="gemini-history",
            size=1024,
            mtime_ns=100,
            digest="old",
        )
        current = L1SourceFingerprint(
            source_id="gemini-history",
            size=1024,
            mtime_ns=100,
            digest="new",
        )

        self.assertTrue(current.changed_from(previous))

    def test_new_source_is_changed(self):
        current = L1SourceFingerprint(
            source_id="agy-history",
            size=1,
            mtime_ns=1,
        )

        self.assertTrue(current.changed_from(None))

    def test_cursor_does_not_change_source_identity(self):
        previous = L1SourceFingerprint(
            source_id="claude-history",
            size=1024,
            mtime_ns=100,
            digest="abc",
            cursor="session-9",
        )
        current = L1SourceFingerprint(
            source_id="claude-history",
            size=1024,
            mtime_ns=100,
            digest="abc",
            cursor="session-10",
        )

        self.assertFalse(current.changed_from(previous))


if __name__ == "__main__":
    unittest.main()

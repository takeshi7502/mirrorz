import tempfile
import unittest
from pathlib import Path

from scripts.migrate_legacy_config import migrate, prepare_settings, read_settings


class ConfigMigrationTests(unittest.TestCase):
    def test_owner_dump_alias_is_mapped_and_old_auto_update_is_disabled(self):
        settings, ignored = prepare_settings(
            {
                "BOT_TOKEN": "test-token",
                "LEECH_DUMP_CHAT": "b:-10001",
                "UPSTREAM_REPO": "https://example.com/old-fork.git",
                "USER_QUOTA_ENABLED": True,
                "CLEAN_LOG_MSG": False,
            }
        )
        self.assertEqual(settings["BOT_TOKEN"], "test-token")
        self.assertEqual(settings["LEECH_LOG_CHAT"], "b:-10001")
        self.assertEqual(settings["UPSTREAM_REPO"], "")
        self.assertNotIn("USER_QUOTA_ENABLED", settings)
        self.assertEqual(settings["UPSTREAM_BRANCH"], "wzv3-takeshi")
        self.assertEqual(ignored, ["CLEAN_LOG_MSG", "USER_QUOTA_ENABLED"])

    def test_config_is_parsed_without_executing_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.py"
            path.write_text('BOT_TOKEN = print("must never run")\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nonliteral"):
                read_settings(path)

    def test_dry_run_does_not_copy_credentials_or_create_config(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "old"
            source.mkdir()
            (source / "config.py").write_text(
                'BOT_TOKEN = "test-token"\n', encoding="utf-8"
            )
            (source / "token.pickle").write_bytes(b"test-credential")
            output = Path(directory) / "new" / "config.py"
            report = migrate(source, output, copy_credentials=True)
            self.assertFalse(report["written"])
            self.assertFalse(output.parent.exists())
            self.assertNotIn("test-token", str(report))

    def test_write_copies_files_and_refuses_to_overwrite_config(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "old"
            source.mkdir()
            (source / "config.py").write_text(
                'BOT_TOKEN = "test-token"\n', encoding="utf-8"
            )
            (source / "token.pickle").write_bytes(b"test-credential")
            output = Path(directory) / "new" / "config.py"
            migrate(source, output, write=True, copy_credentials=True)
            self.assertEqual(read_settings(output)["BOT_TOKEN"], "test-token")
            self.assertEqual(
                (output.parent / "token.pickle").read_bytes(), b"test-credential"
            )
            with self.assertRaises(FileExistsError):
                migrate(source, output, write=True)


if __name__ == "__main__":
    unittest.main()

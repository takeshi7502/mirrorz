import os
import unittest
from unittest.mock import patch

from tests.migration_support import isolated_bot, module


class DatabaseSettingsTests(unittest.TestCase):
    def setUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.config = self.state.config
        self.config.BOT_TOKEN = "test-token"
        self.config.TELEGRAM_API = 123
        self.config.TELEGRAM_HASH = "test-hash"

    def test_legacy_config_cannot_override_db_only_settings(self):
        self.config.USER_QUOTA_ENABLED = False
        settings = module(
            "config",
            BOT_TOKEN="test-token",
            OWNER_ID=1,
            TELEGRAM_API=123,
            TELEGRAM_HASH="test-hash",
            USER_QUOTA_ENABLED=True,
            USER_QUOTA_DAILY_LIMIT=999,
            REFERRAL_ENABLED=True,
        )
        with patch.dict("sys.modules", {"config": settings}):
            self.config.load_config()
        self.assertFalse(self.config.USER_QUOTA_ENABLED)
        self.assertEqual(self.config.USER_QUOTA_DAILY_LIMIT, 2)
        self.assertFalse(self.config.REFERRAL_ENABLED)

    def test_environment_cannot_override_values_loaded_from_db(self):
        self.config.load_dict(
            {
                "USER_QUOTA_ENABLED": True,
                "USER_QUOTA_DAILY_LIMIT": 18,
                "REFERRAL_ENABLED": True,
            }
        )
        with patch.dict(
            os.environ,
            {
                "USER_QUOTA_ENABLED": "false",
                "USER_QUOTA_DAILY_LIMIT": "999",
                "REFERRAL_ENABLED": "false",
            },
            clear=True,
        ):
            self.config.load_env()
        self.assertTrue(self.config.USER_QUOTA_ENABLED)
        self.assertEqual(self.config.USER_QUOTA_DAILY_LIMIT, 18)
        self.assertTrue(self.config.REFERRAL_ENABLED)

    def test_db_values_load_and_stay_out_of_deployment_snapshot(self):
        saved = {
            "USER_QUOTA_ENABLED": False,
            "USER_QUOTA_DAILY_LIMIT": 0,
            "REFERRAL_ENABLED": True,
            "REFERRAL_REWARD_QUOTA": 12,
            "REFERRAL_REQUIRED_CHAT_LINK": "https://t.me/test_group",
        }
        self.config.load_dict(saved)
        for key, value in saved.items():
            self.assertEqual(getattr(self.config, key), value)
        snapshot = self.config.deployment_settings(
            {**saved, "BOT_TOKEN": " test-token ", "__name__": "config"}
        )
        self.assertEqual(snapshot, {"BOT_TOKEN": "test-token"})
        # save_settings()/update_config() must still be able to persist these keys.
        runtime = self.config.get_all()
        self.assertEqual({key: runtime[key] for key in saved}, saved)


if __name__ == "__main__":
    unittest.main()

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.migration_support import isolated_bot


class ReferralMigrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.r = self.state.referral
        self.state.config.REFERRAL_ENABLED = True
        self.state.config.REFERRAL_REQUIRED_CHAT_ID = -10001
        self.state.config.REFERRAL_REQUIRED_CHAT_LINK = "https://t.me/example_group"
        self.state.config.REFERRAL_SUBSCRIBE_ENABLED = True
        self.state.config.REFERRAL_SUBSCRIBE_CHANNEL_LINK = (
            "https://t.me/example_channel"
        )
        self.client = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status=SimpleNamespace(name="MEMBER"))
            )
        )

    async def test_concurrent_referral_claims_reward_inviter_once(self):
        await self.r.set_pending_referral(10, 20)
        results = await asyncio.gather(
            *(self.r.complete_referral(self.client, 10) for _ in range(8))
        )
        self.assertEqual(sum(ok for ok, _ in results), 1)
        self.assertEqual(self.state.quota.quota_summary(20)["extra_quota"], 15)
        self.assertEqual(self.state.saved[10]["REFERRAL"]["status"], "completed")

    async def test_concurrent_subscribe_claims_reward_once(self):
        results = await asyncio.gather(
            *(self.r.complete_subscribe_reward(self.client, 10) for _ in range(8))
        )
        self.assertEqual(sum(ok for ok, _ in results), 1)
        self.assertEqual(self.state.quota.quota_summary(10)["extra_quota"], 36)

    async def test_not_a_member_receives_no_reward(self):
        self.client.get_chat_member.return_value.status.name = "LEFT"
        ok, _ = await self.r.complete_subscribe_reward(self.client, 10)
        self.assertFalse(ok)
        self.assertEqual(self.state.quota.quota_summary(10)["extra_quota"], 0)

    async def test_self_referral_admin_and_existing_users_are_rejected(self):
        self.assertFalse((await self.r.set_pending_referral(10, 10))[0])
        self.assertFalse((await self.r.set_pending_referral(10, 1))[0])
        self.state.user_data[10] = {"USER_QUOTA": {"total_used": 1}}
        self.assertFalse((await self.r.set_pending_referral(10, 20))[0])

    async def test_disabled_referral_does_not_create_pending_record(self):
        self.state.config.REFERRAL_ENABLED = False
        self.assertFalse((await self.r.set_pending_referral(10, 20))[0])
        self.assertNotIn(10, self.state.user_data)


if __name__ == "__main__":
    unittest.main()

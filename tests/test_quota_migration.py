import asyncio
import unittest
from datetime import datetime, timedelta
from time import time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from tests.migration_support import isolated_bot, listener, message


class QuotaMigrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context = isolated_bot()
        self.state = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.q = self.state.quota

    async def test_reservation_confirmation_is_idempotent(self):
        msg = message()
        self.assertIsNone(await self.q.quota_precheck(msg))
        self.assertEqual(self.q.quota_summary(10)["remaining"], 1)
        await self.q.quota_confirm_task(listener(msg))
        await self.q.quota_confirm_task(listener(msg))
        self.assertEqual(self.q.quota_summary(10)["daily_used"], 1)
        self.assertEqual(self.state.saved[10]["USER_QUOTA"]["total_used"], 1)

    async def test_concurrent_requests_cannot_overspend(self):
        results = await asyncio.gather(
            *(self.q.quota_precheck(message(mid=i)) for i in range(12))
        )
        self.assertEqual(sum(result is None for result in results), 2)
        self.assertEqual(self.q.quota_summary(10)["remaining"], 0)

    async def test_torrent_reserves_two_and_charges_two(self):
        item = listener(link="magnet:?xt=urn:btih:test")
        await self.q.quota_reserve_task(item)
        self.assertEqual(self.q.quota_summary(10)["remaining"], 0)
        await self.q.quota_confirm_task(item)
        self.assertEqual(self.q.quota_summary(10)["daily_used"], 2)

    async def test_torrent_upgrade_checks_other_reservations(self):
        first, second = message(mid=100), message(mid=101)
        await self.q.quota_precheck(first)
        await self.q.quota_precheck(second)
        self.assertIsNotNone(await self.q.quota_precheck(first, quota_cost=2))
        self.assertEqual(self.q._quota_doc(10)["pending"]["-10001:100"]["cost"], 1)

    async def test_rechecking_same_task_does_not_double_hold(self):
        msg = message()
        await self.q.quota_precheck(msg, quota_cost=2)
        self.assertIsNone(await self.q.quota_precheck(msg, quota_cost=2))
        self.assertEqual(self.q.quota_summary(10)["pending"], 1)

    async def test_late_torrent_event_does_not_recreate_completed_hold(self):
        msg = message()
        await self.q.quota_precheck(msg)
        await self.q.quota_confirm_task(listener(msg))
        await self.q.quota_precheck(msg, quota_cost=2, existing_only=True)
        self.assertEqual(self.q.quota_summary(10)["pending"], 0)

    async def test_failed_task_releases_hold_without_charging(self):
        msg = message()
        await self.q.quota_precheck(msg)
        await self.q.quota_release_task(listener(msg), "download_error")
        self.assertEqual(self.q.quota_summary(10)["remaining"], 2)
        self.assertEqual(self.q.quota_summary(10)["daily_used"], 0)

    async def test_early_return_does_not_leak_quota(self):
        @self.q.quota_task
        async def event(item):
            await self.q.quota_precheck(item.message)

        await event(listener())
        self.assertEqual(self.q.quota_summary(10)["pending"], 0)

    async def test_running_task_retains_hold_until_completion(self):
        @self.q.quota_task
        async def event(item):
            await self.q.quota_precheck(item.message)
            self.state.task_dict[item.mid] = object()

        await event(listener())
        self.assertEqual(self.q.quota_summary(10)["pending"], 1)

    async def test_exception_and_cancellation_release_hold(self):
        for error in (ValueError, asyncio.CancelledError):

            @self.q.quota_task
            async def event(item):
                await self.q.quota_precheck(item.message)
                raise error()

            with self.assertRaises(error):
                await event(listener())
            self.assertEqual(self.q.quota_summary(10)["pending"], 0)

    async def test_restart_clears_pending_and_keeps_bonus_vip_and_settings(self):
        self.state.user_data[10] = {
            "VIP_ENABLED": True,
            "VIP_DAILY_LIMIT": 10,
            "VIP_EXPIRE_AT": 0,
            "LEECH_PREFIX": "custom",
        }
        await self.q.quota_add_extra(10, 7)
        await self.q.quota_precheck(message())
        self.assertEqual(await self.q.quota_clear_all_pending(), 1)
        saved = self.state.saved[10]
        self.assertEqual(saved["USER_QUOTA"]["extra_quota"], 7)
        self.assertTrue(saved["VIP_ENABLED"])
        self.assertEqual(saved["LEECH_PREFIX"], "custom")
        self.assertEqual(saved["USER_QUOTA"]["pending"], {})

    async def test_daily_reset_keeps_bonus_and_total_usage(self):
        now = datetime(2026, 10, 28, 4, tzinfo=ZoneInfo("UTC"))
        self.state.user_data[10] = {
            "USER_QUOTA": {
                "used_today": 2,
                "extra_quota": 5,
                "pending": {},
                "total_used": 40,
                "last_reset_key": "2026-10-27",
            }
        }
        with patch.object(self.q, "_now", return_value=now):
            result = self.q.quota_summary(10)
        self.assertEqual(result["daily_used"], 0)
        self.assertEqual(result["extra_quota"], 5)
        self.assertEqual(self.state.user_data[10]["USER_QUOTA"]["total_used"], 40)

    async def test_reset_boundary_uses_configured_hour(self):
        now = datetime(2026, 10, 28, 2, 59, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(self.q._reset_key(now), "2026-10-27")
        self.assertEqual(self.q._reset_key(now + timedelta(minutes=1)), "2026-10-28")

    async def test_bonus_is_consumed_after_daily_allowance(self):
        await self.q.quota_add_extra(10, 3)
        for i in range(3):
            msg = message(mid=i)
            await self.q.quota_precheck(msg)
            await self.q.quota_confirm_task(listener(msg))
        summary = self.q.quota_summary(10)
        self.assertEqual((summary["daily_used"], summary["extra_quota"]), (2, 2))

    async def test_vip_expiry_restores_free_limit(self):
        self.state.user_data[10] = {
            "VIP_ENABLED": True,
            "VIP_DAILY_LIMIT": 20,
            "VIP_EXPIRE_AT": int(time()) + 3600,
        }
        self.assertEqual(self.q.quota_summary(10)["daily_limit"], 20)
        self.state.user_data[10]["VIP_EXPIRE_AT"] = int(time()) - 1
        self.assertEqual(self.q.quota_summary(10)["daily_limit"], 2)
        self.assertFalse(self.q.quota_summary(10)["vip"]["active"])

    async def test_owner_sudo_and_disabled_quota_do_not_hold(self):
        self.state.sudo_users.append(2)
        self.state.user_data[3] = {"SUDO": True}
        for uid in (1, 2, 3):
            self.assertIsNone(await self.q.quota_precheck(message(uid=uid)))
            self.assertNotIn("USER_QUOTA", self.state.user_data.get(uid, {}))
        self.state.config.USER_QUOTA_ENABLED = False
        await self.q.quota_precheck(message())
        self.assertNotIn(10, self.state.user_data)

    async def test_disabling_quota_during_task_releases_existing_hold(self):
        msg = message()
        await self.q.quota_precheck(msg)
        self.state.config.USER_QUOTA_ENABLED = False
        await self.q.quota_confirm_task(listener(msg))
        self.assertEqual(self.q.quota_summary(10)["pending"], 0)
        self.assertEqual(self.q.quota_summary(10)["daily_used"], 0)

    async def test_bulk_parent_preview_does_not_consume_child_allowance(self):
        self.state.config.USER_QUOTA_DAILY_LIMIT = 1
        self.assertIsNone(await self.q.quota_precheck(message(mid=100), reserve=False))
        self.assertEqual(self.q.quota_summary(10)["pending"], 0)
        self.assertIsNone(await self.q.quota_precheck(message(mid=101)))
        self.assertEqual(self.q.quota_summary(10)["pending"], 1)

    async def test_disabled_quota_early_return_does_not_create_user_record(self):
        self.state.config.USER_QUOTA_ENABLED = False

        @self.q.quota_task
        async def event(item):
            return

        await event(listener())
        self.assertNotIn(10, self.state.user_data)


if __name__ == "__main__":
    unittest.main()

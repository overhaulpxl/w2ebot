import inspect
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs import marketplace as market_cog
from cogs import economy as economy_cog
from economy.marketplace import MarketplaceResult
from economy.database import initialize_database


EXPECTED_MEMBER = {
    "browse", "search", "details", "sell", "buy", "cancel", "my-listings", "history",
    "price-check", "watch", "watchlist", "unwatch", "claim-returns", "report", "status",
}
EXPECTED_ADMIN = {
    "inspect", "pause", "resume", "pause-listing", "review", "cancel", "return",
    "freeze-user", "unfreeze-user", "reports", "resolve-report", "reconcile",
}


class FakeTree:
    def __init__(self):
        self.groups = []

    def add_command(self, command):
        self.groups.append(command)


class FakeClient:
    async def is_owner(self, _user):
        return False


class FakeMessage:
    def __init__(self):
        self.id = 123
        self.guild = SimpleNamespace(id=1)
        self.author = SimpleNamespace(id=20)
        self.replies = []

    async def reply(self, text, **_kwargs):
        self.replies.append(text)


class MarketplaceCommandTests(unittest.IsolatedAsyncioTestCase):
    def test_complete_slash_trees_and_typed_parameters(self):
        member = market_cog.MarketGroup()
        admin = market_cog.MarketAdminGroup(FakeClient())
        self.assertEqual({command.name for command in member.commands}, EXPECTED_MEMBER)
        self.assertEqual({command.name for command in admin.commands}, EXPECTED_ADMIN)
        for command in (*member.commands, *admin.commands):
            signature = inspect.signature(command.callback)
            for name, parameter in signature.parameters.items():
                if name not in ("self", "interaction"):
                    self.assertIsNot(parameter.annotation, inspect.Parameter.empty, f"{command.name}:{name}")

    async def test_disabled_autocomplete_fails_closed_without_database(self):
        interaction = SimpleNamespace(guild_id=1, user=SimpleNamespace(id=2))
        with patch.object(market_cog, "marketplace_enabled", return_value=False):
            self.assertEqual(await market_cog._listing_choices(interaction, ""), [])
            self.assertEqual(await market_cog._catalog_version_choices(interaction, ""), [])

    async def test_enabled_autocomplete_fails_closed_before_migration(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        path = handle.name
        handle.close()
        try:
            await initialize_database(path)
            interaction = SimpleNamespace(guild_id=1, user=SimpleNamespace(id=2))
            with patch.object(market_cog, "marketplace_enabled", return_value=True), \
                    patch.object(market_cog, "DB_PATH", path):
                self.assertEqual(await market_cog._listing_choices(interaction, ""), [])
                self.assertEqual(await market_cog._catalog_version_choices(interaction, ""), [])
        finally:
            os.unlink(path)

    async def test_staff_authorization_is_rechecked(self):
        admin = SimpleNamespace(guild_permissions=SimpleNamespace(administrator=True))
        member = SimpleNamespace(guild_permissions=SimpleNamespace(administrator=False))
        self.assertTrue(await market_cog._staff_allowed(SimpleNamespace(user=admin), FakeClient()))
        self.assertFalse(await market_cog._staff_allowed(SimpleNamespace(user=member), FakeClient()))

    async def test_prefix_dispatcher_routes_every_supported_action(self):
        tree = FakeTree()
        market_cog.setup(tree, FakeClient())
        from core import PREFIX_COMMAND_HANDLERS
        handler = PREFIX_COMMAND_HANDLERS["rpg-market"]
        listing = {
            "listingId": "listing-1", "equipmentInstanceId": "eq-1", "stackItemId": None,
            "remainingQuantity": 1, "unitPriceEtm": 100_000, "status": "ACTIVE",
        }
        ok = MarketplaceResult(True, "ok", "ok", listing_id="listing-1", sale_id="sale-1")
        patches = (
            patch.object(market_cog, "marketplace_enabled", return_value=True),
            patch.object(market_cog, "browse_listings", AsyncMock(return_value=[listing])),
            patch.object(market_cog, "get_listing_details", AsyncMock(return_value=listing)),
            patch.object(market_cog, "reserve_purchase", AsyncMock(return_value=ok)),
            patch.object(market_cog, "settle_purchase", AsyncMock(return_value=ok)),
            patch.object(market_cog, "cancel_listing", AsyncMock(return_value=ok)),
            patch.object(market_cog, "set_watch", AsyncMock(return_value=ok)),
            patch.object(market_cog, "list_watchlist", AsyncMock(return_value=[listing])),
            patch.object(market_cog, "list_history", AsyncMock(return_value=[{"saleId": "sale-1", "status": "COMMITTED"}])),
            patch.object(market_cog, "price_check", AsyncMock(return_value={"count": 1, "minimum": 1, "median": 1, "maximum": 1})),
            patch.object(market_cog, "claim_returns", AsyncMock(return_value={"settled": 1, "scanned": 1})),
            patch.object(market_cog, "create_report", AsyncMock(return_value=ok)),
            patch.object(market_cog, "marketplace_status", AsyncMock(return_value={"paused": False})),
        )
        for context in patches:
            context.start()
        try:
            actions = (
                ["browse"], ["search", "iron"], ["details", "listing-1"], ["sell"],
                ["buy", "listing-1", "1"], ["cancel", "listing-1"], ["my-listings"],
                ["history", "sales"], ["price-check", "item", "phase3-v1"],
                ["watch", "listing-1"], ["watchlist"], ["unwatch", "listing-1"],
                ["claim-returns"], ["report", "listing-1", "PRICE", "detail"], ["status"],
            )
            for args in actions:
                message = FakeMessage()
                await handler(message, args)
                self.assertEqual(len(message.replies), 1, args)
            message = FakeMessage()
            await handler(message, ["sell"])
            self.assertIn("/rpg-market sell", message.replies[0])
        finally:
            for context in reversed(patches):
                context.stop()

    def test_internal_api_and_forbidden_alias_contract(self):
        from core import DEAL_PREFIX_RESERVED_TOP_LEVEL
        self.assertNotIn("market", DEAL_PREFIX_RESERVED_TOP_LEVEL)
        source = inspect.getsource(__import__("core"))
        self.assertIn("/api/economy/v1-marketplace/action", source)
        self.assertIn("require_token(request)", source)

    async def test_internal_api_token_gate_fails_closed_before_marketplace_service(self):
        import core

        invalid = SimpleNamespace(headers={"X-Auth-Token": "wrong"})
        valid = SimpleNamespace(headers={"X-Auth-Token": "test-secret"})
        with patch.object(core, "DASHBOARD_TOKEN", "test-secret"):
            denied = await core.api_marketplace_v1_action(invalid)
            disabled = await core.api_marketplace_v1_action(valid)
        self.assertEqual(denied.status, 401)
        self.assertEqual(disabled.status, 409)

    async def test_restart_watch_notification_uses_persisted_event_key(self):
        class EmptyHistory:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise StopAsyncIteration

        sent_message = SimpleNamespace(id=777)
        channel = SimpleNamespace(
            history=lambda limit: EmptyHistory(), send=AsyncMock(return_value=sent_message),
        )
        user = SimpleNamespace(create_dm=AsyncMock(return_value=channel))
        client = SimpleNamespace(get_user=lambda _user_id: user)
        rows = [{
            "eventId": "event-1", "eventKey": "listing:listing-1:sale:sale-1",
            "guildId": "1", "userId": "20", "listingId": "listing-1",
        }]
        with patch.object(
            economy_cog, "claim_notification_events", AsyncMock(return_value=rows)
        ), patch.object(
            economy_cog, "finalize_notification_event", AsyncMock(return_value=True)
        ) as marker:
            result = await economy_cog._deliver_phase4_watch_notifications(client)
        self.assertEqual(result, {"scanned": 1, "delivered": 1, "failed": 0})
        self.assertEqual(marker.await_args.kwargs["event_id"], "event-1")
        self.assertTrue(marker.await_args.kwargs["sent"])
        self.assertEqual(marker.await_args.kwargs["message_id"], 777)

    async def test_watch_notification_adopts_existing_marker_without_resend(self):
        event_key = "listing:listing-1:sale:sale-1"

        class ExistingHistory:
            def __init__(self):
                self.rows = iter((SimpleNamespace(
                    id=778, content=f"update\nW2E-MARKET-EVENT:{event_key}",
                ),))
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self.rows)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc

        channel = SimpleNamespace(
            history=lambda limit: ExistingHistory(), send=AsyncMock(),
        )
        user = SimpleNamespace(create_dm=AsyncMock(return_value=channel))
        client = SimpleNamespace(get_user=lambda _user_id: user)
        rows = [{
            "eventId": "event-1", "eventKey": event_key, "guildId": "1",
            "userId": "20", "listingId": "listing-1",
        }]
        with patch.object(
            economy_cog, "claim_notification_events", AsyncMock(return_value=rows)
        ), patch.object(
            economy_cog, "finalize_notification_event", AsyncMock(return_value=True)
        ) as marker:
            result = await economy_cog._deliver_phase4_watch_notifications(client)
        self.assertEqual(result, {"scanned": 1, "delivered": 1, "failed": 0})
        channel.send.assert_not_awaited()
        self.assertEqual(marker.await_args.kwargs["message_id"], 778)


if __name__ == "__main__":
    unittest.main()

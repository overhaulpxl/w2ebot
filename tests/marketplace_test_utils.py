import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import aiosqlite

from economy.database import initialize_database, configure_connection, ensure_system_accounts
from economy.constants import RPG_PHASE3_CATALOG_VERSION
from economy.inventory import adjust_stack
from economy.phase3_migrations import apply_phase3_staging
from economy.phase4_migrations import apply_phase4_staging
from economy.marketplace import (
    issue_discord_staff_authorization, issue_internal_api_authorization,
    issue_member_authorization,
)


NOW = "2026-01-01T00:00:00+00:00"


class MarketplaceDatabaseMixin:
    def member_auth(self, user_id, request_id=None, guild_id="1"):
        return issue_member_authorization(
            actor_id=user_id, guild_id=guild_id,
            request_id=request_id or f"test-member:{user_id}",
        )

    def staff_auth(self, user_id="99", request_id=None, guild_id="1", *, owner=False):
        return issue_discord_staff_authorization(
            actor_id=user_id, guild_id=guild_id,
            request_id=request_id or f"test-staff:{user_id}",
            verified_administrator=not owner, verified_bot_owner=owner,
        )

    def api_auth(self, request_id="test-api", guild_id="1"):
        return issue_internal_api_authorization(
            actor_id="internal-api-principal", guild_id=guild_id,
            request_id=request_id, verified_api_principal=True,
        )

    async def asyncSetUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()
        self.production_path = self.db_path + ".production"
        await initialize_database(self.db_path)
        await apply_phase3_staging(self.db_path, production_db=self.production_path)
        await apply_phase4_staging(self.db_path, production_db=self.production_path)

    async def asyncTearDown(self):
        connection = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            connection.close()
        os.unlink(self.db_path)

    async def fund_user(self, user_id, amount=10_000_000_000, guild_id="1"):
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await ensure_system_accounts(db, guild_id, NOW)
            await db.execute(
                "INSERT INTO EconomyWallet (guildId,userId,etmBalance,ecyBalance,version,createdAt,updatedAt) "
                "VALUES (?,?,?,0,0,?,?) ON CONFLICT(guildId,userId) DO UPDATE SET etmBalance=excluded.etmBalance",
                (str(guild_id), str(user_id), int(amount), NOW, NOW),
            )
            await db.commit()

    async def add_equipment(self, instance_id, owner_id, *, item_id="eq_wanderer_blade",
                            catalog_version=RPG_PHASE3_CATALOG_VERSION, binding="BOUND_ON_EQUIP", guild_id="1"):
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await db.execute(
                "INSERT INTO RpgEquipmentInstance "
                "(equipmentInstanceId,guildId,ownerId,itemId,catalogVersion,slot,enhancementLevel,pityBps,"
                "bindingStatus,status,acquiredSource,createdAt,updatedAt) "
                "VALUES (?,?,?,?,?,'WEAPON',0,0,?,'OWNED','TEST',?,?)",
                (str(instance_id), str(guild_id), str(owner_id), item_id, catalog_version, binding, NOW, NOW),
            )
            await db.commit()

    async def add_stack(self, user_id, item_id="mat_iron_shard", quantity=10, *,
                        catalog_version=RPG_PHASE3_CATALOG_VERSION, binding="UNBOUND", status="ACTIVE", guild_id="1"):
        async with aiosqlite.connect(self.db_path) as db:
            await configure_connection(db)
            await adjust_stack(
                db, guild_id, user_id, item_id, int(quantity), NOW,
                catalog_version=catalog_version, binding_status=binding, status=status,
            )
            await db.commit()

    async def scalar(self, query, params=()):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                return (await cursor.fetchone())[0]

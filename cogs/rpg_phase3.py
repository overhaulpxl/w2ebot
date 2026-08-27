"""Adapter Discord untuk service RPG Phase 3.

Semua mutasi tetap berada di economy service. Cog ini hanya validasi lifecycle,
permission, parsing command, dan rendering respons.
"""

import discord
from discord import app_commands

from core import DB_PATH, add_coins, load_json, register_prefix_command_handler, save_json
from economy.adventures import reserve_dungeon, settle_dungeon
from economy.bosses import boss_status, settle_boss, start_boss
from economy.catalog import DUNGEONS, EQUIPMENT
from economy.constants import ECONOMY_PHASE2_ENABLED, ECONOMY_PHASE3_ENABLED, ECONOMY_V1_ENABLED
from economy.crafting import reserve_craft, settle_craft
from economy.enhancement import reserve_enhancement, settle_enhancement
from economy.equipment import equip_instance
from economy.open_items import reserve_open_item, settle_open_item
from economy.pets import activate_pet, list_pets


def phase3_enabled():
    return ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE3_ENABLED


async def _reply(interaction, text, *, ephemeral=False, embed=None):
    kwargs = {"ephemeral": ephemeral}
    if embed is not None:
        kwargs["embed"] = embed
    else:
        kwargs["content"] = text
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


async def _defer(interaction, *, ephemeral=False):
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=ephemeral)


async def _require_phase3(interaction):
    if phase3_enabled():
        return True
    await _reply(interaction, "RPG Phase 3 belum diaktifkan. Legacy RPG tetap digunakan.", ephemeral=True)
    return False


async def _autocomplete_ready(interaction, table):
    if not phase3_enabled() or not getattr(interaction, "guild_id", None):
        return False
    if not getattr(getattr(interaction, "user", None), "id", None):
        return False
    import aiosqlite
    try:
        async with _pool.acquire() as db:
            rows = await db.fetch(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=$1", table,),
                return await cursor.fetchone() is not None
    except (aiosqlite.Error, OSError):
        return False


async def _equipment_choices(interaction, current):
    if not await _autocomplete_ready(interaction, "RpgEquipmentInstance"):
        return []
    current = str(current or "").lower()
    # Autocomplete hanya membaca instance; tidak membuat profile atau inventory.
    import aiosqlite
    async with _pool.acquire() as db:
        async with db.execute(
            "SELECT equipmentInstanceId,itemId,enhancementLevel FROM RpgEquipmentInstance "
            "WHERE guildId=$1 AND ownerId=$2 AND status='OWNED' ORDER BY createdAt LIMIT 25", str(interaction.guild_id), str(interaction.user.id),
        )
    choices = []
    for instance_id, item_id, enhancement in rows:
        name = f"{EQUIPMENT.get(item_id, {}).get('name', item_id)} +{enhancement}"
        if current in name.lower() or current in str(instance_id).lower():
            choices.append(app_commands.Choice(name=name[:100], value=str(instance_id))
    return choices[:25]


async def _pet_choices(interaction, current):
    if not await _autocomplete_ready(interaction, "RpgPetInstance"):
        return []
    current = str(current or "").lower()
    rows = await list_pets(DB_PATH, interaction.guild_id, interaction.user.id)
    return [
        app_commands.Choice(name=f"{row['name']} Lv.{row['level']}"[:100], value=row["petInstanceId"])
        for row in rows if current in row["name"].lower() or current in row["petInstanceId"].lower()
    ][:25]


async def _open_item_choices(interaction, current):
    if not await _autocomplete_ready(interaction, "RpgInventoryStack"):
        return []
    current = str(current or "").lower()
    import aiosqlite
    async with _pool.acquire() as db:
        rows = await db.fetch(
            "SELECT itemId,quantity FROM RpgInventoryStack WHERE guildId=$1 AND userId=$2 AND quantity>0 "
            "AND (itemId LIKE 'egg_pet_%' OR itemId='item_epic_chest') ORDER BY itemId LIMIT 25", str(interaction.guild_id), str(interaction.user.id),
        )
    return [
        app_commands.Choice(name=f"{item_id} x{quantity}"[:100], value=item_id)
        for item_id, quantity in rows if current in item_id.lower()
    ][:25]


class BossGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="boss", description="Kelola dan periksa Boss Raid Phase 3")

    @app_commands.command(name="start", description="Mulai satu Boss Raid")
    @app_commands.choices(tier=[
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="Elite", value="elite"),
        app_commands.Choice(name="World", value="world"),
    ])
    async def start(self, interaction: discord.Interaction, tier: app_commands.Choice[str]):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        authorized = bool(interaction.user.guild_permissions.administrator)
        try:
            result = await start_boss(
                DB_PATH, guild_id=interaction.guild_id, tier=tier.value,
                start_key=str(interaction.id), authorized=authorized,
            )
            await _reply(interaction, f"Boss {result['tier']} berstatus **{result['status']}**.\n-# Raid ID: `{result['raid_id']}`", ephemeral=True)
        except (ValueError, PermissionError) as exc:
            await _reply(interaction, str(exc), ephemeral=True)

    @app_commands.command(name="status", description="Lihat status Boss Raid")
    async def status(self, interaction: discord.Interaction):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction)
        data = await boss_status(DB_PATH, interaction.guild_id)
        if not data:
            await _reply(interaction, "Belum ada Boss Raid.")
            return
        retry = "Ya, jalankan `/boss settle`." if data["manual_settlement_required"] else "Tidak"
        embed = discord.Embed(title="Boss Raid Status", color=0x5865F2)
        embed.add_field(name="Tier / Status", value=f"{data['tier']} / {data['status']}", inline=False)
        embed.add_field(name="HP", value=f"{data['currentHp']:,}/{data['maxHp']:,}", inline=True)
        embed.add_field(name="Peserta", value=str(data["participant_count"]), inline=True)
        embed.add_field(name="Treasury Siap", value="Ya" if data["treasury_ready"] else "Tidak", inline=True)
        embed.add_field(name="Retry Settlement", value=retry, inline=False)
        await _reply(interaction, "", embed=embed)

    @app_commands.command(name="settle", description="Retry settlement Boss yang menunggu fund")
    async def settle(self, interaction: discord.Interaction):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        try:
            result = await settle_boss(
                DB_PATH, guild_id=interaction.guild_id,
                authorized=bool(interaction.user.guild_permissions.administrator),
            )
            await _reply(interaction, result.message, ephemeral=True)
        except PermissionError as exc:
            await _reply(interaction, str(exc), ephemeral=True)


class PetGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="pet", description="Kelola pet RPG Phase 3")

    @app_commands.command(name="list", description="Lihat semua pet milikmu")
    async def list_command(self, interaction: discord.Interaction):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction)
        rows = await list_pets(DB_PATH, interaction.guild_id, interaction.user.id)
        embed = discord.Embed(title=f"Pet: {interaction.user.display_name}", color=0x5865F2)
        for row in rows[:20]:
            passive = ", ".join(f"{key}={value}" for key, value in row["passive"].items()) or "-"
            embed.add_field(
                name=f"{'[AKTIF] ' if row['active'] else ''}{row['name']} ({row['rarity']})",
                value=(f"Level {row['level']} | XP {row['xp']} | Evolusi {row['evolutionState']}\n"
                       f"Passive: {passive}\nSkill: {row['skill']}\n-# ID: `{row['petInstanceId']}`"), inline=False,
            )
        if not rows:
            embed.description = "Belum ada pet."
        await _reply(interaction, "", embed=embed)

    @app_commands.command(name="activate", description="Aktifkan pet berdasarkan instance ID")
    async def activate(self, interaction: discord.Interaction, pet: str):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        try:
            stats = await activate_pet(DB_PATH, interaction.guild_id, interaction.user.id, pet)
            await _reply(interaction, f"Pet berhasil diaktifkan. Effective Max HP: **{stats.max_hp:,}**.", ephemeral=True)
        except ValueError as exc:
            await _reply(interaction, str(exc), ephemeral=True)

    @activate.autocomplete("pet")
    async def activate_autocomplete(self, interaction: discord.Interaction, current: str):
        return await _pet_choices(interaction, current)


def setup(tree, client):
    tree.add_command(BossGroup())
    tree.add_command(PetGroup())

    @tree.command(name="enhance", description="Enhance equipment Phase 3")
    async def enhance(interaction: discord.Interaction, item: str):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        result = await reserve_enhancement(
            DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
            equipment_instance_id=item,
        )
        if hasattr(result, "ok"):
            await _reply(interaction, result.message, ephemeral=True)
            return
        settled = await settle_enhancement(
            DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id, operation_id=result[0],
        )
        await _reply(interaction, settled.message, ephemeral=True)

    enhance.autocomplete("item")(_equipment_choices)

    @tree.command(name="equip", description="Pakai equipment berdasarkan instance ID")
    async def equip(interaction: discord.Interaction, item: str):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        try:
            stats = await equip_instance(DB_PATH, interaction.guild_id, interaction.user.id, item)
            await _reply(interaction, f"Equipment dipakai. Power Score: **{stats.power_score:,}**.", ephemeral=True)
        except ValueError as exc:
            await _reply(interaction, str(exc), ephemeral=True)

    equip.autocomplete("item")(_equipment_choices)

    @tree.command(name="open", description="Buka Pet Egg atau Epic Chest")
    async def open_item(interaction: discord.Interaction, item: str):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        try:
            operation_id, _, _ = await reserve_open_item(
                DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id, item_id=item,
            )
            result, replayed = await settle_open_item(
                DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                operation_id=operation_id,
            )
            await _reply(interaction, f"Item berhasil dibuka: `{result['definition_id']}`{' (replay)' if replayed else ''}.", ephemeral=True)
        except ValueError as exc:
            await _reply(interaction, str(exc), ephemeral=True)

    open_item.autocomplete("item")(_open_item_choices)

    @tree.command(name="dungeon", description="Jalankan Dungeon Phase 3")
    async def dungeon(interaction: discord.Interaction, dungeon_id: str, use_ticket: bool = False):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        try:
            operation_id, _, _ = await reserve_dungeon(
                DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                dungeon_id=dungeon_id, use_ticket=use_ticket,
            )
            result = await settle_dungeon(
                DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                operation_id=operation_id,
            )
            await _reply(interaction, result.message, ephemeral=True)
        except ValueError as exc:
            await _reply(interaction, str(exc), ephemeral=True)

    @tree.command(name="craft", description="Craft equipment ke rarity berikutnya")
    async def craft(interaction: discord.Interaction, base_item: str):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        try:
            operation_id, _, _ = await reserve_craft(
                DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                base_equipment_instance_id=base_item,
            )
            result = await settle_craft(
                DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id,
                operation_id=operation_id,
            )
            await _reply(interaction, result.message, ephemeral=True)
        except ValueError as exc:
            await _reply(interaction, str(exc), ephemeral=True)

    craft.autocomplete("base_item")(_equipment_choices)

    @tree.command(name="quest-claim", description="Fallback slash untuk klaim Quest Phase 3")
    async def quest_claim(interaction: discord.Interaction, quest_type: str):
        if not await _require_phase3(interaction):
            return
        await _defer(interaction, ephemeral=True)
        from economy.quests import claim_quest
        result = await claim_quest(
            DB_PATH, guild_id=interaction.guild_id, user_id=interaction.user.id, quest_type=quest_type,
        )
        await _reply(interaction, result.message, ephemeral=True)

    bounty_group = app_commands.Group(name="bounty", description="Legacy bounty compatibility")

    @bounty_group.command(name="hunt", description="Buru member dengan legacy bounty")
    async def bounty_hunt(interaction: discord.Interaction, target: discord.Member):
        await _defer(interaction)
        uid, tid = str(interaction.user.id), str(target.id)
        if uid == tid:
            await _reply(interaction, "Kamu tidak dapat memburu diri sendiri.")
            return
        bounties = await load_json("bounties.json")
        reward = int(bounties.get(tid, 0) or 0)
        if reward <= 0:
            await _reply(interaction, "Target tidak memiliki bounty.")
            return
        # Jalur legacy dipertahankan; tidak menyentuh wallet V1.
        import random
        if random.random() <= 0.5:
            await _reply(interaction, "Bounty hunt gagal.")
            return
        bounties[tid] = 0
        await save_json("bounties.json", bounties)
        await add_coins(uid, reward, interaction.user.display_name)
        await _reply(interaction, f"Bounty hunt berhasil. Reward: **{reward} Koin**.")

    tree.add_command(bounty_group)

    async def prefix_boss(message, args):
        if not phase3_enabled():
            await message.reply("RPG Phase 3 belum diaktifkan.")
            return
        action = args[0].lower() if args else "status"
        authorized = bool(message.author.guild_permissions.administrator)
        if action == "start":
            if len(args) < 2:
                await message.reply("Gunakan `w!boss start <normal|elite|world>`.")
                return
            try:
                result = await start_boss(DB_PATH, guild_id=message.guild.id, tier=args[1], start_key=str(message.id), authorized=authorized)
                await message.reply(f"Boss {result['tier']} berstatus {result['status']}.")
            except (ValueError, PermissionError) as exc:
                await message.reply(str(exc))
        elif action == "settle":
            try:
                result = await settle_boss(DB_PATH, guild_id=message.guild.id, authorized=authorized)
                await message.reply(result.message)
            except PermissionError as exc:
                await message.reply(str(exc))
        else:
            data = await boss_status(DB_PATH, message.guild.id)
            await message.reply("Belum ada Boss Raid." if not data else f"{data['tier']} | HP {data['currentHp']}/{data['maxHp']} | {data['status']}")

    async def prefix_pet(message, args):
        if not phase3_enabled():
            await message.reply("RPG Phase 3 belum diaktifkan.")
            return
        action = args[0].lower() if args else "list"
        if action == "activate" and len(args) >= 2:
            try:
                await activate_pet(DB_PATH, message.guild.id, message.author.id, args[1])
                await message.reply("Pet berhasil diaktifkan.")
            except ValueError as exc:
                await message.reply(str(exc))
            return
        rows = await list_pets(DB_PATH, message.guild.id, message.author.id)
        await message.reply("\n".join(f"{'[AKTIF] ' if row['active'] else ''}{row['name']} | `{row['petInstanceId']}`" for row in rows) or "Belum ada pet.")

    async def prefix_open(message, args):
        if not phase3_enabled() or not args:
            await message.reply("Gunakan `w!open <item-id>` saat Phase 3 aktif.")
            return
        try:
            operation_id, _, _ = await reserve_open_item(DB_PATH, guild_id=message.guild.id, user_id=message.author.id, item_id=args[0])
            result, _ = await settle_open_item(DB_PATH, guild_id=message.guild.id, user_id=message.author.id, operation_id=operation_id)
            await message.reply(f"Item berhasil dibuka: `{result['definition_id']}`.")
        except ValueError as exc:
            await message.reply(str(exc))

    async def prefix_bounty(message, args):
        if len(args) < 2 or args[0].lower() != "hunt":
            await message.reply("Gunakan `w!bounty hunt <mention/user-id>`.")
            return
        raw = args[1].strip().replace("<@!", "").replace("<@", "").replace(">", "")
        if not raw.isdigit():
            await message.reply("Target bounty tidak valid.")
            return
        target = message.guild.get_member(int(raw))
        if not target or target.id == message.author.id:
            await message.reply("Target bounty tidak valid.")
            return
        bounties = await load_json("bounties.json")
        reward = int(bounties.get(str(target.id), 0) or 0)
        if reward <= 0:
            await message.reply("Target tidak memiliki bounty.")
            return
        import random
        if random.random() <= 0.5:
            await message.reply("Bounty hunt gagal.")
            return
        bounties[str(target.id)] = 0
        await save_json("bounties.json", bounties)
        await add_coins(str(message.author.id), reward, message.author.display_name)
        await message.reply(f"Bounty hunt berhasil. Reward: **{reward} Koin**.")

    register_prefix_command_handler("boss", prefix_boss)
    register_prefix_command_handler("pet", prefix_pet)
    register_prefix_command_handler("open", prefix_open)
    register_prefix_command_handler("bounty", prefix_bounty)

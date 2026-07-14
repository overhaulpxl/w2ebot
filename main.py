from core import *
from cogs.rpg import setup as setup_rpg
from cogs.ai import setup as setup_ai
from cogs.utils import setup as setup_utils
from cogs.deal import setup as setup_deal
from cogs.economy import setup as setup_economy
from cogs.rpg_phase3 import setup as setup_rpg_phase3
from cogs.marketplace import setup as setup_marketplace
from cogs.mining import setup as setup_mining

for setup_name, setup_callback in (
    ("rpg", setup_rpg), ("ai", setup_ai), ("utils", setup_utils),
    ("deal", setup_deal), ("economy", setup_economy), ("rpg_phase3", setup_rpg_phase3),
    ("marketplace", setup_marketplace),
    ("mining", setup_mining),
):
    try:
        setup_callback(tree, client)
    except discord.app_commands.CommandAlreadyRegistered as exc:
        logging.critical(
            "Duplicate command registration setup=%s command=%s",
            setup_name, getattr(exc, "name", "unknown"),
        )
        raise RuntimeError(f"Duplicate command registration pada setup {setup_name}.") from exc

if __name__ == "__main__":
    client.run(DISCORD_API_KEY)

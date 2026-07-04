from core import *
from cogs.rpg import setup as setup_rpg
from cogs.ai import setup as setup_ai
from cogs.utils import setup as setup_utils
from cogs.deal import setup as setup_deal

setup_rpg(tree, client)
setup_ai(tree, client)
setup_utils(tree, client)
setup_deal(tree, client)

if __name__ == "__main__":
    client.run(DISCORD_API_KEY)

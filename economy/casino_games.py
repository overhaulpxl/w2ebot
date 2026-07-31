"""Mesin permainan Casino V1 yang murni dan integer-only."""

from dataclasses import dataclass
import random
import secrets

from .constants import ECONOMY_MAX_AMOUNT, SQLITE_MAX_INTEGER


SLOTS_SYMBOLS = ("cherry", "lemon", "bell", "star", "diamond", "7")
SLOTS_TRIPLE_BPS = {
    "7": 80_000,
    "diamond": 50_000,
    "star": 40_000,
    "bell": 30_000,
    "cherry": 30_000,
    "lemon": 22_000,
}
GACHA_LABELS = (
    "Ampas (Zonk)",
    "Nasi Bungkus",
    "Panci Bolong",
    "Kunci Jawaban UN",
    "Waifu Wangi",
    "Pedang Excalibur",
    "Gundam Bekas",
    "Sertifikat Rumah",
)
BOX_OUTCOMES = ((50, 0), (30, 1_000), (15, 2_000), (4, 5_000), (1, 15_000))
RPS_CHOICES = ("batu", "gunting", "kertas")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("S", "H", "D", "C")


class SecureRng:
    def randbelow(self, upper):
        return secrets.randbelow(upper)

    def shuffle(self, values):
        secrets.SystemRandom().shuffle(values)


class DeterministicRng:
    def __init__(self, seed):
        self._random = random.Random(seed)

    def randbelow(self, upper):
        return self._random.randrange(upper)

    def shuffle(self, values):
        self._random.shuffle(values)


def checked_payout(stake, multiplier_bps):
    if isinstance(stake, bool) or not isinstance(stake, int) or stake < 0:
        raise ValueError("Stake harus integer non-negatif.")
    if isinstance(multiplier_bps, bool) or not isinstance(multiplier_bps, int) or multiplier_bps < 0:
        raise ValueError("Multiplier harus integer basis points non-negatif.")
    if stake > ECONOMY_MAX_AMOUNT or (multiplier_bps and stake > SQLITE_MAX_INTEGER // multiplier_bps):
        raise OverflowError("Perhitungan payout melewati batas integer yang didukung.")
    payout = stake * multiplier_bps // 10_000
    if payout > ECONOMY_MAX_AMOUNT or payout > SQLITE_MAX_INTEGER:
        raise OverflowError("Payout melewati batas ekonomi yang didukung.")
    return payout


def liability_for(game, stake):
    game = str(game).upper()
    if game == "GACHA":
        return 0
    if game == "BOX":
        return 15_000
    bps = {
        "SLOT": 80_000,
        "COINFLIP": 19_400,
        "RPS": 19_010,
        "NUMBER": 190_000,
        "BLACKJACK": 40_000,
    }.get(game)
    if bps is None:
        raise ValueError("Permainan Casino tidak dikenal.")
    return checked_payout(stake, bps)


def roll_slot(stake, rng):
    reels = tuple(SLOTS_SYMBOLS[rng.randbelow(len(SLOTS_SYMBOLS))] for _ in range(3))
    if reels[0] == reels[1] == reels[2]:
        payout = checked_payout(stake, SLOTS_TRIPLE_BPS[reels[0]])
    elif len(set(reels)) == 2:
        payout = stake * 2
    else:
        payout = 0
    return {"reels": list(reels), "grossPayoutEcy": payout}


def roll_coinflip(stake, choice, rng):
    normalized = str(choice).strip().lower()
    if normalized not in {"angka", "gambar"}:
        raise ValueError("Pilihan Coinflip harus angka atau gambar.")
    result = ("angka", "gambar")[rng.randbelow(2)]
    return {"choice": normalized, "result": result,
            "grossPayoutEcy": checked_payout(stake, 19_400) if result == normalized else 0}


def roll_rps(stake, choice, rng):
    normalized = str(choice).strip().lower()
    if normalized not in RPS_CHOICES:
        raise ValueError("Pilihan RPS harus batu, gunting, atau kertas.")
    bot = RPS_CHOICES[rng.randbelow(3)]
    wins = {("batu", "gunting"), ("gunting", "kertas"), ("kertas", "batu")}
    payout = stake if bot == normalized else checked_payout(stake, 19_010) if (normalized, bot) in wins else 0
    return {"choice": normalized, "opponent": bot, "grossPayoutEcy": payout}


def roll_number(stake, guess, rng):
    value = int(guess)
    if value < 1 or value > 20:
        raise ValueError("Tebakan harus 1 sampai 20.")
    result = rng.randbelow(20) + 1
    return {"guess": value, "result": result, "grossPayoutEcy": stake * 19 if value == result else 0}


def roll_gacha(rng):
    return {"label": GACHA_LABELS[rng.randbelow(len(GACHA_LABELS))], "grossPayoutEcy": 0}


def roll_box(rng):
    roll = rng.randbelow(100)
    cursor = 0
    for weight, payout in BOX_OUTCOMES:
        cursor += weight
        if roll < cursor:
            return {"roll": roll, "grossPayoutEcy": payout}
    raise AssertionError("Tabel Loot Box tidak lengkap.")


def card_rank(card):
    return str(card).split("-", 1)[0]


def hand_value(cards):
    total = 0
    aces = 0
    for card in cards:
        rank = card_rank(card)
        if rank == "A":
            total += 11
            aces += 1
        elif rank in {"J", "Q", "K"}:
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def new_blackjack_plan(stake, rng):
    shoe = [f"{rank}-{suit}-{deck}" for deck in range(6) for suit in SUITS for rank in RANKS]
    rng.shuffle(shoe)
    player = [shoe.pop(), shoe.pop()]
    dealer = [shoe.pop(), shoe.pop()]
    plan = {
        "stakeEcy": stake,
        "shoe": shoe,
        "hands": [{"cards": player, "stakeEcy": stake, "stood": False, "doubled": False}],
        "dealer": dealer,
        "activeHand": 0,
        "splitUsed": False,
        "state": "PLAYER_TURN",
    }
    if blackjack_natural(player) or blackjack_natural(dealer):
        plan["state"] = "DEALER_TURN"
    return plan


def blackjack_natural(cards):
    return len(cards) == 2 and hand_value(cards)[0] == 21


def blackjack_allowed_actions(plan):
    if plan["state"] != "PLAYER_TURN":
        return ()
    hand = plan["hands"][plan["activeHand"]]
    value, _ = hand_value(hand["cards"])
    actions = ["HIT", "STAND"]
    if len(plan["hands"]) == 1 and len(hand["cards"]) == 2 and value == 11 and not plan["splitUsed"]:
        actions.append("DOUBLE")
    ranks = [card_rank(c) for c in hand["cards"]]
    if len(plan["hands"]) == 1 and len(ranks) == 2 and ranks[0] == ranks[1] and ranks[0] in {"A", "8"}:
        actions.append("SPLIT")
    return tuple(actions)


def apply_blackjack_action(plan, action):
    action = str(action).upper()
    if action not in blackjack_allowed_actions(plan):
        raise ValueError("Aksi Blackjack tidak tersedia.")
    hand = plan["hands"][plan["activeHand"]]
    if action == "HIT":
        hand["cards"].append(plan["shoe"].pop())
        if hand_value(hand["cards"])[0] >= 21:
            hand["stood"] = True
    elif action == "STAND":
        hand["stood"] = True
    elif action == "DOUBLE":
        hand["stakeEcy"] *= 2
        hand["doubled"] = True
        hand["cards"].append(plan["shoe"].pop())
        hand["stood"] = True
    else:
        first, second = hand["cards"]
        plan["splitUsed"] = True
        plan["hands"] = [
            {"cards": [first, plan["shoe"].pop()], "stakeEcy": hand["stakeEcy"], "stood": False, "doubled": False},
            {"cards": [second, plan["shoe"].pop()], "stakeEcy": hand["stakeEcy"], "stood": False, "doubled": False},
        ]
        if card_rank(first) == "A":
            plan["hands"][0]["stood"] = plan["hands"][1]["stood"] = True
    while plan["activeHand"] < len(plan["hands"]) and plan["hands"][plan["activeHand"]]["stood"]:
        plan["activeHand"] += 1
    if plan["activeHand"] >= len(plan["hands"]):
        plan["state"] = "DEALER_TURN"
    return plan


def settle_blackjack_plan(plan):
    if plan["state"] == "PLAYER_TURN":
        raise ValueError("Putaran Blackjack belum selesai.")
    dealer = plan["dealer"]
    dealer_natural = blackjack_natural(dealer)
    while not dealer_natural:
        value, soft = hand_value(dealer)
        if value < 17 or (value == 17 and soft):
            dealer.append(plan["shoe"].pop())
        else:
            break
    dealer_value = hand_value(dealer)[0]
    gross = 0
    receipts = []
    for index, hand in enumerate(plan["hands"]):
        value = hand_value(hand["cards"])[0]
        natural = len(plan["hands"]) == 1 and blackjack_natural(hand["cards"])
        if value > 21 or (dealer_natural and not natural):
            payout, result = 0, "LOSE"
        elif natural and not dealer_natural:
            payout, result = checked_payout(hand["stakeEcy"], 22_500), "BLACKJACK"
        elif dealer_value > 21 or value > dealer_value:
            payout, result = hand["stakeEcy"] * 2, "WIN"
        elif value == dealer_value:
            payout, result = hand["stakeEcy"], "PUSH"
        else:
            payout, result = 0, "LOSE"
        gross += payout
        receipts.append({"hand": index, "value": value, "result": result, "grossPayoutEcy": payout})
    plan["state"] = "SETTLED"
    return {"dealer": dealer, "dealerValue": dealer_value, "hands": receipts, "grossPayoutEcy": gross}


def basic_strategy_action(plan):
    actions = blackjack_allowed_actions(plan)
    hand = plan["hands"][plan["activeHand"]]
    cards = hand["cards"]
    dealer_rank = card_rank(plan["dealer"][0])
    dealer = 11 if dealer_rank == "A" else 10 if dealer_rank in {"J", "Q", "K"} else int(dealer_rank)
    ranks = [card_rank(c) for c in cards]
    pair = ranks[0] if len(ranks) == 2 and ranks[0] == ranks[1] else None
    if "SPLIT" in actions and pair in {"A", "8"}:
        return "SPLIT"
    value, soft = hand_value(cards)
    if "DOUBLE" in actions and value == 11:
        return "DOUBLE"
    if soft:
        if value >= 19 or (value == 18 and 2 <= dealer <= 8):
            return "STAND"
        return "HIT"
    if value >= 17 or (13 <= value <= 16 and 2 <= dealer <= 6) or (value == 12 and 4 <= dealer <= 6):
        return "STAND"
    return "HIT"


def simulate_blackjack(stake, rng):
    plan = new_blackjack_plan(stake, rng)
    player_natural = blackjack_natural(plan["hands"][0]["cards"])
    dealer_natural = blackjack_natural(plan["dealer"])
    if player_natural or dealer_natural:
        plan["state"] = "DEALER_TURN"
    while plan["state"] == "PLAYER_TURN":
        apply_blackjack_action(plan, basic_strategy_action(plan))
    result = settle_blackjack_plan(plan)
    total_stake = sum(hand["stakeEcy"] for hand in plan["hands"])
    return total_stake, result["grossPayoutEcy"]

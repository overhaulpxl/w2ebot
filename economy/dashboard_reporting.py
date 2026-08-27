"""Authoritative, integer-safe Phase 9B economy dashboard read models."""

from __future__ import annotations

from datetime import timedelta
import json

from .dashboard_security import DashboardSecurityError, iso, utc_now
from .constants import ECONOMY_FEE_BPS
from .notification_routing import list_notification_routes
from .phase9b_schema import phase9b_capability
from .reporting_taxonomy import classify_operation


def _decimal(value):
    return str(int(value or 0))


async def _table_exists(db, table):
    async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=$1", table) as cursor:
        return bool(await cursor.fetchone())


async def _rows(db, sql, params=()):
    async with db.execute(sql, params) as cursor:
        return await cursor.fetchall()


async def _require(db):
    if not await phase9b_capability(db):
        raise DashboardSecurityError("capability_unavailable", 503)


def _envelope(guild_id, moment, data, *, source_as_of=None, warnings=None, freshness="FRESH"):
    return {"schemaVersion": "1", "guildId": str(guild_id), "asOf": iso(moment),
            "sourceAsOf": source_as_of or iso(moment), "freshness": freshness,
            "warnings": sorted(set(warnings or [])), "data": data}


async def supply_report(db, guild_id, *, now=None):
    await _require(db)
    moment = now or utc_now()
    guild = str(guild_id)
    wallet_rows = await _rows(db, "SELECT etmBalance,ecyBalance FROM EconomyWallet WHERE guildId=$1", guild)
    account_rows = await _rows(db, "SELECT accountCode,currency,accountClass,balance FROM EconomySystemAccount WHERE guildId=$1", guild,)
    totals = {"ETM": 0, "ECY": 0}
    for etm, ecy in wallet_rows:
        totals["ETM"] += int(etm); totals["ECY"] += int(ecy)
    accounts = []
    mint = {"ETM": 0, "ECY": 0}; burn = {"ETM": 0, "ECY": 0}
    for code, currency, account_class, balance in account_rows:
        totals[currency] += int(balance)
        accounts.append({"accountCode": code, "currency": currency, "accountClass": account_class,
                         "balance": _decimal(balance)})
    ledger_rows = await _rows(
        db, "SELECT l.currency,l.accountId,l.amount FROM EconomyLedger l JOIN EconomyTransaction t "
            "ON t.transactionId=l.transactionId WHERE t.guildId=$1 AND t.status='COMMITTED' "
            "AND l.accountKind='SYSTEM'", (guild,),
    )
    classes = {row[0]: row[2] for row in account_rows}
    for currency, account_id, amount in ledger_rows:
        if classes.get(account_id) == "ISSUANCE":
            mint[currency] += max(0, -int(amount))
        if classes.get(account_id) == "BURN":
            burn[currency] += max(0, int(amount))
    distribution = await balance_distribution(db, guild)
    data = {"walletCount": _decimal(len(wallet_rows)), "supply": {key: _decimal(value) for key, value in totals.items()},
            "minted": {key: _decimal(value) for key, value in mint.items()},
            "burned": {key: _decimal(value) for key, value in burn.items()},
            "systemAccounts": accounts, "balanceDistribution": distribution}
    return _envelope(guild, moment, data)


async def balance_distribution(db, guild_id):
    rows = await _rows(db, "SELECT ecyBalance FROM EconomyWallet WHERE guildId=$1 ORDER BY ecyBalance", (str(guild_id),))
    values = [int(row[0]) for row in rows]
    positive = [value for value in values if value > 0]
    def percentile(percent):
        if not values:
            return 0
        index = ((len(values) - 1) * percent) // 100
        return values[index]
    median = 0
    if values:
        middle = len(values) // 2
        median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) // 2
    return {"zeroCount": _decimal(len(values) - len(positive)), "positiveCount": _decimal(len(positive)),
            "min": _decimal(values[0] if values else 0), "p25": _decimal(percentile(25)),
            "median": _decimal(median), "p75": _decimal(percentile(75)), "p90": _decimal(percentile(90)),
            "p99": _decimal(percentile(99)), "max": _decimal(values[-1] if values else 0)}


async def flows_report(db, guild_id, *, window_days, now=None):
    await _require(db)
    if int(window_days) not in {7, 30}:
        raise DashboardSecurityError("invalid_request", 400)
    moment = now or utc_now(); start = moment - timedelta(days=int(window_days)); guild = str(guild_id)
    rows = await _rows(
        db, "SELECT t.transactionId,t.operation,l.currency,l.amount,l.accountKind FROM EconomyTransaction t "
            "JOIN EconomyLedger l ON l.transactionId=t.transactionId WHERE t.guildId=$1 AND t.status='COMMITTED' "
            "AND t.committedAt>=$1 AND t.committedAt<$2", (guild, iso(start), iso(moment)),
    )
    groups = {}; unclassified = set(); transaction_debits = {}
    for transaction_id, operation, currency, amount, account_kind in rows:
        category = classify_operation(operation)
        if category == "UNCLASSIFIED":
            unclassified.add(str(operation))
        key = (category, currency)
        item = groups.setdefault(key, {"debits": 0, "credits": 0, "entries": 0})
        value = int(amount); item["entries"] += 1
        if account_kind == "USER":
            item["credits" if value > 0 else "debits"] += abs(value)
            if value < 0:
                transaction_debits[(transaction_id, str(operation), currency)] = (
                    transaction_debits.get((transaction_id, str(operation), currency), 0) + abs(value)
    fees = {"TRANSFER": {"ETM": 0}, "EXCHANGE": {"ETM": 0},
            "MARKETPLACE": {"ETM": 0}, "CRYPTO": {"ECY": 0}}
    for (_, operation, currency), amount in transaction_debits.items():
        if operation == "PLAYER_TRANSFER_ETM" and currency == "ETM":
            fees["TRANSFER"]["ETM"] += amount * ECONOMY_FEE_BPS // 10_000
        elif operation == "ETM_TO_ECY_EXCHANGE" and currency == "ETM":
            fees["EXCHANGE"]["ETM"] += amount * ECONOMY_FEE_BPS // 10_000
    fee_specs = (
        ("MarketplaceSale", "feeEtm", "ETM", "MARKETPLACE"),
        ("CryptoTrade", "feeEcy", "ECY", "CRYPTO"),
    )
    for table, column, currency, category in fee_specs:
        if not await _table_exists(db, table):
            continue
        columns = {row[1] for row in await _rows(db, f"PRAGMA table_info({table})")}
        time_column = "settledAt" if "settledAt" in columns else "createdAt"
        fee_rows = await _rows(
            db, f"SELECT {column} FROM {table} WHERE guildId=$1 AND status='COMMITTED' "
                f"AND {time_column}>=$1 AND {time_column}<$2", (guild, iso(start), iso(moment)),
        )
        fees[category][currency] += sum(int(row[0]) for row in fee_rows)
    data = {"windowDays": str(window_days), "windowStart": iso(start), "windowEnd": iso(moment),
            "flows": [{"category": key[0], "currency": key[1], **{name: _decimal(value) for name, value in item.items()}}
                      for key, item in sorted(groups.items())],
            "fees": [{"category": category, "currency": currency, "amount": _decimal(amount)}
                     for category, values in sorted(fees.items())
                     for currency, amount in sorted(values.items())]}
    warnings = [f"unclassified_operation:{name}" for name in sorted(unclassified)]
    return _envelope(guild, moment, data, warnings=warnings)


async def liabilities_report(db, guild_id, *, now=None):
    await _require(db); moment = now or utc_now(); guild = str(guild_id)
    specs = (
        ("marketplace", "MarketplaceEscrow", "remainingQuantity", "status", ("ACTIVE", "PARTIALLY_FILLED", "PAUSED", "REVIEW_REQUIRED", "CANCELLED", "EXPIRED")),
        ("casino", "CasinoBankrollReservation", "liabilityEcy", "status", ("ACTIVE", "REVIEW_REQUIRED")),
        ("options", "EternalOptionReservation", "liabilityEcy", "status", ("ACTIVE", "REVIEW_REQUIRED")),
    )
    result = {}; warnings = []
    for name, table, amount_column, status_column, statuses in specs:
        if not await _table_exists(db, table):
            result[name] = {"count": "0", "amount": "0", "available": False}; warnings.append(f"source_unavailable:{table}")
            continue
        columns = {row[1] for row in await _rows(db, f"PRAGMA table_info({table})")}
        guild_clause = "guildId=$1" if "guildId" in columns else "1=1"
        params = [guild] if "guildId" in columns else []
        where = guild_clause
        if status_column and statuses:
            where += f" AND {status_column} IN ({','.join('$1' for _ in statuses)})"; params.extend(statuses)
        rows = await _rows(db, f"SELECT {amount_column} FROM {table} WHERE {where}", tuple(params))
        result[name] = {"count": _decimal(len(rows)), "amount": _decimal(sum(int(row[0] or 0) for row in rows)), "available": True}
    if await _table_exists(db, "MiningPendingAsset") and await _table_exists(db, "MiningRigInstance"):
        rows = await _rows(
            db, "SELECT p.pendingUnits FROM MiningPendingAsset p JOIN MiningRigInstance r "
                "ON r.rigInstanceId=p.rigInstanceId WHERE r.guildId=$1", (guild,),
        )
        result["mining"] = {"count": _decimal(len(rows)),
                            "amount": _decimal(sum(int(row[0] or 0) for row in rows)), "available": True}
    else:
        result["mining"] = {"count": "0", "amount": "0", "available": False}
        warnings.append("source_unavailable:MiningPendingAsset")
    return _envelope(guild, moment, {"liabilities": result}, warnings=warnings,
                     freshness="STALE" if warnings else "FRESH")


async def domain_metrics(db, guild_id, domain, *, now=None):
    await _require(db); moment = now or utc_now(); guild = str(guild_id)
    tables = {
        "marketplace": (("MarketplaceListing", "status"),),
        "casino-options": (("CasinoSession", "status"), ("EternalOptionPosition", "status")),
        "giveaway": (("GiveawayV1", "status"),),
        "crypto-mining": (("CryptoTrade", "status"), ("MiningOperation", "status")),
    }
    sources = tables.get(domain)
    if not sources:
        return _envelope(guild, moment, {"domain": domain, "statuses": []}, warnings=["source_unavailable"], freshness="UNAVAILABLE")
    statuses = []
    warnings = []
    for table, status_column in sources:
        if not await _table_exists(db, table):
            warnings.append(f"source_unavailable:{table}")
            continue
        columns = {row[1] for row in await _rows(db, f"PRAGMA table_info({table})")}
        where, params = (" WHERE guildId=$1", (guild,)) if "guildId" in columns else ("", ())
        rows = await _rows(db, f"SELECT {status_column},COUNT(*) FROM {table}{where} GROUP BY {status_column}", params)
        statuses.extend({"source": table, "status": row[0], "count": _decimal(row[1])} for row in rows)
    freshness = "STALE" if warnings and statuses else ("UNAVAILABLE" if warnings else "FRESH")
    return _envelope(guild, moment, {"domain": domain, "statuses": statuses}, warnings=warnings, freshness=freshness)


async def recovery_report(db, guild_id, *, limit=50, now=None):
    await _require(db); moment = now or utc_now(); guild = str(guild_id)
    bounded = max(1, min(int(limit), 100))
    deliveries = await _rows(db, "SELECT deliveryId,category,status,lastFailureCode,createdAt FROM DashboardNotificationDelivery "
                            "WHERE guildId=$1 AND status IN ('FAILED','REVIEW_REQUIRED') ORDER BY createdAt DESC LIMIT $2", (guild, bounded))
    controls = await _rows(db, "SELECT domain,entityType,entityId,status,version,updatedAt FROM DashboardRecoveryControl "
                           "WHERE guildId=$1 AND status<>'RESOLVED' ORDER BY updatedAt DESC LIMIT $2", (guild, bounded))
    return _envelope(guild, moment, {"deliveries": [{"deliveryId": r[0], "category": r[1], "status": r[2], "failureCode": r[3], "createdAt": r[4]} for r in deliveries],
                                      "reviews": [{"domain": r[0], "entityType": r[1], "entityId": r[2], "status": r[3], "version": _decimal(r[4]), "updatedAt": r[5]} for r in controls]})


async def overview_report(db, guild_id, *, current_non_bot_user_ids=None, now=None):
    await _require(db); moment = now or utc_now(); guild = str(guild_id)
    ledger_rows = await _rows(
        db, "SELECT t.transactionId,l.currency,l.amount FROM EconomyTransaction t JOIN EconomyLedger l "
            "ON l.transactionId=t.transactionId WHERE t.guildId=$1 AND t.status='COMMITTED'", (guild,),
    )
    balances = {}
    for transaction_id, currency, amount in ledger_rows:
        key = (transaction_id, currency)
        balances[key] = balances.get(key, 0) + int(amount)
    unbalanced = [key for key, amount in balances.items() if amount]
    reviews = await _rows(db, "SELECT COUNT(*) FROM DashboardNotificationDelivery WHERE guildId=$1 AND status='REVIEW_REQUIRED'", (guild,))
    routes = await list_notification_routes(db, guild)
    missing = sum(1 for route in routes if route["status"] == "NOT_CONFIGURED")
    window_start = iso(moment - timedelta(days=30))
    economic_rows = await _rows(
        db, "SELECT DISTINCT l.userId FROM EconomyLedger l JOIN EconomyTransaction t "
            "ON t.transactionId=l.transactionId WHERE t.guildId=$1 AND t.status='COMMITTED' "
            "AND l.accountKind='USER' AND l.userId IS NOT NULL AND l.createdAt>=$1 AND l.createdAt<$2",
        (guild, window_start, iso(moment)),
    )
    approved_activity_types = (
        "DAILY_CLAIM", "WEEKLY_CLAIM", "WORK", "HUNT", "DUNGEON_COMPLETED",
        "BOSS_ATTACK", "BOSS_PARTICIPATION", "DAILY_QUEST_COMPLETED",
        "WEEKLY_QUEST_COMPLETED", "VOICE_ACTIVITY_30M",
    )
    activity_rows = await _rows(
        db, "SELECT DISTINCT userId FROM EconomyActivityEvent WHERE guildId=$1 "
            f"AND eventType IN ({','.join('$1' for _ in approved_activity_types)}) "
            "AND occurredAt>=$1 AND occurredAt<$2",
        (guild, *approved_activity_types, window_start, iso(moment)),
    )
    activity_users = {str(row[0]) for row in activity_rows}
    warnings = []
    if current_non_bot_user_ids is None:
        current_activity_count = 0
        warnings.append("discord_membership_unavailable")
    else:
        current_activity_count = len(activity_users.intersection({str(value) for value in current_non_bot_user_ids}))
    if unbalanced:
        health = "UNBALANCED"
    elif reviews[0][0] or missing:
        health = "NEEDS_ATTENTION"
    else:
        health = "HEALTHY"
    data = {"health": health, "unbalancedTransactions": _decimal(len(unbalanced)),
            "reviewRequiredDeliveries": _decimal(reviews[0][0]), "unconfiguredRoutes": _decimal(missing),
            "activeUsers30d": {"committedLedgerUsers": _decimal(len(economic_rows)),
                               "currentNonBotApprovedActivityUsers": _decimal(current_activity_count)}}
    return _envelope(guild, moment, data, warnings=warnings,
                     freshness="STALE" if warnings else "FRESH")

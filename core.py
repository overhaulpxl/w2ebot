import discord
import os
from google import genai
import asyncio
from discord import FFmpegPCMAudio
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import random
import sqlite3
import gtts
from aiohttp import web
import aiohttp
import io
import json
import re
import hmac
import hashlib
import unicodedata
from contextlib import asynccontextmanager

import math

from runtime_config import (
    DATABASE_PATH_STRING, STAGING_MODE, STARTUP_CONFIGURATION, command_sync_guild_id,
    DASHBOARD_PUBLIC_URL, DASHBOARD_INTERNAL_KEY_ID, DASHBOARD_INTERNAL_SIGNING_KEY,
    DASHBOARD_SESSION_KEY_ID, DASHBOARD_SESSION_HASH_KEY,
)

from economy.database import ensure_phase1_schema
from economy.constants import (
    ECONOMY_PHASE2_ENABLED, ECONOMY_PHASE3_ENABLED, ECONOMY_PHASE4_ENABLED, ECONOMY_PHASE5_ENABLED,
    ECONOMY_PHASE6_ENABLED, ECONOMY_V1_ENABLED,
    ECONOMY_PHASE7_ENABLED, ECONOMY_PHASE8_ENABLED,
)
from economy.profile import get_profile_snapshot
from economy.treasury import get_supply_report
from economy.dashboard_auth import (
    consume_csrf, create_oauth_attempt, establish_session, has_permission, issue_csrf,
    list_permissions, revoke_session, rotate_session, validate_session,
)
from economy.dashboard_operations import change_permission, revoke_dashboard_session
from economy.dashboard_security import (
    DashboardSecurityError, canonical_json, consume_internal_nonce, enforce_rate_limit,
    envelope_from_headers, payload_hash, record_security_event, sha256_text,
    verify_envelope_signature,
)
from economy.phase9a_schema import PHASE9A_SCHEMA_CHECKSUM, phase9a_capability

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logging.warning("Pillow not installed. Family tree/profile images will use text fallback.")


DB_PATH = DATABASE_PATH_STRING

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_API_KEY = os.getenv('DISCORD_TOKEN', 'MMM')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'MMM')
CONFIGURED_ALLOWED_SERVER_ID = int(os.getenv('ALLOWED_SERVER_ID', '887968847842402355'))
ALLOWED_SERVER_ID = command_sync_guild_id(CONFIGURED_ALLOWED_SERVER_ID)
BOT_PREFIX = os.getenv('BOT_PREFIX', 'w!')
DASHBOARD_TOKEN = os.getenv('DASHBOARD_TOKEN', '')
# Channel tempat bot auto-reply pakai AI tanpa perlu prefix. 0 = nonaktif.
AI_AUTO_REPLY_CHANNEL_ID = int(os.getenv('AI_AUTO_REPLY_CHANNEL_ID', '1341038015186862201'))
# Comma-separated origins yang boleh akses API (mis. web main way2eternal).
# Kosong = izinkan semua (dev only). Wajib diisi kalau web main di domain lain.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv('ALLOWED_ORIGINS', '').split(',') if o.strip()]

# genai Client
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)
READY_STARTUP_CALLBACKS = []
VOICE_STATE_CALLBACKS = []
READY_TASKS = {}
READY_ONCE_TASKS = set()
TREE_SYNC_DONE = False


def _schedule_ready_task(name, factory, *, once=False):
    """Schedule one on-ready task without duplicating it after reconnects."""
    key = str(name)
    existing = READY_TASKS.get(key)
    if existing and not existing.done():
        return existing
    if once and key in READY_ONCE_TASKS:
        return existing
    try:
        task = asyncio.create_task(factory())
    except Exception as exc:
        logging.error("Failed to schedule ready task name=%s exception=%s", key, type(exc).__name__)
        return None
    READY_TASKS[key] = task
    if once:
        READY_ONCE_TASKS.add(key)

    def _report_ready_task(done_task):
        if done_task.cancelled():
            return
        try:
            error = done_task.exception()
        except Exception:
            error = None
        if error:
            READY_ONCE_TASKS.discard(key)
            logging.error("Ready task failed name=%s exception=%s", key, type(error).__name__)

    task.add_done_callback(_report_ready_task)
    return task


def register_ready_startup_task(callback):
    if callback not in READY_STARTUP_CALLBACKS:
        READY_STARTUP_CALLBACKS.append(callback)


def register_voice_state_callback(callback):
    if callback not in VOICE_STATE_CALLBACKS:
        VOICE_STATE_CALLBACKS.append(callback)

# Waktu start proses (untuk uptime di /api/bot/stats).
BOT_START_TIME = datetime.utcnow()




voice_join_times = {} # user_id -> datetime
chat_sessions = {} # user_id -> chat session
rob_cooldowns = {}  # (attacker_id, target_id) -> datetime
rps_pending = {}    # challenger_id -> {target, bet, choice}
quest_progress = {} # user_id -> {quest_id: progress}
work_cooldowns = {} # user_id -> datetime
boss_cooldowns = {} # user_id -> datetime

# ── File paths ────────────────────────────────────────────────────────────────
FAMILY_FILE    = 'family.json'
ITEMS_FILE     = 'items.json'
WEEKLY_FILE    = 'weekly.json'
QUESTS_FILE    = 'quests.json'
CUSTOM_ROLES_FILE = 'custom_roles.json'
MARKET_FILE       = 'market.json'
PORTFOLIO_FILE    = 'portfolio.json'
PERSONAS_FILE     = 'personas.json'
BOSS_FILE         = 'boss.json'
RIGS_FILE         = 'rigs.json'
TREASURY_FILE     = 'treasury.json'
BINOMO_FILE       = 'binomo.json'

# ⬇ Set this to the channel ID of your #custom-role channel
CUSTOM_ROLE_CHANNEL_ID = 0  # TODO: ganti dengan ID channel #custom-role kamu

# ── JSON helpers ─────────────────────────────────────────────────────────────
import sqlite3
import os

def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS json_store (filename TEXT PRIMARY KEY, content TEXT)")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS DiscordStat (
            id TEXT PRIMARY KEY,
            displayName TEXT,
            coins INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            lastDaily TEXT,
            updatedAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS ChatMemory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            content TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Reminder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            channel_id TEXT,
            message TEXT,
            fire_at TEXT,
            created_at TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Giveaway (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            message_id TEXT,
            prize TEXT,
            host_id TEXT,
            end_at TEXT,
            ended INTEGER DEFAULT 0
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS AuditLog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            action TEXT,
            target_id TEXT,
            detail TEXT,
            source TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS dealAuditLogConfig (
            guildId TEXT PRIMARY KEY,
            channelId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS DealConfig (
            guildId TEXT PRIMARY KEY,
            middlemanRoleId TEXT,
            ownerRoleId TEXT,
            dealLogChannelId TEXT,
            vouchChannelId TEXT,
            dealStaffRoleIds TEXT DEFAULT '[]',
            allowedTicketCategoryIds TEXT DEFAULT '[]',
            dealIdPrefix TEXT DEFAULT 'MM',
            pingCooldownSeconds INTEGER DEFAULT 3600,
            reminderEnabled INTEGER DEFAULT 0,
            reminderIntervals TEXT DEFAULT '{}',
            requirePaymentProof INTEGER DEFAULT 0,
            requireTransferProof INTEGER DEFAULT 0,
            allowUserCancelRequest INTEGER DEFAULT 1,
            autoTimeoutEnabled INTEGER DEFAULT 0,
            trustedRoleThreshold INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        )
    ''')
    existing_config_cols = {row[1] for row in conn.execute("PRAGMA table_info(DealConfig)").fetchall()}
    if "ownerRoleId" not in existing_config_cols:
        conn.execute("ALTER TABLE DealConfig ADD COLUMN ownerRoleId TEXT")
    if "vouchChannelId" not in existing_config_cols:
        conn.execute("ALTER TABLE DealConfig ADD COLUMN vouchChannelId TEXT")
    config_columns_to_add = {
        "dealStaffRoleIds": "TEXT DEFAULT '[]'",
        "pingCooldownSeconds": "INTEGER DEFAULT 3600",
        "reminderEnabled": "INTEGER DEFAULT 0",
        "reminderIntervals": "TEXT DEFAULT '{}'",
        "requirePaymentProof": "INTEGER DEFAULT 0",
        "requireTransferProof": "INTEGER DEFAULT 0",
        "allowUserCancelRequest": "INTEGER DEFAULT 1",
        "autoTimeoutEnabled": "INTEGER DEFAULT 0",
        "trustedRoleThreshold": "INTEGER DEFAULT 0",
    }
    for col, ddl in config_columns_to_add.items():
        if col not in existing_config_cols:
            conn.execute(f"ALTER TABLE DealConfig ADD COLUMN {col} {ddl}")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Deal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dealId TEXT,
            guildId TEXT NOT NULL,
            ticketChannelId TEXT NOT NULL,
            createdById TEXT NOT NULL,
            buyerId TEXT NOT NULL,
            sellerId TEXT NOT NULL,
            middlemanId TEXT NOT NULL,
            paymentPenjual TEXT,
            paymentPembeli TEXT,
            nominalItem INTEGER,
            feeType TEXT,
            mmFee INTEGER,
            buyerPays INTEGER,
            sellerReceives INTEGER,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'Menunggu Form',
            warningMessageId TEXT,
            summaryMessageId TEXT,
            fundsReceivedStageMessageId TEXT,
            buyerConfirmStageMessageId TEXT,
            payoutStageMessageId TEXT,
            doneStageMessageId TEXT,
            completedSummaryMessageId TEXT,
            vouchProgressMessageId TEXT,
            cancelledById TEXT,
            cancelledAt TEXT,
            cancelReason TEXT,
            disputedById TEXT,
            disputedAt TEXT,
            disputeReason TEXT,
            disputeProofUrl TEXT,
            disputePreviousStatus TEXT,
            statusBeforeDispute TEXT,
            disputeResolvedById TEXT,
            disputeResolvedAt TEXT,
            disputeResolution TEXT,
            paymentProofUrl TEXT,
            paymentProofNotes TEXT,
            paymentProofMessageId TEXT,
            paymentProofChannelId TEXT,
            paymentProofSubmittedById TEXT,
            paymentProofSubmittedAt TEXT,
            paymentProofInvalidatedAt TEXT,
            paymentProofInvalidatedById TEXT,
            paymentProofInvalidationReason TEXT,
            paymentProofConfirmationMessageId TEXT,
            transferProofUrl TEXT,
            transferProofNotes TEXT,
            transferProofMessageId TEXT,
            transferProofChannelId TEXT,
            transferProofSubmittedById TEXT,
            transferProofSubmittedAt TEXT,
            sellerPayoutPlatform TEXT,
            sellerPayoutAccount TEXT,
            sellerPayoutName TEXT,
            sellerPayoutSubmittedById TEXT,
            sellerPayoutSubmittedAt TEXT,
            formSubmittedById TEXT,
            formSubmittedAt TEXT,
            paymentInstructionOwnerId TEXT,
            paymentInstructionMessageId TEXT,
            paymentInstructionSentAt TEXT,
            paymentInstructionPayloadHash TEXT,
            fundsReceivedNotes TEXT,
            fundsReceivedById TEXT,
            fundsReceivedAt TEXT,
            itemSentById TEXT,
            itemSentAt TEXT,
            buyerConfirmedById TEXT,
            buyerConfirmedAt TEXT,
            buyerConfirmationSource TEXT,
            completedById TEXT,
            completedAt TEXT,
            isVouchEligible INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT,
            UNIQUE(guildId, dealId)
        )
    ''')
    existing_deal_cols = {row[1] for row in conn.execute("PRAGMA table_info(Deal)").fetchall()}
    required_deal_columns = {"id", "guildId", "dealId", "ticketChannelId"}
    if not required_deal_columns.issubset(existing_deal_cols):
        logging.critical("Deal database schema is incompatible and requires manual repair.")
        raise RuntimeError("Deal database schema is incompatible and requires manual repair.")
    deal_columns_to_add = {
        "paymentProofUrl": "TEXT",
        "paymentProofNotes": "TEXT",
        "paymentProofMessageId": "TEXT",
        "paymentProofChannelId": "TEXT",
        "paymentProofSubmittedById": "TEXT",
        "paymentProofSubmittedAt": "TEXT",
        "paymentProofInvalidatedAt": "TEXT",
        "paymentProofInvalidatedById": "TEXT",
        "paymentProofInvalidationReason": "TEXT",
        "paymentProofConfirmationMessageId": "TEXT",
        "fundsReceivedStageMessageId": "TEXT",
        "buyerConfirmStageMessageId": "TEXT",
        "payoutStageMessageId": "TEXT",
        "doneStageMessageId": "TEXT",
        "completedSummaryMessageId": "TEXT",
        "transferProofUrl": "TEXT",
        "transferProofNotes": "TEXT",
        "transferProofMessageId": "TEXT",
        "transferProofChannelId": "TEXT",
        "transferProofSubmittedById": "TEXT",
        "transferProofSubmittedAt": "TEXT",
        "sellerPayoutPlatform": "TEXT",
        "sellerPayoutAccount": "TEXT",
        "sellerPayoutName": "TEXT",
        "sellerPayoutSubmittedById": "TEXT",
        "sellerPayoutSubmittedAt": "TEXT",
        "formSubmittedById": "TEXT",
        "formSubmittedAt": "TEXT",
        "paymentInstructionOwnerId": "TEXT",
        "paymentInstructionMessageId": "TEXT",
        "paymentInstructionSentAt": "TEXT",
        "paymentInstructionPayloadHash": "TEXT",
        "fundsReceivedNotes": "TEXT",
        "fundsReceivedById": "TEXT",
        "fundsReceivedAt": "TEXT",
        "itemSentById": "TEXT",
        "itemSentAt": "TEXT",
        "buyerConfirmedById": "TEXT",
        "buyerConfirmedAt": "TEXT",
        "buyerConfirmationSource": "TEXT",
        "completedById": "TEXT",
        "completedAt": "TEXT",
        "isVouchEligible": "INTEGER DEFAULT 0",
        "vouchProgressMessageId": "TEXT",
        "disputedById": "TEXT",
        "disputedAt": "TEXT",
        "disputeReason": "TEXT",
        "disputeProofUrl": "TEXT",
        "disputePreviousStatus": "TEXT",
        "statusBeforeDispute": "TEXT",
        "disputeResolvedById": "TEXT",
        "disputeResolvedAt": "TEXT",
        "disputeResolution": "TEXT",
    }
    for col, ddl in deal_columns_to_add.items():
        if col not in existing_deal_cols:
            conn.execute(f"ALTER TABLE Deal ADD COLUMN {col} {ddl}")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS DealLog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            dealId TEXT,
            action TEXT,
            actorId TEXT,
            oldValue TEXT,
            newValue TEXT,
            reason TEXT,
            createdAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS dealPaymentProfiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT NOT NULL,
            userId TEXT NOT NULL,
            title TEXT,
            paymentText TEXT,
            qrisNote TEXT,
            note TEXT,
            footerText TEXT,
            imageUrl TEXT,
            imageFilename TEXT,
            enabled INTEGER DEFAULT 1,
            createdAt TEXT,
            updatedAt TEXT,
            UNIQUE(guildId, userId)
        )
    ''')
    existing_payment_profile_cols = {row[1] for row in conn.execute("PRAGMA table_info(dealPaymentProfiles)").fetchall()}
    payment_profile_columns_to_add = {
        "title": "TEXT",
        "paymentText": "TEXT",
        "qrisNote": "TEXT",
        "note": "TEXT",
        "footerText": "TEXT",
        "imageUrl": "TEXT",
        "imageFilename": "TEXT",
        "enabled": "INTEGER DEFAULT 1",
        "createdAt": "TEXT",
        "updatedAt": "TEXT",
    }
    for col, ddl in payment_profile_columns_to_add.items():
        if col not in existing_payment_profile_cols:
            conn.execute(f"ALTER TABLE dealPaymentProfiles ADD COLUMN {col} {ddl}")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Vouch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            dealId TEXT,
            reviewerId TEXT,
            targetId TEXT,
            reviewerRole TEXT,
            targetRole TEXT,
            rating INTEGER,
            review TEXT,
            proofUrl TEXT,
            verifiedDeal INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            removedBy TEXT,
            removeReason TEXT,
            createdAt TEXT,
            updatedAt TEXT,
            UNIQUE(guildId, dealId, reviewerId, targetId)
        )
    ''')
    existing_vouch_cols = {row[1] for row in conn.execute("PRAGMA table_info(Vouch)").fetchall()}
    vouch_columns_to_add = {
        "vouchType": "TEXT",
        "approvalStatus": "TEXT",
        "proofCount": "INTEGER DEFAULT 0",
        "proofData": "TEXT",
        "proofSubmittedAt": "TEXT",
        "approvedById": "TEXT",
        "approvedAt": "TEXT",
        "rejectedById": "TEXT",
        "rejectedAt": "TEXT",
        "rejectionReason": "TEXT",
        "context": "TEXT",
        "staffNotes": "TEXT",
        "targetRaw": "TEXT",
        "targetResolved": "INTEGER DEFAULT 1",
    }
    for col, ddl in vouch_columns_to_add.items():
        if col not in existing_vouch_cols:
            conn.execute(f"ALTER TABLE Vouch ADD COLUMN {col} {ddl}")
    conn.execute("UPDATE Vouch SET vouchType='verified_deal' WHERE vouchType IS NULL")
    conn.execute("UPDATE Vouch SET approvalStatus=CASE WHEN status='removed' THEN 'removed' ELSE 'verified' END WHERE approvalStatus IS NULL")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS DealNote (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            dealId TEXT,
            actorId TEXT,
            note TEXT,
            createdAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS DealReminderLog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            dealId TEXT,
            reminderType TEXT,
            sentAt TEXT,
            UNIQUE(guildId, dealId, reminderType)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS dealArchives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            dealId TEXT,
            channelId TEXT,
            buyerId TEXT,
            sellerId TEXT,
            middlemanId TEXT,
            finalStatus TEXT,
            paymentProofSubmitted INTEGER DEFAULT 0,
            transferProofSubmitted INTEGER DEFAULT 0,
            vouchEligible INTEGER DEFAULT 0,
            disputeOpened INTEGER DEFAULT 0,
            disputeResolved INTEGER DEFAULT 0,
            cancelled INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            finalActionById TEXT,
            cancelledById TEXT,
            completedById TEXT,
            disputeOpenedById TEXT,
            disputeResolvedById TEXT,
            safeReason TEXT,
            safeResolution TEXT,
            createdAt TEXT,
            finalizedAt TEXT,
            archivedAt TEXT,
            UNIQUE(guildId, dealId)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS dealPanels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            panelType TEXT,
            channelId TEXT,
            messageId TEXT,
            enabled INTEGER DEFAULT 0,
            lastPayloadHash TEXT,
            createdAt TEXT,
            updatedAt TEXT,
            UNIQUE(guildId, panelType)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS dealPanelEvents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            panelType TEXT,
            eventType TEXT,
            eventKey TEXT,
            messageId TEXT,
            channelId TEXT,
            createdAt TEXT,
            UNIQUE(guildId, panelType, eventKey)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS middlemanStatus (
            guildId TEXT,
            userId TEXT,
            status TEXT DEFAULT 'offline',
            note TEXT,
            updatedAt TEXT,
            updatedById TEXT,
            createdAt TEXT,
            PRIMARY KEY (guildId, userId)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS rateLimitEvents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            userId TEXT,
            actionType TEXT,
            targetId TEXT,
            eventKey TEXT,
            createdAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS VouchReport (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            vouchId INTEGER,
            reporterId TEXT,
            reason TEXT,
            proofUrl TEXT,
            status TEXT DEFAULT 'open',
            handledBy TEXT,
            handledAt TEXT,
            createdAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS manualVouchReviewConfig (
            guildId TEXT PRIMARY KEY,
            reviewChannelId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS manualVouchPanelConfig (
            guildId TEXT PRIMARY KEY,
            channelId TEXT,
            messageId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scammerReports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guildId TEXT,
            reporterId TEXT,
            reportedUserId TEXT,
            reportedRaw TEXT,
            reportedResolved INTEGER DEFAULT 0,
            reason TEXT,
            chronology TEXT,
            nominalItem TEXT,
            notes TEXT,
            proofCount INTEGER DEFAULT 0,
            proofData TEXT,
            proofSubmittedAt TEXT,
            status TEXT DEFAULT 'pending',
            reviewMessageId TEXT,
            reviewChannelId TEXT,
            evidenceThreadId TEXT,
            reviewedById TEXT,
            rejectedById TEXT,
            rejectedAt TEXT,
            rejectionReason TEXT,
            resolvedById TEXT,
            resolvedAt TEXT,
            resolution TEXT,
            staffNotes TEXT,
            createdAt TEXT,
            updatedAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scamReportReviewConfig (
            guildId TEXT PRIMARY KEY,
            reviewChannelId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scamReportPanelConfig (
            guildId TEXT PRIMARY KEY,
            channelId TEXT,
            messageId TEXT,
            enabled INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS trustModerationStatus (
            guildId TEXT,
            userId TEXT,
            status TEXT DEFAULT 'clear',
            reason TEXT,
            sourceType TEXT,
            sourceId TEXT,
            updatedById TEXT,
            updatedAt TEXT,
            createdAt TEXT,
            PRIMARY KEY (guildId, userId)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS UserReputation (
            guildId TEXT,
            userId TEXT,
            totalVouches INTEGER DEFAULT 0,
            verifiedVouches INTEGER DEFAULT 0,
            verifiedDealVouches INTEGER DEFAULT 0,
            manualApprovedVouches INTEGER DEFAULT 0,
            averageRating REAL DEFAULT 0,
            trustScore REAL DEFAULT 0,
            buyerVouches INTEGER DEFAULT 0,
            sellerVouches INTEGER DEFAULT 0,
            middlemanVouches INTEGER DEFAULT 0,
            removedVouches INTEGER DEFAULT 0,
            reports INTEGER DEFAULT 0,
            trustLevel TEXT DEFAULT 'New User',
            updatedAt TEXT,
            PRIMARY KEY (guildId, userId)
        )
    ''')
    existing_rep_cols = {row[1] for row in conn.execute("PRAGMA table_info(UserReputation)").fetchall()}
    if "verifiedDealVouches" not in existing_rep_cols:
        conn.execute("ALTER TABLE UserReputation ADD COLUMN verifiedDealVouches INTEGER DEFAULT 0")
    if "manualApprovedVouches" not in existing_rep_cols:
        conn.execute("ALTER TABLE UserReputation ADD COLUMN manualApprovedVouches INTEGER DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_channel_status ON Deal(ticketChannelId, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_log_deal ON DealLog(guildId, dealId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vouch_deal ON Vouch(guildId, dealId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_note_deal ON DealNote(guildId, dealId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_reminder_due ON DealReminderLog(guildId, dealId, reminderType)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_archive_status ON dealArchives(guildId, finalStatus)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_archive_buyer ON dealArchives(guildId, buyerId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_archive_seller ON dealArchives(guildId, sellerId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_archive_middleman ON dealArchives(guildId, middlemanId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_archive_archived ON dealArchives(guildId, archivedAt)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_panels_type ON dealPanels(guildId, panelType)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_panel_events_type ON dealPanelEvents(guildId, panelType)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_panel_events_created ON dealPanelEvents(createdAt)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_payment_profiles_guild ON dealPaymentProfiles(guildId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_payment_profiles_user ON dealPaymentProfiles(userId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_middleman_status_status ON middlemanStatus(guildId, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limit_events_lookup ON rateLimitEvents(guildId, userId, actionType, createdAt)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limit_events_key ON rateLimitEvents(guildId, eventKey, createdAt)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vouch_target ON Vouch(guildId, targetId, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vouch_approval ON Vouch(guildId, approvalStatus, vouchType)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vouch_report_vouch ON VouchReport(guildId, vouchId, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scam_report_status ON scammerReports(guildId, status, reportedUserId)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trust_moderation_status ON trustModerationStatus(guildId, status)")
    # Economy V1 foundation creates only empty, additive tables. It does not
    # migrate DiscordStat/json_store or enable Phase 1/2 wallet mutations.
    ensure_phase1_schema(conn)
    conn.commit()
    conn.close()

_init_db()

import aiosqlite
import asyncio
from math import floor, sqrt
import json
import logging
from datetime import datetime

_json_cache = {}

async def load_json(filepath):
    basename = os.path.basename(filepath)
    if basename in _json_cache:
        return _json_cache[basename]
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT content FROM json_store WHERE filename=?", (basename,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    _json_cache[basename] = data
                    return data
    except Exception as e:
        logging.error("DB Load Error exception=%s", type(e).__name__)
    _json_cache[basename] = {}
    return {}

async def save_json(filepath, data):
    basename = os.path.basename(filepath)
    _json_cache[basename] = data
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO json_store (filename, content) VALUES (?, ?)", (basename, json.dumps(data, ensure_ascii=False)))
            await db.commit()
    except Exception as e:
        logging.error("DB Save Error exception=%s", type(e).__name__)

async def get_discord_stat(uid):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT coins, xp, level, lastDaily FROM DiscordStat WHERE id=?", (str(uid),)) as cursor:
                row = await cursor.fetchone()
                if row:
                    coins, xp, level, lastDaily = row[0], row[1], row[2], row[3]
                    
                    # O(1) Level Up Math
                    if xp >= level * 100:
                        a = 50
                        b = 100 * level - 50
                        c = -xp
                        discriminant = b**2 - 4*a*c
                        if discriminant > 0:
                            n = floor((-b + sqrt(discriminant)) / (2*a))
                            if n > 0:
                                xp_consumed = 100 * n * level + 50 * n * (n - 1)
                                old_level = level
                                level += n
                                xp -= int(xp_consumed)
                                await db.execute("UPDATE DiscordStat SET xp=?, level=? WHERE id=?", (xp, level, str(uid)))
                                await db.commit()
                                logging.info(f"[LEVELUP] uid={uid} naik level {old_level} -> {level} (sisa XP {xp})")
                    return {'coins': coins, 'xp': xp, 'level': level, 'lastDaily': lastDaily}
    except Exception as e:
        logging.error("DB Error get exception=%s", type(e).__name__)
    return {'coins': 0, 'xp': 0, 'level': 1, 'lastDaily': ''}

async def update_discord_stat(uid, display_name, coins, xp, level, last_daily):
    if xp >= level * 100:
        a = 50
        b = 100 * level - 50
        c = -xp
        discriminant = b**2 - 4*a*c
        if discriminant > 0:
            n = floor((-b + sqrt(discriminant)) / (2*a))
            if n > 0:
                xp_consumed = 100 * n * level + 50 * n * (n - 1)
                level += n
                xp -= int(xp_consumed)
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            now = datetime.utcnow().isoformat() + "Z"
            await db.execute("""
                INSERT INTO DiscordStat (id, displayName, coins, xp, level, lastDaily, updatedAt) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET 
                displayName=excluded.displayName,
                coins=excluded.coins,
                xp=excluded.xp,
                level=excluded.level,
                lastDaily=excluded.lastDaily,
                updatedAt=excluded.updatedAt
            """, (str(uid), display_name, coins, xp, level, last_daily, now))
            await db.commit()
    except Exception as e:
        logging.error("DB Error update exception=%s", type(e).__name__)


async def adjust_coins(uid, delta, display_name=None):
    # Atomic coin delta — avoids the read-modify-write race where two concurrent
    # commands read the same balance and the last writer wins. Clamps at 0.
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO DiscordStat (id, displayName, coins, updatedAt) VALUES (?, ?, MAX(0, ?), ?) "
                "ON CONFLICT(id) DO UPDATE SET coins = MAX(0, coins + ?), "
                "displayName = COALESCE(?, displayName), updatedAt = ?",
                (str(uid), display_name or str(uid), delta, now, delta, display_name, now))
            await db.commit()
            async with db.execute("SELECT coins FROM DiscordStat WHERE id=?", (str(uid),)) as c:
                row = await c.fetchone()
            saldo = row[0] if row else '?'
        arah = '+' if delta >= 0 else ''
        logging.info(f"[ECONOMY] {display_name or uid} ({uid}) koin {arah}{delta} -> saldo {saldo}")
    except Exception as e:
        logging.error("DB Error adjust_coins exception=%s", type(e).__name__)


# Alias semantik untuk kredit koin (biar maksud kode jelas).
async def add_coins(uid, amount, display_name=None):
    await adjust_coins(uid, amount, display_name)


async def try_spend(uid, amount, display_name=None):
    # Debit ATOMIK dengan syarat saldo cukup. Mengembalikan True kalau berhasil
    # memotong koin, False kalau saldo kurang / user belum punya row.
    # Ini menutup race "cek saldo lalu potong" yang bisa dipakai untuk double-spend
    # via prefix + slash bersamaan. Selalu pakai ini untuk pembelian/biaya.
    if amount is None or amount <= 0:
        return True
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "UPDATE DiscordStat SET coins = coins - ?, "
                "displayName = COALESCE(?, displayName), updatedAt = ? "
                "WHERE id = ? AND coins >= ?",
                (amount, display_name, now, str(uid), amount))
            await db.commit()
            ok = cur.rowcount > 0
            if ok:
                async with db.execute("SELECT coins FROM DiscordStat WHERE id=?", (str(uid),)) as c:
                    row = await c.fetchone()
                saldo = row[0] if row else '?'
                logging.info(f"[ECONOMY] {display_name or uid} ({uid}) bayar -{amount} -> saldo {saldo}")
            else:
                logging.info(f"[ECONOMY] {display_name or uid} ({uid}) GAGAL bayar {amount} (saldo kurang)")
            return ok
    except Exception as e:
        logging.error("DB Error try_spend exception=%s", type(e).__name__)
        return False


async def add_xp(uid, display_name, xp_delta):
    # Increment XP secara ATOMIK. Level-up di-resolve lazy oleh get_discord_stat
    # (rumus kuadratik di sana), jadi cukup tambah XP-nya saja.
    if not xp_delta:
        return
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO DiscordStat (id, displayName, xp, updatedAt) VALUES (?, ?, MAX(0, ?), ?) "
                "ON CONFLICT(id) DO UPDATE SET xp = MAX(0, xp + ?), "
                "displayName = COALESCE(?, displayName), updatedAt = ?",
                (str(uid), display_name or str(uid), xp_delta, now, xp_delta, display_name, now))
            await db.commit()
        logging.info(f"[XP] {display_name or uid} ({uid}) +{xp_delta} XP")
    except Exception as e:
        logging.error("DB Error add_xp exception=%s", type(e).__name__)


async def set_last_daily(uid, value, display_name=None):
    # Update kolom lastDaily TANPA menyentuh coins/xp (menghindari clobber saldo).
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO DiscordStat (id, displayName, lastDaily, updatedAt) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET lastDaily = ?, "
                "displayName = COALESCE(?, displayName), updatedAt = ?",
                (str(uid), display_name or str(uid), value, now, value, display_name, now))
            await db.commit()
    except Exception as e:
        logging.error("DB Error set_last_daily exception=%s", type(e).__name__)


# Fee transaksi kripto (2% dua arah). Dipakai /buycoin & /sellcoin.
CRYPTO_FEE_RATE = 0.02

# ── Konstanta Ekonomi (terpusat, gampang di-tweak) ────────────────────────────
ECON_WORK_MIN = 30
ECON_WORK_MAX = 120
ECON_WORK_XP = 10
ECON_VC_COINS_PER_10MIN = 30
ECON_VC_XP_PER_10MIN = 15
ECON_PRAY_NORMAL = 30
ECON_PRAY_JACKPOT = 500
ECON_BOSS_REWARD = 3000
ECON_SOFT_CAP = 500000          # Wallet di atas ini, reward non-gambling di-halve.
ECON_TRANSFER_TAX = 0.05        # 5% transfer/rob masuk treasury.
ECON_CHAT_XP = 5
ECON_CHAT_XP_COOLDOWN = 30      # detik

# Hashrate mining per koin per tier (unit/jam per rig). FLOAT — koin mahal yield kecil.
# Format: {symbol: {tier: (min, max)}}
MINING_RATES = {
    'ETHR': {'1': (0.005, 0.01), '2': (0.02, 0.06), '3': (0.08, 0.2)},
    'ORCL': {'1': (0.01, 0.04), '2': (0.05, 0.15), '3': (0.2, 0.5)},
    'MTR':  {'1': (0.1, 0.4), '2': (0.5, 1.5), '3': (2.0, 5.0)},
    'ECLP': {'1': (1.0, 3.0), '2': (4.0, 10.0), '3': (12.0, 30.0)},
    'ORBT': {'1': (1.0, 3.0), '2': (4.0, 10.0), '3': (12.0, 30.0)},
    'TRST': {'1': (1.0, 3.0), '2': (4.0, 10.0), '3': (12.0, 30.0)},
    'LUNA': {'1': (0.001, 0.003), '2': (0.005, 0.015), '3': (0.02, 0.05)},
}

# Harga rig per tier (sama untuk semua koin).
RIG_PRICES = {1: 10000, 2: 30000, 3: 80000}


async def add_treasury(amount):
    # Tambah saldo kas komunitas (treasury.json). Dipakai untuk menampung fee
    # transaksi kripto. Ini JSON blob (bukan kolom SQL), jadi tidak seatomik koin —
    # tapi risikonya rendah (fee kecil, bukan dompet user langsung).
    if not amount or amount <= 0:
        return
    try:
        treasury = await load_json(TREASURY_FILE)
        if not isinstance(treasury, dict):
            treasury = {}
        treasury['balance'] = treasury.get('balance', 0) + int(amount)
        await save_json(TREASURY_FILE, treasury)
        logging.info(f"[TREASURY] +{int(amount)} koin (fee) -> kas {treasury['balance']}")
    except Exception as e:
        logging.error("Error add_treasury exception=%s", type(e).__name__)


async def record_game(uid, game, won):
    # Catat statistik minigame per user. Disimpan di users.json[uid]['games'][game].
    # game: 'slot','blackjack','cf','rps','crash','tebak','gacha','box','hunt'
    # won: True/False/None (None = seri/netral, dihitung sebagai plays tapi bukan win/loss).
    try:
        users = await load_json('users.json')
        u = users.setdefault(str(uid), {})
        games = u.setdefault('games', {})
        g = games.setdefault(game, {'plays': 0, 'wins': 0, 'losses': 0})
        g['plays'] += 1
        if won is True:
            g['wins'] += 1
        elif won is False:
            g['losses'] += 1
        await save_json('users.json', users)
    except Exception as e:
        logging.error("record_game error exception=%s", type(e).__name__)


async def apply_soft_cap(uid, base_amount):
    # Soft cap: kalau wallet user > ECON_SOFT_CAP (500k), reward di-halve.
    # Dipakai untuk work/VC/pray/boss — BUKAN daily/weekly/gambling/crypto/transfer.
    try:
        stat = await get_discord_stat(str(uid))
        if stat['coins'] > ECON_SOFT_CAP:
            return max(1, base_amount // 2)
    except Exception:
        pass
    return base_amount


# Cooldown chat XP per user (in-memory, reset saat restart — acceptable).
chat_xp_cooldowns = {}  # uid -> datetime






# ── Shop items ────────────────────────────────────────────────────────────────
SHOP_ITEMS = {
    'shield':      {'name': '🛡️ Shield',      'price': 500,  'desc': 'Kebal dari curse & rob 1x'},
    'double_xp':   {'name': '⚡ Double XP',   'price': 800,  'desc': '2x XP selama 2 jam'},
    'lucky_charm': {'name': '🍀 Lucky Charm', 'price': 300,  'desc': '+20% slot winrate 1x'},
}

# ── Quest templates ──────────────────────────────────────────────────────────
QUEST_TEMPLATES = [
    {'id': 'send_msg',    'desc': 'Kirim 5 pesan',           'target': 5},
    {'id': 'do_coinflip', 'desc': 'Lakukan coin flip 1x',    'target': 1},
    {'id': 'open_box',    'desc': 'Buka 1 lootbox',          'target': 1},
    {'id': 'pray_user',   'desc': 'Doakan 1 member',         'target': 1},
    {'id': 'use_slot',    'desc': 'Main slot 1x',            'target': 1},
    {'id': 'check_top',   'desc': 'Lihat leaderboard',       'target': 1},
    {'id': 'give_coins',  'desc': 'Berikan koin ke seseorang','target': 1},
]






async def check_level_up(channel, user, xp_gained):
    uid = str(user.id)
    stat_before = await get_discord_stat(uid)
    level_before = stat_before['level']
    # Tambah XP atomik; level-up di-resolve oleh get_discord_stat (rumus kuadratik).
    await add_xp(uid, user.display_name, xp_gained)
    stat_after = await get_discord_stat(uid)
    if stat_after['level'] > level_before:
        await channel.send(f"Selamat {user.mention}, kamu naik ke **Level {stat_after['level']}**!")

async def check_toxicity(text):
    prompt = f"Evaluasi pesan berikut. Jika mengandung ujaran kebencian parah, rasisme, atau NSFW ekstrim, balas HANYA dengan kata 'TOXIC'. Jika aman, balas 'SAFE'.\nPesan: {text}"
    try:
        response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=prompt)
        return "TOXIC" in response.text.upper()
    except Exception:
        return False

# ── Quest helpers ─────────────────────────────────────────────────────────────
async def get_user_quests(uid):
    quests_data = await load_json(QUESTS_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    if uid not in quests_data or quests_data[uid].get('date') != today:
        chosen = random.sample(QUEST_TEMPLATES, min(3, len(QUEST_TEMPLATES)))
        quests_data[uid] = {
            'date': today,
            'quests': [{'id': q['id'], 'desc': q['desc'], 'target': q['target'], 'progress': 0, 'done': False} for q in chosen],
            'claimed': False
        }
        await save_json(QUESTS_FILE, quests_data)
    return quests_data[uid]

async def update_quest_progress(uid, quest_id, amount=1):
    quests_data = await load_json(QUESTS_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    if uid not in quests_data or quests_data[uid].get('date') != today:
        return
    for q in quests_data[uid]['quests']:
        if q['id'] == quest_id and not q['done']:
            q['progress'] = min(q['progress'] + amount, q['target'])
            if q['progress'] >= q['target']:
                q['done'] = True
    await save_json(QUESTS_FILE, quests_data)

import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_remote_url(url):
    # Guard SSRF: hanya izinkan http/https ke host publik. Blokir loopback,
    # private/link-local/reserved IP (mis. 169.254.169.254 metadata, 10.x, dst).
    # Dipakai sebelum bot mem-fetch URL yang dikontrol user (mis. /bg).
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


async def fetch_remote_image(url, max_bytes=8 * 1024 * 1024):
    # Fetch gambar dari URL user dengan proteksi SSRF + batas ukuran + cek tipe.
    # Mengembalikan PIL.Image atau None. Resolusi DNS divalidasi dulu lewat
    # is_safe_remote_url (best-effort; masih ada kemungkinan kecil TOCTOU tapi
    # jauh lebih aman daripada fetch mentah).
    if not await asyncio.to_thread(is_safe_remote_url, url):
        logging.warning(f"Blocked unsafe image URL: {url}")
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                ctype = resp.headers.get('Content-Type', '')
                if not ctype.startswith('image/'):
                    logging.warning(f"Rejected non-image content-type '{ctype}' from {url}")
                    return None
                data = await resp.content.read(max_bytes + 1)
                if len(data) > max_bytes:
                    logging.warning(f"Rejected oversized image from {url}")
                    return None
                return Image.open(io.BytesIO(data))
    except Exception as e:
        logging.error("Failed to fetch remote image exception=%s", type(e).__name__)
        return None


# ── Family tree image generator ───────────────────────────────────────────────
async def fetch_avatar(session, url, size=80):
    try:
        async with session.get(url) as resp:
            data = await resp.read()
            img = Image.open(io.BytesIO(data)).convert('RGBA').resize((size, size))
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            img.putalpha(mask)
            return img
    except Exception:
        img = Image.new('RGBA', (size, size), (80, 80, 100, 255))
        ImageDraw.Draw(img).ellipse((0, 0, size, size), fill=(100, 100, 120, 255))
        return img

async def generate_family_image(guild, uid):
    if not PILLOW_AVAILABLE:
        return None
    family = await load_json(FAMILY_FILE)
    udata = family.get(str(uid), {})
    partner_id = udata.get('partner')
    children_ids = udata.get('children', [])

    async def get_member(mid):
        m = guild.get_member(int(mid)) if mid else None
        return m

    user_m   = await get_member(uid)
    partner_m = await get_member(partner_id) if partner_id else None
    child_ms  = [await get_member(cid) for cid in children_ids[:6]]

    W = max(900, 200 + len(child_ms) * 140)
    H = 420
    img = Image.new('RGB', (W, H), (13, 13, 23))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_small = ImageFont.truetype("arial.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    AVSIZE = 80
    async with aiohttp.ClientSession() as session:
        # Main user avatar
        u_av_url = user_m.display_avatar.with_size(128).url if user_m else None
        u_av = await fetch_avatar(session, u_av_url) if u_av_url else None

        # Partner avatar
        p_av_url = partner_m.display_avatar.with_size(128).url if partner_m else None
        p_av = await fetch_avatar(session, p_av_url) if p_av_url else None

        # Children avatars
        c_avs = []
        for cm in child_ms:
            av_url = cm.display_avatar.with_size(128).url if cm else None
            c_avs.append(await fetch_avatar(session, av_url) if av_url else None)

    cx = W // 2

    # Draw user (left of center if partner exists, else center)
    if partner_m:
        u_x, p_x = cx - 100, cx + 20
    else:
        u_x = cx - 40

    u_y = 40
    if u_av:
        img.paste(u_av, (u_x, u_y), u_av)
    u_name = (user_m.display_name if user_m else "You")[:14]
    draw.text((u_x + AVSIZE//2, u_y + AVSIZE + 4), u_name, fill=(200, 200, 255), font=font, anchor="mm")

    # Draw heart between couple
    couple_mid_x = cx
    if partner_m:
        if p_av:
            img.paste(p_av, (p_x, u_y), p_av)
        p_name = (partner_m.display_name)[:14]
        draw.text((p_x + AVSIZE//2, u_y + AVSIZE + 4), p_name, fill=(255, 180, 220), font=font, anchor="mm")
        draw.text((cx - 10, u_y + 30), "💑", fill=(255, 100, 150), font=font)
        # Line down from couple
        line_top = u_y + AVSIZE + 20
        draw.line([(couple_mid_x, line_top), (couple_mid_x, line_top + 40)], fill=(100, 100, 150), width=2)
    else:
        line_top = u_y + AVSIZE + 20
        draw.line([(u_x + AVSIZE//2, line_top), (u_x + AVSIZE//2, line_top + 40)], fill=(100, 100, 150), width=2)
        couple_mid_x = u_x + AVSIZE//2

    # Draw children
    if child_ms:
        n = len(child_ms)
        child_y = 260
        spacing = min(140, (W - 60) // n)
        start_x = cx - (n * spacing) // 2

        draw.line([(start_x + 40, child_y - 30), (start_x + (n-1)*spacing + 40, child_y - 30)], fill=(100, 100, 150), width=2)

        for i, (cm, cav) in enumerate(zip(child_ms, c_avs)):
            cx_i = start_x + i * spacing
            draw.line([(cx_i + 40, child_y - 30), (cx_i + 40, child_y)], fill=(100, 100, 150), width=2)
            if cav:
                img.paste(cav, (cx_i, child_y), cav)
            c_name = (cm.display_name if cm else "?")[:12]
            draw.text((cx_i + 40, child_y + AVSIZE + 4), c_name, fill=(180, 255, 180), font=font_small, anchor="mm")

    # Title
    draw.text((W//2, 15), "👨‍👩‍👧‍👦  W2E Family", fill=(180, 160, 255), font=font, anchor="mm")
    draw.rounded_rectangle([(5, 5), (W-5, H-5)], radius=16, outline=(60, 60, 90), width=2)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

# ── Config & Helpers for Premium Profile Card ────────────────────────────────
W, H = 1600, 400

# Palette
BG            = (13, 15, 30)
ACCENT        = (99, 102, 241)   # indigo
ACCENT2       = (168, 85, 247)   # purple
GOLD          = (250, 189, 47)
CYAN          = (56, 189, 248)
GREEN         = (52, 211, 153)
WHITE         = (240, 242, 255)
MUTED         = (120, 128, 160)
STAT_BG       = (25, 28, 50)
XP_TRACK      = (30, 35, 68)
DIVIDER_C     = (60, 65, 100)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_BOLD_PATH   = os.path.join(FONT_DIR, "Poppins-Bold.ttf")
FONT_MED_PATH    = os.path.join(FONT_DIR, "Poppins-Medium.ttf")
FONT_REG_PATH    = os.path.join(FONT_DIR, "Poppins-Regular.ttf")
FONT_LIGHT_PATH  = os.path.join(FONT_DIR, "Poppins-Light.ttf")

def get_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype("arial.ttf", size)
        except Exception:
            return ImageFont.load_default()

def ensure_fonts():
    import urllib.request
    urls = {
        FONT_BOLD_PATH: "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf",
        FONT_MED_PATH: "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf",
        FONT_REG_PATH: "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf",
        FONT_LIGHT_PATH: "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Light.ttf"
    }
    if not os.path.exists(FONT_DIR):
        os.makedirs(FONT_DIR, exist_ok=True)
    for path, url in urls.items():
        if not os.path.exists(path):
            logging.info(f"Downloading font: {os.path.basename(path)}...")
            try:
                urllib.request.urlretrieve(url, path)
                logging.info(f"Downloaded {os.path.basename(path)} successfully.")
            except Exception as e:
                logging.error("Failed to download font path=%s exception=%s", os.path.basename(path), type(e).__name__)

# Pre-download fonts if possible on import/startup
try:
    ensure_fonts()
except Exception as e:
    logging.error("Error checking/downloading Poppins fonts on startup exception=%s", type(e).__name__)

def rounded_rectangle(draw, xy, radius, fill=None, outline=None, width=4):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill,
                            outline=outline, width=width)

def draw_glow_circle(img, center, radius, color, alpha_max=45):
    """Draw a soft radial glow"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for r in range(radius, 0, -6):
        a = int(alpha_max * (1 - r / radius) ** 2)
        draw.ellipse(
            [center[0] - r, center[1] - r, center[0] + r, center[1] + r],
            fill=(*color, a)
        )
    return Image.alpha_composite(img.convert("RGBA"), overlay)

def circle_avatar(av_source, size):
    """Crop avatar to a crisp circle, accepts path/BytesIO or PIL Image"""
    if isinstance(av_source, Image.Image):
        av = av_source.convert("RGBA").resize((size, size), Image.LANCZOS)
    else:
        av = Image.open(av_source).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    av.putalpha(mask)
    return av

def draw_xp_bar(draw, x, y, w, h, progress, radius=10):
    """Rounded XP progress bar with gradient feel"""
    rounded_rectangle(draw, [x, y, x + w, y + h], radius, fill=XP_TRACK)
    if progress > 0:
        fill_w = max(int(w * progress), radius * 2)
        for i in range(fill_w):
            t = i / max(fill_w - 1, 1)
            r = int(ACCENT[0] + (ACCENT2[0] - ACCENT[0]) * t)
            g = int(ACCENT[1] + (ACCENT2[1] - ACCENT[1]) * t)
            b = int(ACCENT[2] + (ACCENT2[2] - ACCENT[2]) * t)
            draw.line([(x + i, y + 2), (x + i, y + h - 2)], fill=(r, g, b))
        rounded_rectangle(draw, [x, y, x + w, y + h], radius,
                           fill=None, outline=XP_TRACK, width=2)

def resize_and_crop(img, target_size):
    target_w, target_h = target_size
    img_w, img_h = img.size
    scale = max(target_w / img_w, target_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    right = left + target_w
    bottom = top + target_h
    return resized.crop((left, top, right, bottom))

async def get_user_rank(uid):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM DiscordStat WHERE id=?", (str(uid),)) as c:
                if not await c.fetchone():
                    return None
            async with db.execute("""
                WITH user_stat AS (SELECT level, coins FROM DiscordStat WHERE id=?)
                SELECT COUNT(*) + 1 FROM DiscordStat, user_stat
                WHERE DiscordStat.level > user_stat.level
                OR (DiscordStat.level = user_stat.level AND DiscordStat.coins > user_stat.coins)
            """, (str(uid),)) as c:
                row = await c.fetchone()
                if row:
                    return row[0]
    except Exception as e:
        logging.error("Error getting user rank exception=%s", type(e).__name__)
    return None


def build_profile_card_sync(
    username="blurred",
    role="Member",
    level=1,
    xp=0,
    xp_max=100,
    coins=0,
    rank=None,
    avatar_img=None,
    bg_img=None,
):
    # layout
    STAT_H  = 96
    PAD_T   = (H - (52 + 16 + 52 + 16 + 2 + 16 + STAT_H)) // 2 # 74
    Y_NAME    = PAD_T
    Y_XP_LBL  = Y_NAME + 52 + 16
    Y_XP_BAR  = Y_XP_LBL + 28
    Y_DIV     = Y_XP_BAR + 20 + 16
    Y_STATS   = Y_DIV + 2 + 16

    # Base background
    if bg_img:
        bg_card_resized = resize_and_crop(bg_img, (W, H))
        overlay = Image.new("RGBA", (W, H), (*BG, 140))  # dark overlay for text readability
        card = Image.alpha_composite(bg_card_resized, overlay)
    else:
        card = Image.new("RGBA", (W, H), BG)

    # Glow behind avatar
    card = draw_glow_circle(card, (236, H // 2), 180, ACCENT, alpha_max=45)
    draw = ImageDraw.Draw(card)

    # Accent bar on left
    bar_h = H - 56
    bar = Image.new("RGBA", (8, bar_h), (0,0,0,0))
    bd = ImageDraw.Draw(bar)
    for y in range(bar_h):
        t = y / bar_h
        c = tuple(int(ACCENT[i] + (ACCENT2[i]-ACCENT[i])*t) for i in range(3))
        bd.line([(0,y),(7,y)], fill=(*c, 220))
    card.paste(bar, (0, 28), bar)

    # Corner lines
    for i, a in enumerate([25, 15, 8]):
        o = i * 18
        draw.line([(W-160+o, 12), (W-12, 160-o)], fill=(*ACCENT, a), width=2)

    # Avatar ring & image
    AV, AV_X, AV_Y = 200, 44, (H - 200) // 2
    for extra, alpha in [(10, 28), (6, 55)]:
        draw.ellipse([AV_X-extra, AV_Y-extra, AV_X+AV+extra, AV_Y+AV+extra], outline=(*ACCENT2, alpha), width=4)
    draw.ellipse([AV_X-4, AV_Y-4, AV_X+AV+2, AV_Y+AV+2], outline=(*ACCENT, 210), width=4)

    # Avatar
    if avatar_img:
        av = circle_avatar(avatar_img, AV)
        card.paste(av, (AV_X, AV_Y), av)
    else:
        # Fallback circle with initial letter
        draw.ellipse([AV_X, AV_Y, AV_X + AV, AV_Y + AV], fill=(25, 28, 50))
        letter_font = get_font(FONT_BOLD_PATH, 96)
        draw.text((AV_X + AV // 2, AV_Y + AV // 2 - 4), username[0].upper() if username else "?", font=letter_font, fill=MUTED, anchor="mm")

    # Online dot
    dx, dy = AV_X+AV-28, AV_Y+AV-28
    draw.ellipse([dx-14, dy-14, dx+14, dy+14], fill=BG)
    draw.ellipse([dx-10, dy-10, dx+10, dy+10], fill=GREEN)

    # Columns
    COL_X = AV_X + AV + 40
    COL_W = W - COL_X - 40

    # Username + badge
    name_fnt  = get_font(FONT_BOLD_PATH, 44)
    badge_fnt = get_font(FONT_MED_PATH, 22)
    name_w = int(draw.textlength(username, font=name_fnt))
    draw.text((COL_X, Y_NAME), username, font=name_fnt, fill=WHITE)

    badge_txt = role.upper()
    badge_tw  = int(draw.textlength(badge_txt, font=badge_fnt))
    bx = COL_X + name_w + 24
    by = Y_NAME + (52 - 40) // 2
    rounded_rectangle(draw, [bx, by, bx+badge_tw+28, by+40], 20, fill=(*ACCENT, 38))
    rounded_rectangle(draw, [bx, by, bx+badge_tw+28, by+40], 20, fill=None, outline=(*ACCENT, 165), width=2)
    draw.text((bx+14, by+8), badge_txt, font=badge_fnt, fill=(*ACCENT, 255))

    # XP Label + Bar
    xp_fnt = get_font(FONT_REG_PATH, 20)
    xp_str = f"{xp:,} / {xp_max:,} XP"
    xp_str_w = int(draw.textlength(xp_str, font=xp_fnt))
    draw.text((COL_X, Y_XP_LBL), "EXPERIENCE", font=xp_fnt, fill=MUTED)
    draw.text((COL_X+COL_W-xp_str_w, Y_XP_LBL), xp_str, font=xp_fnt, fill=MUTED)
    
    # XP Bar
    progress = xp / xp_max if xp_max > 0 else 0
    draw_xp_bar(draw, COL_X, Y_XP_BAR, COL_W, 20, progress, radius=10)

    # Divider
    draw.line([(COL_X, Y_DIV), (COL_X+COL_W, Y_DIV)], fill=DIVIDER_C, width=2)

    # Stats
    GAP = 16
    SW = (COL_W - GAP * 2) // 3
    stats = [
        ("LEVEL", str(level), ACCENT),
        ("RANK", f"#{rank}" if rank else "—", CYAN),
        ("KOIN", f"{coins:,}", GOLD),
    ]
    for i, (lbl, val, col) in enumerate(stats):
        sx = COL_X + i * (SW + GAP)
        rounded_rectangle(draw, [sx, Y_STATS, sx+SW, Y_STATS+STAT_H], 20, fill=STAT_BG)
        # Dot
        cx_dot, cy_dot = sx + 32, Y_STATS + STAT_H // 2
        draw.ellipse([cx_dot-10, cy_dot-10, cx_dot+10, cy_dot+10], fill=col)
        # Text
        tx = sx + 60
        lbl_font = get_font(FONT_REG_PATH, 20)
        val_font = get_font(FONT_BOLD_PATH, 34)
        draw.text((tx, Y_STATS + STAT_H//2 - 36), lbl, font=lbl_font, fill=MUTED)
        draw.text((tx, Y_STATS + STAT_H//2 - 8), val, font=val_font, fill=WHITE)

    # Outer border
    draw.rounded_rectangle([2, 2, W-4, H-4], radius=32, outline=(*ACCENT, 60), width=4)

    # Rounded crop
    out = Image.new("RGBA", (W, H), (0,0,0,0))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0,0,W,H], radius=32, fill=255)
    out.paste(card, (0,0), mask)

    buf = io.BytesIO()
    out.save(buf, format='PNG')
    buf.seek(0)
    return buf

async def generate_profile_image(member, stat, bg_url=None):
    if not PILLOW_AVAILABLE:
        return None

    # Fetch avatar image (with size 512 for high resolution)
    avatar_img = None
    av_url = member.display_avatar.with_size(512).url if member.display_avatar else None
    if av_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(av_url) as resp:
                    if resp.status == 200:
                        av_data = await resp.read()
                        avatar_img = Image.open(io.BytesIO(av_data))
        except Exception as e:
            logging.error("Failed to fetch user avatar exception=%s", type(e).__name__)

    # Fetch background image if bg_url is provided (SSRF-guarded + size/type capped)
    bg_img = None
    if bg_url:
        bg_img = await fetch_remote_image(bg_url)

    # Determine user role
    role = "Member"
    if hasattr(member, "roles") and member.roles:
        non_everyone = [r for r in member.roles if not r.is_default()]
        if non_everyone:
            non_everyone.sort(key=lambda r: r.position, reverse=True)
            role = non_everyone[0].name
            if len(role) > 15:
                role = role[:12] + "..."

    # Determine rank
    rank = await get_user_rank(member.id)

    # XP calculations
    xp = stat.get('xp', 0)
    level = stat.get('level', 1)
    xp_max = level * 100
    coins = stat.get('coins', 0)
    username = member.display_name

    # Generate profile card in background thread to avoid blocking event loop
    try:
        buf = await asyncio.to_thread(
            build_profile_card_sync,
            username=username,
            role=role,
            level=level,
            xp=xp,
            xp_max=xp_max,
            coins=coins,
            rank=rank,
            avatar_img=avatar_img,
            bg_img=bg_img
        )
        return buf
    except Exception as e:
        logging.error("Error in profile card generation exception=%s", type(e).__name__)
        return None

def heart_polygon(cx, cy, size, n=500):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x =  16 * math.sin(t)**3
        y = -(13*math.cos(t) - 5*math.cos(2*t)
               - 2*math.cos(3*t) - math.cos(4*t))
        pts.append((cx + x*size/16, cy + y*size/13))
    return pts

def build_love_card(name1="Blurred", name2="Equiv", percentage=59, avatar_img1=None, avatar_img2=None):
    W, H = 660, 175

    # ── Elegant rose palette ──────────────────────────────────────────────────────
    BG_TOP      = (255, 228, 235)
    BG_BOT      = (252, 205, 220)
    BORDER_C    = (240, 170, 190)
    WHITE       = (255, 255, 255)
    AVATAR_BG   = (255, 245, 248)   # circle fill
    AVATAR_RIM  = (240, 185, 200)   # circle border
    INITIAL_C   = (200,  70, 110)   # letter color
    HEART_EMPTY = (255, 242, 247)
    FILL_A      = (255, 165, 195)   # gradient top
    FILL_B      = (235,  50, 100)   # gradient bottom
    PCT_COLOR   = (180,  25,  65)
    NAME_COLOR  = (190,  85, 115)
    HEART_RIM   = (245, 175, 200)   # outline of heart

    card = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(card)

    # ── Gradient background ───────────────────────────────────────────────────
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOT[0]-BG_TOP[0])*t)
        g = int(BG_TOP[1] + (BG_BOT[1]-BG_TOP[1])*t)
        b = int(BG_TOP[2] + (BG_BOT[2]-BG_TOP[2])*t)
        draw.line([(0,y),(W,y)], fill=(r,g,b,255))

    rr_mask = Image.new("L", (W,H), 0)
    ImageDraw.Draw(rr_mask).rounded_rectangle([0,0,W-1,H-1], radius=24, fill=255)
    card.putalpha(rr_mask)

    # Soft border
    bl = Image.new("RGBA", (W,H), (0,0,0,0))
    ImageDraw.Draw(bl).rounded_rectangle([0,0,W-1,H-1], radius=24,
                                          outline=(*BORDER_C,200), width=3)
    card = Image.alpha_composite(card, bl)
    draw = ImageDraw.Draw(card)

    # ── Avatar circles with initials/images ────────────────────────────────────
    AV     = 110
    HEART_HALF_W = 68         # half the heart's visual width (reserve space)
    GAP          = 28         # gap between avatar edge and heart

    # Direct placement: avatars equidistant from card centre
    cx1 = W//2 - HEART_HALF_W - GAP - AV//2
    cx2 = W//2 + HEART_HALF_W + GAP + AV//2
    cy  = H//2

    init_font_size = 38
    name_font_size = 13

    for cx, name, av_img in [(cx1, name1, avatar_img1), (cx2, name2, avatar_img2)]:
        # Outer soft glow ring
        for r_off, a in [(7,40),(5,80),(3,130)]:
            rr = AV//2 + r_off
            draw.ellipse([cx-rr, cy-rr, cx+rr, cy+rr],
                         outline=(*WHITE, a), width=2)
        # White ring
        rim = AV//2 + 3
        draw.ellipse([cx-rim, cy-rim, cx+rim, cy+rim],
                     outline=AVATAR_RIM, width=2)
        # Circle fill
        draw.ellipse([cx-AV//2, cy-AV//2, cx+AV//2, cy+AV//2],
                     fill=AVATAR_BG)
        
        if av_img:
            av = circle_avatar(av_img, AV)
            card.paste(av, (cx - AV//2, cy - AV//2), av)
        else:
            # Initial letter
            initial  = name[0].upper() if name else "?"
            if_font  = get_font(FONT_BOLD_PATH, init_font_size)
            iw = int(draw.textlength(initial, font=if_font))
            # textbbox for vertical centering
            bb = draw.textbbox((0,0), initial, font=if_font)
            ih = bb[3] - bb[1]
            draw.text((cx - iw//2, cy - ih//2 - bb[1]//2 - 2),
                      initial, font=if_font, fill=INITIAL_C)
        # Name below circle
        nf  = get_font(FONT_MED_PATH, name_font_size)
        nw  = int(draw.textlength(name, font=nf))
        ny  = cy + AV//2 + 7
        if ny + 16 < H:
            draw.text((cx - nw//2, ny), name, font=nf, fill=NAME_COLOR)

    # ── Heart ─────────────────────────────────────────────────────────────────
    HCX, HCY, HSIZE = W//2, H//2 - 2, 46
    pts = heart_polygon(HCX, HCY, HSIZE)

    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    hx0, hx1 = min(xs), max(xs)
    hy0, hy1 = min(ys), max(ys)
    hh  = hy1 - hy0
    fill_y = hy1 - hh * percentage / 100

    # Heart shape mask
    heart_mask = Image.new("L", (W,H), 0)
    ImageDraw.Draw(heart_mask).polygon(pts, fill=255)

    # 1. Empty heart fill
    el = Image.new("RGBA", (W,H), (0,0,0,0))
    ImageDraw.Draw(el).polygon(pts, fill=(*HEART_EMPTY, 255))
    card = Image.alpha_composite(card, el)

    # 2. Gradient fill — only bottom %
    fl = Image.new("RGBA", (W,H), (0,0,0,0))
    fd = ImageDraw.Draw(fl)
    for y in range(int(fill_y), int(hy1)+2):
        t = (y - fill_y) / max(hy1 - fill_y, 1)
        t = min(max(t, 0), 1)
        r = int(FILL_A[0] + (FILL_B[0]-FILL_A[0])*t)
        g = int(FILL_A[1] + (FILL_B[1]-FILL_A[1])*t)
        b = int(FILL_A[2] + (FILL_B[2]-FILL_A[2])*t)
        fd.line([(int(hx0), y),(int(hx1), y)], fill=(r,g,b,255))
    fz = Image.new("L", (W,H), 0)
    ImageDraw.Draw(fz).rectangle([0, int(fill_y), W, H], fill=255)
    fl.putalpha(ImageChops.multiply(heart_mask, fz))
    card = Image.alpha_composite(card, fl)
    draw = ImageDraw.Draw(card)

    # Subtle divider
    if 0 < percentage < 100:
        draw.line([(int(hx0)+4, int(fill_y)), (int(hx1)-4, int(fill_y))],
                  fill=(*WHITE, 140), width=1)

    # Heart outline — soft rose, thin and clean
    for i in range(len(pts)):
        draw.line([pts[i], pts[(i+1)%len(pts)]],
                  fill=(*HEART_RIM, 220), width=2)

    # Percentage text — centred in heart
    pf   = get_font(FONT_BOLD_PATH, 22)
    ptxt = f"{percentage}%"
    pw   = int(draw.textlength(ptxt, font=pf))
    bb   = draw.textbbox((0,0), ptxt, font=pf)
    ph   = bb[3] - bb[1]
    tx   = HCX - pw//2
    ty   = HCY - ph//2 + 2
    # Subtle white shadow
    draw.text((tx+1, ty+1), ptxt, font=pf, fill=(*WHITE, 160))
    draw.text((tx,   ty),   ptxt, font=pf, fill=PCT_COLOR)

    # ── Final rounded crop ─────────────────────────────────────────────────────
    fm = Image.new("L", (W,H), 0)
    ImageDraw.Draw(fm).rounded_rectangle([0,0,W-1,H-1], radius=24, fill=255)
    card.putalpha(fm)

    buf = io.BytesIO()
    card.save(buf, format='PNG')
    buf.seek(0)
    return buf

async def generate_love_image(member1, member2, percentage):
    if not PILLOW_AVAILABLE:
        return None

    avatar_img1 = None
    av_url1 = member1.display_avatar.with_size(128).url if member1.display_avatar else None
    if av_url1:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(av_url1) as resp:
                    if resp.status == 200:
                        av_data = await resp.read()
                        avatar_img1 = Image.open(io.BytesIO(av_data))
        except Exception as e:
            logging.error("Failed to fetch user1 avatar exception=%s", type(e).__name__)

    avatar_img2 = None
    av_url2 = member2.display_avatar.with_size(128).url if member2.display_avatar else None
    if av_url2:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(av_url2) as resp:
                    if resp.status == 200:
                        av_data = await resp.read()
                        avatar_img2 = Image.open(io.BytesIO(av_data))
        except Exception as e:
            logging.error("Failed to fetch user2 avatar exception=%s", type(e).__name__)

    name1 = member1.display_name
    name2 = member2.display_name

    try:
        buf = await asyncio.to_thread(
            build_love_card,
            name1=name1,
            name2=name2,
            percentage=percentage,
            avatar_img1=avatar_img1,
            avatar_img2=avatar_img2
        )
        return buf
    except Exception as e:
        logging.error("Error in love card generation exception=%s", type(e).__name__)
        return None


ANNOUNCE_CATEGORIES = ['market', 'levelup', 'birthday', 'boss', 'booster', 'binomo']

# Cache config.json di memori supaya get_announce_channel (dipanggil di banyak
# loop & event) tidak melakukan blocking file I/O di event loop tiap kali.
_config_cache = None

def _load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            _config_cache = json.load(f)
    except Exception:
        _config_cache = {}
    return _config_cache

def _save_config(cfg):
    # Tulis config.json dan refresh cache. Dipakai endpoint web write.
    global _config_cache
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(cfg, f)
    _config_cache = cfg

def _find_fallback_channel(guild):
    # Logika lama: cari channel general/chat, kalau gagal ambil channel pertama yang writable.
    for ch in guild.text_channels:
        if 'general' in ch.name.lower() or 'chat' in ch.name.lower():
            if ch.permissions_for(guild.me).send_messages:
                return ch
    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).send_messages:
            return ch
    return None

def get_announce_channel(guild, category):
    # Resolusi: announce_channels[category] -> announce_channels[default] -> fallback lama.
    # Mengembalikan channel yang writable, atau None.
    cfg = _load_config()
    announce = cfg.get('announce_channels', {}) if isinstance(cfg, dict) else {}

    candidates = []
    if category:
        candidates.append(announce.get(category))
    candidates.append(announce.get('default'))
    # Kompatibilitas: key lama booster_channel_id untuk kategori booster
    if category == 'booster':
        candidates.append(cfg.get('booster_channel_id'))

    for cid in candidates:
        if not cid:
            continue
        try:
            ch = guild.get_channel(int(cid))
        except (ValueError, TypeError):
            ch = None
        if ch and ch.permissions_for(guild.me).send_messages:
            return ch

    return _find_fallback_channel(guild)

async def check_birthdays():
    await client.wait_until_ready()
    while not client.is_closed():
        today_str = datetime.now().strftime("%d-%m")
        bdays = await load_json('birthdays.json')
        
        # We need a channel to announce birthdays.
        for guild in client.guilds:
            announce_channel = get_announce_channel(guild, 'birthday')

            if announce_channel:
                for uid, date_str in bdays.items():
                    if date_str == today_str:
                        # Check if we already announced this year
                        last_bday = await load_json('last_bday.json')
                        year = str(datetime.now().year)
                        key = f"{uid}_{year}"
                        if last_bday.get(key):
                            continue
                            
                        # Reward
                        user = client.get_user(int(uid))
                        name = user.display_name if user else f"User {uid}"
                        await adjust_coins(uid, 1000, name)
                        
                        await announce_channel.send(f"🎉 **SELAMAT ULANG TAHUN!** 🎉\nHari ini adalah hari ulang tahun {user.mention if user else name}!\nSebagai hadiah, kamu mendapatkan **1000 Koin**! 🎁")
                        
                        last_bday[key] = True
                        await save_json('last_bday.json', last_bday)
                        
        await asyncio.sleep(3600) # Check every hour

async def init_market():
    market = await load_json(MARKET_FILE)
    if not market or 'coins' not in market:
        market = {
            'last_updated': datetime.now().isoformat(),
            'coins': {
                'ETHR': {'name': 'ETHERnal', 'price': 1000, 'history': [1000]},
                'ORCL': {'name': 'Cosmic Oracle', 'price': 2000, 'history': [2000]},
                'MTR': {'name': 'Meteorite', 'price': 500, 'history': [500]},
                'ECLP': {'name': 'Eclipsoin', 'price': 250, 'history': [250]},
                'ORBT': {'name': 'Orbitcoin', 'price': 100, 'history': [100]},
                'TRST': {'name': 'TrustCoin', 'price': 50, 'history': [50]},
                'LUNA': {'name': 'Lunniera', 'price': 5000, 'history': [5000]}
            }
        }
        await save_json(MARKET_FILE, market)
    return market

async def update_market_prices():
    await client.wait_until_ready()
    while not client.is_closed():
        market = await init_market()
        for symbol, data in market['coins'].items():
            current_price = data['price']
            
            # Volatility setting
            if symbol == 'ETHR':
                volatility = 0.05 # 5%
            elif symbol == 'ORCL':
                volatility = 0.08 # 8%
            elif symbol == 'ECLP':
                volatility = 0.15 # 15%
            elif symbol == 'ORBT':
                volatility = 0.20 # 20%
            elif symbol == 'MTR':
                volatility = 0.25 # 25%
            elif symbol == 'LUNA':
                volatility = 0.40 # 40% high risk
            elif symbol == 'TRST':
                volatility = 0.50 # 50% extreme risk
            else:
                volatility = 0.10
                
            change_pct = random.uniform(-volatility, volatility)
            new_price = int(current_price * (1 + change_pct))
            
            # Prevent going to 0
            if new_price < 10:
                new_price = 10
                
            # Update history (keep last 10)
            data['history'].append(new_price)
            if len(data['history']) > 10:
                data['history'].pop(0)
                
            data['price'] = new_price
            
        # Random Market Event (10% chance)
        event_message = None
        if random.random() < 0.10:
            target_coin = random.choice(list(market['coins'].keys()))
            event_type = random.choice(['pump', 'dump'])
            
            if event_type == 'pump':
                pump_pct = random.uniform(0.5, 1.2) # 50% to 120% pump
                market['coins'][target_coin]['price'] = int(market['coins'][target_coin]['price'] * (1 + pump_pct))
                event_message = f"📈 **MARKET UPDATE:** Harga {market['coins'][target_coin]['name']} ({target_coin}) naik sebesar **+{int(pump_pct*100)}%**!"
            else:
                dump_pct = random.uniform(0.4, 0.8) # 40% to 80% dump
                market['coins'][target_coin]['price'] = int(market['coins'][target_coin]['price'] * (1 - dump_pct))
                event_message = f"📉 **MARKET UPDATE:** Harga {market['coins'][target_coin]['name']} ({target_coin}) turun sebesar **-{int(dump_pct*100)}%**!"
                
            # Prevent going to 0 again
            if market['coins'][target_coin]['price'] < 10:
                market['coins'][target_coin]['price'] = 10
                
            # Update latest history point to reflect massive change
            market['coins'][target_coin]['history'][-1] = market['coins'][target_coin]['price']
            
        market['last_updated'] = datetime.now().isoformat()
        await save_json(MARKET_FILE, market)
        if event_message:
            logging.info(f"[MARKET] Event harga: {target_coin} {event_type}")
        
        # Broadcast event message
        if event_message and not (ECONOMY_V1_ENABLED and ECONOMY_PHASE6_ENABLED):
            for guild in client.guilds:
                ch = get_announce_channel(guild, 'market')
                if ch:
                    client.loop.create_task(ch.send(event_message))
                            
        # Resolve Binomo Bets
        binomo = {} if ECONOMY_PHASE8_ENABLED else await load_json(BINOMO_FILE)
        if binomo:
            results = []
            for uid, bet_data in list(binomo.items()):
                symbol = bet_data['symbol']
                direction = bet_data['direction'] # 'UP' or 'DOWN'
                bet_amount = bet_data['bet']
                entry_price = bet_data['entry_price']
                
                new_price = market['coins'][symbol]['price']
                won = False
                if direction == 'UP' and new_price > entry_price:
                    won = True
                elif direction == 'DOWN' and new_price < entry_price:
                    won = True
                    
                if won:
                    winnings = bet_amount * 2
                    await adjust_coins(uid, winnings, f"User_{uid}")
                    results.append(f"<@{uid}> **MENANG {winnings} Koin!** (Tebak {symbol} {direction} | Entry: {entry_price}, Now: {new_price})")
                else:
                    results.append(f"<@{uid}> **RUGI {bet_amount} Koin!** (Tebak {symbol} {direction} | Entry: {entry_price}, Now: {new_price})")
                
                del binomo[uid]
            await save_json(BINOMO_FILE, binomo)
            
            if results:
                result_str = "🎰 **HASIL JUDI BINOMO 10 MENIT INI:** 🎰\n" + "\n".join(results)
                for guild in client.guilds:
                    ch = get_announce_channel(guild, 'binomo')
                    if ch:
                        client.loop.create_task(ch.send(result_str))
                            
        await asyncio.sleep(600) # Every 10 minutes

async def voice_salary_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(600) # Wait 10 minutes
        for guild in client.guilds:
            # Channel pengumuman level-up dari VC
            announce_channel = get_announce_channel(guild, 'levelup')

            # Loop setiap voice channel
            for vc in guild.voice_channels:
                members = [m for m in vc.members if not m.bot]
                if len(members) >= 2: # Minimal 2 orang (anti solo farming)
                    for m in members:
                        if not m.voice.self_deaf and not m.voice.deaf:
                            uid = str(m.id)
                            # Kredit koin + XP secara atomik (hindari race read-modify-write).
                            reward = await apply_soft_cap(uid, ECON_VC_COINS_PER_10MIN)
                            await add_coins(uid, reward, m.display_name)

                            stat_before = await get_discord_stat(uid)
                            level_before = stat_before['level']
                            await add_xp(uid, m.display_name, ECON_VC_XP_PER_10MIN)
                            stat_after = await get_discord_stat(uid)

                            if stat_after['level'] > level_before and announce_channel:
                                client.loop.create_task(
                                    announce_channel.send(f"Selamat {m.mention}, kamu naik ke **Level {stat_after['level']}** dari Voice Channel!")
                                )

async def boss_raid_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        await asyncio.sleep(3600) # Every 1 hour
        if random.random() < 0.20: # 20% chance to spawn boss
            boss_data = await load_json(BOSS_FILE)
            if not boss_data.get('active', False):
                boss_data = {
                    'active': True,
                    'hp': 10000,
                    'max_hp': 10000,
                    'name': '🐉 Naga Emas Koruptor'
                }
                await save_json(BOSS_FILE, boss_data)
                logging.info(f"[BOSS] Boss raid spawn: {boss_data['name']} HP {boss_data['hp']}")
                # Cari channel pengumuman
                for guild in client.guilds:
                    ch = get_announce_channel(guild, 'boss')
                    if ch:
                        client.loop.create_task(
                            ch.send(f"⚠️ **BOSS RAID EVENT DIMULAI!** ⚠️\n**{boss_data['name']}** telah muncul dengan {boss_data['hp']} HP!\nKetik `!attack` untuk menyerang! Yang berhasil membunuhnya mendapat hadiah 5000 Koin!")
                        )
                                
async def crypto_mining_loop():
    await client.wait_until_ready()
    if ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE7_ENABLED:
        from economy.phase7_recovery import recover_phase7
        while not client.is_closed():
            result = await recover_phase7(DB_PATH)
            if not result.get("ready"):
                logging.warning("Phase 7 Mining recovery fail-closed: %s", result.get("code"))
            await asyncio.sleep(3600)
        return
    while not client.is_closed():
        await asyncio.sleep(3600) # Every 1 hour
        users = await load_json('users.json')

        has_mined = False
        miner_count = 0
        mined_summary = {}  # {symbol: total_mined}
        for uid, udata in users.items():
            rigs = udata.get('rigs', {}) if isinstance(udata, dict) else {}
            if not rigs:
                continue
            # Format rigs baru: {symbol: {tier: count}}
            # Format lama (migrasi): {tier: count} → dianggap ETHR
            if rigs and isinstance(next(iter(rigs.values())), int):
                # Migrasi format lama → semua rig dianggap mining ETHR
                rigs = {'ETHR': rigs}
                udata['rigs'] = rigs
            user_mined = False
            crypto = udata.setdefault('crypto', {})
            for symbol, tier_map in rigs.items():
                if not isinstance(tier_map, dict):
                    continue
                rates = MINING_RATES.get(symbol)
                if not rates:
                    continue
                mined = 0.0
                for tier, count in tier_map.items():
                    lo, hi = rates.get(str(tier), (0, 0))
                    if hi <= 0:
                        continue
                    mined += random.uniform(lo, hi) * count
                if mined > 0:
                    crypto[symbol] = crypto.get(symbol, 0) + round(mined, 6)
                    mined_summary[symbol] = mined_summary.get(symbol, 0) + mined
                    user_mined = True
            if user_mined:
                has_mined = True
                miner_count += 1

        if has_mined:
            await save_json('users.json', users)
            summary_str = ", ".join(f"{s}={n}" for s, n in mined_summary.items())
            logging.info(f"[MINING] {miner_count} penambang: {summary_str}")

@client.event
async def on_ready():
    global TREE_SYNC_DONE
    if not clean_caches.is_running():
        clean_caches.start()
    if deal_phase_at_least(5) and not deal_reminder_loop.is_running():
        deal_reminder_loop.start()
    if not public_trust_panel_loop.is_running():
        public_trust_panel_loop.start()
    if not staff_operation_panel_loop.is_running():
        staff_operation_panel_loop.start()
    runtime_guild_id = ALLOWED_SERVER_ID
    if runtime_guild_id is None:
        raise RuntimeError("Guild runtime belum dikonfigurasi.")
    # Single Server Lock
    for guild in client.guilds:
        if guild.id != runtime_guild_id:
            logging.warning(f"Leaving unauthorized server: {guild.name}")
            await guild.leave()

    def collect_command_names(commands, prefix=""):
        names = []
        for command in commands:
            qualified = f"{prefix} {command.name}".strip()
            names.append(qualified)
            if isinstance(command, discord.app_commands.Group):
                names.extend(collect_command_names(command.commands, qualified))
        return names

    command_names = collect_command_names(tree.get_commands())
    duplicate_names = sorted({name for name in command_names if command_names.count(name) > 1})
    if duplicate_names:
        logging.error("Duplicate command registration names=%s", duplicate_names)
        raise RuntimeError("Duplicate command registration terdeteksi.")

    sync_guild = discord.Object(id=runtime_guild_id)
    tree.copy_global_to(guild=sync_guild)
    if not TREE_SYNC_DONE:
        synced = await tree.sync(guild=sync_guild)
        TREE_SYNC_DONE = True
        logging.info(
            "Command sync completed staging_mode=%s guild_id=%s count=%s names=%s",
            STAGING_MODE, runtime_guild_id, len(synced), sorted(command.name for command in synced),
        )
    if STAGING_MODE:
        from economy.catalog import catalog_hash
        from economy.constants import RPG_PHASE3_CATALOG_VERSION
        from economy.phase3_schema import PHASE3_HARDENING_CHECKSUM, PHASE3_HARDENING_VERSION
        logging.info(
            "Staging startup database_path=%s database_role=staging guild_id=%s "
            "economy_flags=%s/%s/%s migration_version=%s migration_checksum=%s "
            "catalog_version=%s catalog_checksum=%s registered_command_count=%s",
            DB_PATH, runtime_guild_id,
            STARTUP_CONFIGURATION.economy_v1_enabled,
            STARTUP_CONFIGURATION.economy_phase2_enabled,
            STARTUP_CONFIGURATION.economy_phase3_enabled,
            PHASE3_HARDENING_VERSION, PHASE3_HARDENING_CHECKSUM,
            RPG_PHASE3_CATALOG_VERSION, catalog_hash(), len(command_names),
        )
    _schedule_ready_task("web_server", start_web_server, once=True)
    _schedule_ready_task("check_birthdays", check_birthdays)
    _schedule_ready_task("update_market_prices", update_market_prices)
    _schedule_ready_task("voice_salary_loop", voice_salary_loop)
    _schedule_ready_task("boss_raid_loop", boss_raid_loop)
    _schedule_ready_task("crypto_mining_loop", crypto_mining_loop)
    _schedule_ready_task("resume_scheduled_jobs", resume_scheduled_jobs, once=True)
    _schedule_ready_task("refresh_public_trust_panels", refresh_all_public_trust_panels, once=True)
    _schedule_ready_task("refresh_staff_operation_panels", refresh_all_staff_operation_panels, once=True)
    for callback in list(READY_STARTUP_CALLBACKS):
        callback_name = getattr(callback, "__qualname__", getattr(callback, "__name__", "callback"))
        _schedule_ready_task(f"startup:{callback_name}", callback, once=True)
    logging.info(f'We have logged in as {client.user}')

@web.middleware
async def cors_middleware(request, handler):
    try:
        response = await handler(request)
    except DashboardSecurityError as exc:
        response = web.json_response({'error': exc.code}, status=exc.status)
    except web.HTTPException:
        raise
    except Exception:
        logging.error("dashboard backend request failed route=%s", request.path, exc_info=True)
        response = web.json_response({'error': 'internal_error'}, status=500)
    origin = request.headers.get('Origin')
    if origin and origin in ALLOWED_ORIGINS and not request.path.startswith('/internal/'):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    return response

async def handle_options(request):
    origin = request.headers.get('Origin')
    if not origin or origin not in ALLOWED_ORIGINS:
        return web.json_response({'error': 'forbidden'}, status=403)
    response = web.Response(status=204)
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

async def api_radar(request):
    data = []
    for uid, join_time in voice_join_times.items():
        delta = datetime.now() - join_time
        minutes = int(delta.total_seconds() // 60)
        
        # Try to find the user in discord cache
        user = client.get_user(uid)
        username = user.display_name if user else f"User {uid}"
        
        # Find which voice channel they are in
        channel_name = "Unknown"
        for guild in client.guilds:
            member = guild.get_member(uid)
            if member and member.voice and member.voice.channel:
                channel_name = member.voice.channel.name
                break
                
        data.append({
            'user_id': str(uid),
            'username': username,
            'channel': channel_name,
            'minutes': minutes
        })
    return web.json_response(data)

def require_token(request):
    # Returns True if the request carries a valid X-Auth-Token. If DASHBOARD_TOKEN
    # is unset, all access is denied (fail closed) to avoid an open write surface.
    if not DASHBOARD_TOKEN:
        return False
    supplied = request.headers.get('X-Auth-Token', '')
    return hmac.compare_digest(supplied, DASHBOARD_TOKEN)

async def api_broadcast(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        data = await request.json()
        channel_type = data.get('channel')
        message = data.get('message')
        
        if not channel_type or not message:
            return web.json_response({'error': 'Missing channel or message'}, status=400)
            
        try:
            cid = int(channel_type)
        except ValueError:
            return web.json_response({'error': 'Invalid channel ID format'}, status=400)
            
        channel = client.get_channel(cid)
        if not channel:
            return web.json_response({'error': 'Channel not found by bot'}, status=404)
            
        await send_long_message(channel, message)
            
        return web.json_response({'status': 'sent'})
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def serve_dashboard(request):
    try:
        with open('dashboard.html', 'r', encoding='utf-8') as f:
            html = f.read()
        return web.Response(text=html, content_type='text/html')
    except Exception:
        return web.Response(text="Dashboard not found.", status=404)


async def get_server_data(request):
    try:
        guild = client.get_guild(ALLOWED_SERVER_ID)
        if not guild:
            return web.json_response({'error': 'Bot is not in the allowed server'})
            
        data = {
            'id': str(guild.id),
            'name': guild.name,
            'icon_url': str(guild.icon.url) if guild.icon else None,
            'member_count': guild.member_count,
            'description': guild.description,
            'premium_subscription_count': guild.premium_subscription_count,
            'text_channels': [{'id': str(c.id), 'name': c.name} for c in guild.text_channels],
            'voice_channels': [{'id': str(c.id), 'name': c.name, 'connected_members': len(c.members)} for c in guild.voice_channels],
            'roles': [{'id': str(r.id), 'name': r.name, 'color': str(r.color)} for r in guild.roles if r.name != '@everyone']
        }
        return web.json_response(data)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def get_config_api(request):
    return web.json_response(_load_config())

async def update_config_api(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        data = await request.json()
        # Validasi: body harus objek JSON (dict), bukan list/str/null.
        if not isinstance(data, dict):
            return web.json_response({'error': 'Body must be a JSON object'}, status=400)
        # Jaga agar announce_channels (kalau ada) tetap berbentuk mapping valid,
        # supaya POST mentah ini tidak merusak struktur yang dipakai bot.
        if 'announce_channels' in data:
            ac = data['announce_channels']
            if not isinstance(ac, dict):
                return web.json_response({'error': 'announce_channels must be an object'}, status=400)
            for k, v in ac.items():
                if v is None:
                    ac[k] = ''
                elif not str(v).strip().isdigit() and str(v).strip() != '':
                    return web.json_response({'error': f'Invalid channel id for {k}'}, status=400)
        _save_config(data)
        return web.json_response({'status': 'success'})
    except Exception as e:
        logging.error("update_config_api error exception=%s", type(e).__name__)
        return web.json_response({'status': 'error'}, status=500)

async def api_channels(request):
    # Daftar text channel guild untuk dropdown di dashboard / web main.
    guild = client.get_guild(ALLOWED_SERVER_ID)
    if not guild:
        return web.json_response({'error': 'Bot is not in the allowed server'}, status=404)
    channels = [{'id': str(c.id), 'name': c.name} for c in guild.text_channels]
    return web.json_response(channels)

async def get_announce_config_api(request):
    cfg = _load_config()
    announce = cfg.get('announce_channels', {}) if isinstance(cfg, dict) else {}
    # Pastikan semua kategori hadir (default + 6) supaya client gampang render.
    result = {'default': announce.get('default', '')}
    for cat in ANNOUNCE_CATEGORIES:
        result[cat] = announce.get(cat, '')
    return web.json_response(result)

async def update_announce_config_api(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        data = await request.json()
        allowed = ['default'] + ANNOUNCE_CATEGORIES
        announce = {}
        for key in allowed:
            val = data.get(key, '')
            if val is None:
                val = ''
            val = str(val).strip()
            # Hanya terima channel ID berupa digit, atau string kosong (= pakai fallback).
            if val and not val.isdigit():
                return web.json_response({'error': f'Invalid channel id for {key}'}, status=400)
            announce[key] = val
        cfg = _load_config()
        if not isinstance(cfg, dict):
            cfg = {}
        cfg['announce_channels'] = announce
        _save_config(cfg)
        await write_audit('announce-config', None, str(announce), source="api")
        return web.json_response({'status': 'success', 'announce_channels': announce})
    except Exception as e:
        logging.error("update_announce_config_api error exception=%s", type(e).__name__)
        return web.json_response({'status': 'error'}, status=500)

# ── Extra dashboard READ endpoints ───────────────────────────────────────────
def _resolve_name(uid):
    # Resolve display name dari cache discord; fallback ke "User <id>".
    try:
        u = client.get_user(int(uid))
        if u:
            return u.display_name
    except (ValueError, TypeError):
        pass
    return f"User {uid}"


async def api_leaderboard(request):
    # Top member dari DiscordStat. ?sort=coins|level (default level), ?limit=N (1..100).
    sort = request.query.get('sort', 'level')
    if sort not in ('coins', 'level'):
        return web.json_response({'error': "sort must be 'coins' or 'level'"}, status=400)
    try:
        limit = int(request.query.get('limit', '10'))
    except ValueError:
        limit = 10
    limit = max(1, min(limit, 100))
    order = "coins DESC, level DESC" if sort == 'coins' else "level DESC, coins DESC"
    rows_out = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                f"SELECT id, displayName, coins, xp, level FROM DiscordStat ORDER BY {order} LIMIT ?",
                (limit,)) as cur:
                rows = await cur.fetchall()
        for i, r in enumerate(rows):
            rows_out.append({
                'rank': i + 1, 'id': str(r[0]),
                'displayName': r[1] or _resolve_name(r[0]),
                'coins': r[2], 'xp': r[3], 'level': r[4],
            })
    except Exception as e:
        logging.error("api_leaderboard error exception=%s", type(e).__name__)
        return web.json_response({'error': 'internal error'}, status=500)
    return web.json_response({'sort': sort, 'limit': limit, 'entries': rows_out})


def _cooldown_info(users, uid, now):
    # Hitung sisa cooldown (detik) untuk tiap aktivitas berbasis users.json.
    u = users.get(uid, {})
    specs = {'work': 3600, 'rob': 7200, 'pray': 3600, 'curse': 14400}
    keymap = {'work': 'lastWork', 'rob': 'lastRob', 'pray': 'lastPray', 'curse': 'lastCurse'}
    out = {}
    for name, dur in specs.items():
        ts = u.get(keymap[name])
        remaining = 0
        if ts:
            try:
                elapsed = (now - datetime.fromisoformat(ts)).total_seconds()
                remaining = max(0, int(dur - elapsed))
            except Exception:
                remaining = 0
        out[name] = remaining
    return out


async def api_user(request):
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    stat = await get_discord_stat(uid)
    rank = await get_user_rank(uid)
    users = await load_json('users.json')
    u = users.get(uid, {})
    marriages = await load_json('marriages.json')
    partner = marriages.get(uid)
    personas = await load_json(PERSONAS_FILE)
    bounties = await load_json('bounties.json')
    weekly_data = await load_json('weekly.json')
    quests_data = await load_json(QUESTS_FILE)
    items_data = await load_json(ITEMS_FILE)
    bdays = await load_json('birthdays.json')
    now = datetime.now()

    # Top 3 minigame berdasarkan jumlah main (plays).
    games = u.get('games', {})
    sorted_games = sorted(games.items(), key=lambda x: x[1].get('plays', 0), reverse=True)
    top_games = []
    for gname, gstats in sorted_games[:3]:
        plays = gstats.get('plays', 0)
        wins = gstats.get('wins', 0)
        win_rate = round((wins / plays) * 100, 1) if plays > 0 else 0
        top_games.append({'game': gname, 'plays': plays, 'wins': wins, 'win_rate': win_rate})

    data = {
        'id': uid,
        'displayName': _resolve_name(uid),
        'coins': stat['coins'],
        'xp': stat['xp'],
        'level': stat['level'],
        'xp_to_next': stat['level'] * 100,
        'rank': rank,
        'lastDaily': stat['lastDaily'],
        'crypto': u.get('crypto', {}),
        'rigs': u.get('rigs', {}),
        'items': u.get('items', {}),
        'pet': u.get('pet'),
        'achievements': u.get('achievements', []),
        'total_vc_minutes': u.get('total_vc_minutes', 0),
        'married_to': partner,
        'children': u.get('children', []),
        'bg_url': items_data.get(uid, {}).get('bg_url') or u.get('bg_url'),
        'cooldowns': _cooldown_info(users, uid, now),
        'games': games,
        'top_games': top_games,
        'persona': personas.get(uid),
        'birthday': bdays.get(uid),
        'bounty': bounties.get(uid, 0),
        'weekly_claimed': weekly_data.get(uid),
        'quest': quests_data.get(uid),
    }
    return web.json_response(data)


async def api_market(request):
    if ECONOMY_V1_ENABLED and ECONOMY_PHASE6_ENABLED:
        from economy.crypto_market import market_snapshot
        return web.json_response(await market_snapshot(DB_PATH))
    market = await load_json(MARKET_FILE)
    return web.json_response(market or {})


async def api_crypto_v1_status(request):
    """Status Crypto read-only; semua mutasi tetap melalui service transaksi."""
    if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE6_ENABLED):
        return web.json_response({'enabled': False, 'schema_ready': False})
    from economy.crypto import crypto_readiness
    from economy.crypto_market import market_snapshot
    readiness = await crypto_readiness(DB_PATH, ALLOWED_SERVER_ID)
    snapshot = await market_snapshot(DB_PATH)
    return web.json_response({
        'enabled': True,
        'schema_ready': bool(snapshot.get('available')),
        'readiness': readiness,
        'market': snapshot,
    })


async def api_treasury(request):
    treasury = await load_json(TREASURY_FILE)
    balance = treasury.get('balance', 0) if isinstance(treasury, dict) else 0
    return web.json_response({'balance': balance})


async def api_boss(request):
    if ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE3_ENABLED:
        from economy.bosses import boss_status
        return web.json_response(await boss_status(DB_PATH, ALLOWED_SERVER_ID) or {"active": False})
    boss = await load_json(BOSS_FILE)
    return web.json_response(boss or {'active': False})


async def api_economy_stats(request):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*), COALESCE(SUM(coins),0), COALESCE(AVG(level),0), COALESCE(MAX(coins),0) FROM DiscordStat") as cur:
                count, total_coins, avg_level, max_coins = await cur.fetchone()
            async with db.execute(
                "SELECT id, displayName, coins FROM DiscordStat ORDER BY coins DESC LIMIT 1") as cur:
                top = await cur.fetchone()
    except Exception as e:
        logging.error("api_economy_stats error exception=%s", type(e).__name__)
        return web.json_response({'error': 'internal error'}, status=500)
    treasury = await load_json(TREASURY_FILE)
    top_holder = None
    if top:
        top_holder = {'id': str(top[0]), 'displayName': top[1] or _resolve_name(top[0]), 'coins': top[2]}
    v1_supply = await get_supply_report(DB_PATH, ALLOWED_SERVER_ID)
    return web.json_response({
        'player_count': count,
        'total_coins_in_circulation': int(total_coins),
        'average_level': round(avg_level, 2),
        'richest_coins': int(max_coins),
        'top_holder': top_holder,
        'treasury_balance': treasury.get('balance', 0) if isinstance(treasury, dict) else 0,
        'v1_enabled': os.getenv('ECONOMY_V1_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on'),
        'v1_supply': v1_supply,
    })


async def api_economy_v1_supply(request):
    return web.json_response({
        'enabled': os.getenv('ECONOMY_V1_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on'),
        'guild_id': str(ALLOWED_SERVER_ID),
        'supply': await get_supply_report(DB_PATH, ALLOWED_SERVER_ID),
    })


async def api_economy_v1_profile(request):
    user_id = str(request.match_info.get('id', '')).strip()
    if not user_id.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    profile = await get_profile_snapshot(
        DB_PATH, ALLOWED_SERVER_ID, user_id, create=False,
    )
    if profile is None:
        return web.json_response({'error': 'v1 profile not found'}, status=404)
    payload = {
        'guild_id': profile.guild_id,
        'user_id': profile.user_id,
        'level': profile.level,
        'xp': profile.xp,
        'etm_balance': profile.etm_balance,
        'ecy_balance': profile.ecy_balance,
        'max_hp': profile.max_hp,
        'current_hp': profile.current_hp,
        'attack': profile.attack,
        'defense': profile.defense,
        'crit_bps': profile.crit_bps,
        'energy': profile.energy,
        'power_score': profile.power_score,
        'activity_score_30d': profile.activity_score_30d,
        'active_weapon_instance_id': profile.active_weapon_instance_id,
        'active_armor_instance_id': profile.active_armor_instance_id,
        'active_accessory_instance_id': profile.active_accessory_instance_id,
        'active_pet_instance_id': profile.active_pet_instance_id,
        'phase3_enabled': ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE3_ENABLED,
    }
    if payload['phase3_enabled']:
        from economy.equipment import get_active_loadout, get_effective_stats
        effective = await get_effective_stats(DB_PATH, ALLOWED_SERVER_ID, user_id)
        if effective:
            payload.update({
                'effective_max_hp': effective.max_hp,
                'effective_attack': effective.attack,
                'effective_defense': effective.defense,
                'effective_crit_bps': effective.crit_bps,
                'effective_power_score': effective.power_score,
                'active_loadout': await get_active_loadout(DB_PATH, ALLOWED_SERVER_ID, user_id),
            })
    return web.json_response(payload)


async def api_marketplace_v1_status(request):
    if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and
            ECONOMY_PHASE3_ENABLED and ECONOMY_PHASE4_ENABLED):
        return web.json_response({'enabled': False, 'schema_ready': False})
    from economy.marketplace import marketplace_status
    from economy.phase4_schema import phase4_schema_capability
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            ready = await phase4_schema_capability(db)
        if not ready:
            return web.json_response({'enabled': True, 'schema_ready': False})
        payload = await marketplace_status(DB_PATH, ALLOWED_SERVER_ID)
        return web.json_response({'enabled': True, 'schema_ready': True, **payload})
    except Exception:
        logging.error("api_marketplace_v1_status error", exc_info=True)
        return web.json_response({'error': 'internal error'}, status=500)


async def api_mining_v1_status(request):
    """Status Mining read-only; tidak menyediakan jalur mutasi API."""
    if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE7_ENABLED):
        return web.json_response({'enabled': False, 'schema_ready': False})
    from economy.mining import mining_readiness
    try:
        payload = await mining_readiness(DB_PATH, ALLOWED_SERVER_ID)
        return web.json_response({
            'enabled': True,
            'schema_ready': payload.get('code') != 'schema_unavailable',
            **payload,
        })
    except Exception:
        logging.error("api_mining_v1_status error", exc_info=True)
        return web.json_response({'error': 'internal error'}, status=500)


async def api_casino_v1_status(request):
    """Status Casino read-only; tidak menyediakan jalur mutasi API."""
    if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE5_ENABLED):
        return web.json_response({'enabled': False, 'schema_ready': False})
    from economy.casino import casino_status
    try:
        payload = await casino_status(DB_PATH, ALLOWED_SERVER_ID)
        return web.json_response({
            'enabled': True,
            'schema_ready': bool(payload.pop('schemaCapable', False)),
            **payload,
        })
    except Exception:
        logging.error("api_casino_v1_status error", exc_info=True)
        return web.json_response({'error': 'internal error'}, status=500)


async def api_phase8_status(request):
    """Status Phase 8 read-only; tidak menyediakan mutasi Giveaway/Options."""
    if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE5_ENABLED
            and ECONOMY_PHASE6_ENABLED and ECONOMY_PHASE8_ENABLED):
        return web.json_response({'enabled': False, 'schema_ready': False})
    from economy.eternal_options import options_status
    try:
        payload = await options_status(DB_PATH, ALLOWED_SERVER_ID)
        return web.json_response({'enabled': True,
                                  'schema_ready': bool(payload.pop('schemaCapable', False)), **payload})
    except Exception:
        logging.error("api_phase8_status error", exc_info=True)
        return web.json_response({'error': 'internal error'}, status=500)


async def api_marketplace_v1_action(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and
            ECONOMY_PHASE3_ENABLED and ECONOMY_PHASE4_ENABLED):
        return web.json_response({'error': 'marketplace disabled'}, status=409)
    try:
        data = await request.json()
        action = str(data.get('action', '')).strip().lower()
        actor_id = 'internal-api-principal'
        reason = _audit_safe_text(data.get('reason'), 100) or 'internal_api'
        from economy.marketplace import (
            issue_internal_api_authorization, require_authorization,
            set_marketplace_pause,
        )
        authorization = issue_internal_api_authorization(
            actor_id=actor_id, guild_id=ALLOWED_SERVER_ID,
            request_id=str(request.headers.get('X-Request-ID') or f'api:{id(request)}'),
            verified_api_principal=True,
        )
        if action == 'reconcile':
            from economy.phase4_recovery import recover_phase4_runtime
            require_authorization(authorization, guild_id=ALLOWED_SERVER_ID, staff=True)
            result = await recover_phase4_runtime(DB_PATH)
        elif action in ('pause', 'resume'):
            response = await set_marketplace_pause(
                DB_PATH, guild_id=ALLOWED_SERVER_ID, paused=action == 'pause',
                reason=reason, authorization=authorization,
            )
            result = {'ok': response.ok, 'code': response.code}
        elif action == 'return':
            from economy.marketplace import cancel_listing
            listing_id = str(data.get('listing_id', '')).strip()
            if not listing_id:
                return web.json_response({'error': 'listing_id required'}, status=400)
            response = await cancel_listing(
                DB_PATH, guild_id=ALLOWED_SERVER_ID, listing_id=listing_id,
                authorization=authorization, reason_code=reason,
            )
            result = {'ok': response.ok, 'code': response.code,
                      'listing_id': response.listing_id}
        elif action == 'user-state':
            from economy.marketplace import set_marketplace_user_state
            user_id = str(data.get('user_id', '')).strip()
            state = str(data.get('status', '')).strip().upper()
            if not user_id.isdigit():
                return web.json_response({'error': 'invalid user_id'}, status=400)
            response = await set_marketplace_user_state(
                DB_PATH, guild_id=ALLOWED_SERVER_ID, user_id=user_id, status=state,
                authorization=authorization, reason_code=reason,
            )
            result = {'ok': response.ok, 'code': response.code}
        else:
            return web.json_response({'error': 'unsupported action'}, status=400)
        await write_audit(
            'marketplace_internal_action', target_id=data.get('listing_id') or data.get('user_id'),
            detail=f"action={action};result={result.get('code', 'ok')}", source='internal_api',
        )
        return web.json_response(result)
    except (ValueError, json.JSONDecodeError):
        return web.json_response({'error': 'invalid request'}, status=400)
    except Exception:
        logging.error("api_marketplace_v1_action error", exc_info=True)
        return web.json_response({'error': 'internal error'}, status=500)


async def api_marriages(request):
    marriages = await load_json('marriages.json')
    seen = set()
    pairs = []
    for a, b in marriages.items():
        key = tuple(sorted((str(a), str(b))))
        if key in seen:
            continue
        seen.add(key)
        pairs.append({
            'a': {'id': str(a), 'displayName': _resolve_name(a)},
            'b': {'id': str(b), 'displayName': _resolve_name(b)},
        })
    return web.json_response(pairs)


async def api_stats_summary(request):
    guild = client.get_guild(ALLOWED_SERVER_ID)
    in_voice = 0
    member_count = 0
    if guild:
        member_count = guild.member_count
        for vc in guild.voice_channels:
            in_voice += len([m for m in vc.members if not m.bot])
    boss = await load_json(BOSS_FILE)
    treasury = await load_json(TREASURY_FILE)
    total_coins = 0
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COALESCE(SUM(coins),0) FROM DiscordStat") as cur:
                row = await cur.fetchone()
                total_coins = int(row[0]) if row else 0
    except Exception as e:
        logging.error("api_stats_summary error exception=%s", type(e).__name__)
    return web.json_response({
        'member_count': member_count,
        'members_in_voice': in_voice,
        'boss_active': bool(boss.get('active', False)) if isinstance(boss, dict) else False,
        'treasury_balance': treasury.get('balance', 0) if isinstance(treasury, dict) else 0,
        'total_coins_in_circulation': total_coins,
    })


# ── Extra dashboard WRITE endpoints (token wajib) ─────────────────────────────
async def api_user_coins(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    name = _resolve_name(uid)
    if 'delta' in body:
        try:
            delta = int(body['delta'])
        except (ValueError, TypeError):
            return web.json_response({'error': 'delta must be an integer'}, status=400)
        await adjust_coins(uid, delta, name)
    elif 'set' in body:
        try:
            value = int(body['set'])
        except (ValueError, TypeError):
            return web.json_response({'error': 'set must be an integer'}, status=400)
        if value < 0:
            return web.json_response({'error': 'set must be >= 0'}, status=400)
        stat = await get_discord_stat(uid)
        await update_discord_stat(uid, name, value, stat['xp'], stat['level'], stat['lastDaily'])
        logging.info(f"[ECONOMY] (api) {name} ({uid}) coins SET -> {value}")
    else:
        return web.json_response({'error': 'provide "delta" or "set"'}, status=400)
    stat = await get_discord_stat(uid)
    await write_audit('coins', uid, f"{'delta' if 'delta' in body else 'set'}={body.get('delta', body.get('set'))} -> {stat['coins']}")
    return web.json_response({'status': 'success', 'id': uid, 'coins': stat['coins']})


async def api_user_xp(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
        delta = int(body['delta'])
    except (ValueError, TypeError, KeyError):
        return web.json_response({'error': 'provide integer "delta"'}, status=400)
    await add_xp(uid, _resolve_name(uid), delta)
    stat = await get_discord_stat(uid)
    await write_audit('xp', uid, f"delta={delta} -> xp {stat['xp']} lvl {stat['level']}")
    return web.json_response({'status': 'success', 'id': uid, 'xp': stat['xp'], 'level': stat['level']})


async def api_user_give_item(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    item_id = body.get('item_id')
    if item_id not in SHOP_ITEMS:
        return web.json_response({'error': f'unknown item_id (valid: {", ".join(SHOP_ITEMS)})'}, status=400)
    try:
        qty = int(body.get('qty', 1))
    except (ValueError, TypeError):
        return web.json_response({'error': 'qty must be an integer'}, status=400)
    if qty <= 0:
        return web.json_response({'error': 'qty must be > 0'}, status=400)
    users = await load_json('users.json')
    items = users.setdefault(uid, {}).setdefault('items', {})
    items[item_id] = items.get(item_id, 0) + qty
    await save_json('users.json', users)
    logging.info(f"[ITEM] (api) beri {qty}x {item_id} ke {uid}")
    await write_audit('give-item', uid, f"{qty}x {item_id}")
    return web.json_response({'status': 'success', 'id': uid, 'items': items})


async def api_user_reset_cooldown(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    ctype = (body.get('type') or '').lower()
    keymap = {'work': 'lastWork', 'rob': 'lastRob', 'pray': 'lastPray', 'curse': 'lastCurse'}
    valid = set(keymap) | {'daily', 'all'}
    if ctype not in valid:
        return web.json_response({'error': f'type must be one of {", ".join(sorted(valid))}'}, status=400)
    users = await load_json('users.json')
    u = users.setdefault(uid, {})
    targets = list(keymap) if ctype in ('all',) else ([ctype] if ctype in keymap else [])
    for t in targets:
        u.pop(keymap[t], None)
    await save_json('users.json', users)
    if ctype in ('daily', 'all'):
        await set_last_daily(uid, '', _resolve_name(uid))
    logging.info(f"[COOLDOWN] (api) reset '{ctype}' untuk {uid}")
    await write_audit('reset-cooldown', uid, f"type={ctype}")
    return web.json_response({'status': 'success', 'id': uid, 'reset': ctype})


async def api_boss_spawn(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    if ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE3_ENABLED:
        from economy.bosses import start_boss
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            result = await start_boss(
                DB_PATH, guild_id=ALLOWED_SERVER_ID, tier=body.get("tier", "normal"),
                start_key=body.get("request_id") or request.headers.get("X-Request-ID") or os.urandom(8).hex(),
                authorized=True,
            )
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        await write_audit('boss-spawn-v1', result['raid_id'], result['tier'])
        return web.json_response({'status': 'success', 'boss': result})
    boss_data = await load_json(BOSS_FILE)
    if boss_data.get('active', False):
        return web.json_response({'error': 'boss already active', 'boss': boss_data}, status=409)
    boss_data = {'active': True, 'hp': 10000, 'max_hp': 10000, 'name': '🐉 Naga Emas Koruptor'}
    await save_json(BOSS_FILE, boss_data)
    logging.info("[BOSS] (api) Boss raid dipaksa spawn lewat dashboard")
    await write_audit('boss-spawn', None, boss_data['name'])
    for guild in client.guilds:
        ch = get_announce_channel(guild, 'boss')
        if ch:
            client.loop.create_task(
                ch.send(f"⚠️ **BOSS RAID EVENT DIMULAI!** ⚠️\n**{boss_data['name']}** telah muncul dengan {boss_data['hp']} HP!\nKetik `!attack` untuk menyerang! Yang berhasil membunuhnya mendapat hadiah 5000 Koin!")
            )
    return web.json_response({'status': 'success', 'boss': boss_data})


async def api_boss_settle(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    if not (ECONOMY_V1_ENABLED and ECONOMY_PHASE2_ENABLED and ECONOMY_PHASE3_ENABLED):
        return web.json_response({'error': 'phase 3 disabled'}, status=409)
    from economy.bosses import settle_boss
    result = await settle_boss(DB_PATH, guild_id=ALLOWED_SERVER_ID, authorized=True)
    return web.json_response({
        'ok': result.ok, 'code': result.code, 'message': result.message,
        'transaction_id': result.transaction_id, 'replayed': result.replayed,
    }, status=200 if result.ok else 409)


async def api_announce(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    category = body.get('category')
    message = body.get('message')
    if category not in ANNOUNCE_CATEGORIES and category != 'default':
        return web.json_response({'error': f'category must be one of {", ".join(ANNOUNCE_CATEGORIES + ["default"])}'}, status=400)
    if not message:
        return web.json_response({'error': 'missing message'}, status=400)
    sent = 0
    for guild in client.guilds:
        ch = get_announce_channel(guild, category if category != 'default' else None)
        if ch:
            await send_long_message(ch, str(message))
            sent += 1
    await write_audit('announce', category, f"{sent} channel: {str(message)[:80]}")
    return web.json_response({'status': 'sent', 'channels': sent})


async def api_user_persona(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    persona = body.get('persona', '')
    personas = await load_json(PERSONAS_FILE)
    if persona and persona.strip():
        personas[uid] = persona.strip()
    else:
        personas.pop(uid, None)
    await save_json(PERSONAS_FILE, personas)
    await write_audit('persona', uid, persona[:80] if persona else 'reset')
    logging.info(f"[SETTING] (api) persona uid={uid} -> {persona[:40] if persona else 'reset'}")
    return web.json_response({'status': 'success', 'id': uid, 'persona': personas.get(uid)})


async def api_user_birthday(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    date = body.get('date', '')
    if date:
        date = str(date).strip()
        if len(date) != 5 or date[2] != '-':
            return web.json_response({'error': 'format harus DD-MM (cth. 25-12)'}, status=400)
        try:
            int(date[:2]); int(date[3:])
        except ValueError:
            return web.json_response({'error': 'format harus DD-MM (cth. 25-12)'}, status=400)
    users = await load_json('users.json')
    bdays = await load_json('birthdays.json')
    if date:
        users.setdefault(uid, {})['birthday'] = date
        bdays[uid] = date
    else:
        users.get(uid, {}).pop('birthday', None)
        bdays.pop(uid, None)
    await save_json('users.json', users)
    await save_json('birthdays.json', bdays)
    await write_audit('birthday', uid, date or 'hapus')
    return web.json_response({'status': 'success', 'id': uid, 'birthday': date or None})


async def api_user_bg(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    url = body.get('url', '')
    if url:
        url = str(url).strip()
        if not url.lower().startswith(('http://', 'https://')):
            return web.json_response({'error': 'URL harus http/https'}, status=400)
        if not await asyncio.to_thread(is_safe_remote_url, url):
            return web.json_response({'error': 'URL ditolak (host internal/privat)'}, status=400)
        test = await fetch_remote_image(url)
        if test is None:
            return web.json_response({'error': 'URL tidak mengarah ke gambar valid'}, status=400)
    items_data = await load_json(ITEMS_FILE)
    if url:
        items_data.setdefault(uid, {})['bg_url'] = url
    else:
        items_data.get(uid, {}).pop('bg_url', None)
    await save_json(ITEMS_FILE, items_data)
    await write_audit('bg', uid, url[:100] if url else 'hapus')
    return web.json_response({'status': 'success', 'id': uid, 'bg_url': url or None})


async def api_user_divorce(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    marriages = await load_json('marriages.json')
    partner = marriages.get(uid)
    if not partner:
        return web.json_response({'error': 'user tidak menikah'}, status=400)
    marriages.pop(uid, None)
    marriages.pop(partner, None)
    await save_json('marriages.json', marriages)
    await write_audit('divorce', uid, f'pasangan={partner}')
    logging.info(f"[SETTING] (api) paksa cerai uid={uid} pasangan={partner}")
    return web.json_response({'status': 'success', 'id': uid, 'divorced_from': partner})


async def api_user_bounty(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    amount = body.get('amount')
    if amount is None:
        return web.json_response({'error': 'sediakan "amount" (0 = hapus)'}, status=400)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return web.json_response({'error': 'amount harus integer'}, status=400)
    bounties = await load_json('bounties.json')
    if amount <= 0:
        bounties.pop(uid, None)
    else:
        bounties[uid] = amount
    await save_json('bounties.json', bounties)
    await write_audit('bounty', uid, f'amount={amount}')
    return web.json_response({'status': 'success', 'id': uid, 'bounty': bounties.get(uid, 0)})


async def api_user_reset_weekly(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    weekly = await load_json('weekly.json')
    weekly.pop(uid, None)
    await save_json('weekly.json', weekly)
    await write_audit('reset-weekly', uid, 'weekly direset')
    return web.json_response({'status': 'success', 'id': uid, 'weekly_claimed': None})


async def api_user_reset_quest(request):
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)
    quests = await load_json(QUESTS_FILE)
    quests.pop(uid, None)
    await save_json(QUESTS_FILE, quests)
    await write_audit('reset-quest', uid, 'quest direset')
    return web.json_response({'status': 'success', 'id': uid, 'quest': None})


async def api_user_reset_player(request):
    # Reset pemain — bisa full atau parsial berdasarkan field "targets" di body.
    # Body: {} atau {"targets": ["all"]} = reset semua.
    # Body: {"targets": ["coins","xp","items","crypto","rigs","pet","achievements",
    #         "games","marriage","bounty","persona","birthday","bg","weekly","quest","cooldowns"]}
    # Hanya reset field yang dipilih. DESTRUKTIF, hanya admin.
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    uid = request.match_info.get('id', '')
    if not uid.isdigit():
        return web.json_response({'error': 'invalid user id'}, status=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    ALL_TARGETS = ['coins', 'xp', 'items', 'crypto', 'rigs', 'pet', 'achievements',
                   'games', 'marriage', 'bounty', 'persona', 'birthday', 'bg',
                   'weekly', 'quest', 'cooldowns']
    targets = body.get('targets', ['all'])
    if 'all' in targets:
        targets = ALL_TARGETS

    # Validasi
    invalid = [t for t in targets if t not in ALL_TARGETS]
    if invalid:
        return web.json_response({'error': f'invalid targets: {invalid}. Valid: {ALL_TARGETS}'}, status=400)

    name = _resolve_name(uid)
    reset_done = []

    # DB: coins, xp, level
    if 'coins' in targets or 'xp' in targets:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                sets = []
                if 'coins' in targets:
                    sets.append("coins=0")
                if 'xp' in targets:
                    sets.append("xp=0, level=1, lastDaily=''")
                await db.execute(f"UPDATE DiscordStat SET {', '.join(sets)} WHERE id=?", (uid,))
                await db.commit()
        except Exception as e:
            logging.error("api_user_reset_player DB error exception=%s", type(e).__name__)
        if 'coins' in targets:
            reset_done.append('coins')
        if 'xp' in targets:
            reset_done.append('xp/level')

    # users.json fields
    users = await load_json('users.json')
    u = users.get(uid, {})
    json_fields = {
        'items': 'items', 'crypto': 'crypto', 'rigs': 'rigs',
        'pet': 'pet', 'achievements': 'achievements', 'games': 'games',
    }
    cooldown_keys = ['lastWork', 'lastRob', 'lastPray', 'lastCurse']
    changed_users = False
    for target, key in json_fields.items():
        if target in targets and key in u:
            if isinstance(u[key], dict):
                u[key] = {}
            elif isinstance(u[key], list):
                u[key] = []
            else:
                u[key] = None
            reset_done.append(target)
            changed_users = True
    if 'cooldowns' in targets:
        for ck in cooldown_keys:
            u.pop(ck, None)
        reset_done.append('cooldowns')
        changed_users = True
    if changed_users:
        users[uid] = u
        await save_json('users.json', users)

    # Marriage
    if 'marriage' in targets:
        marriages = await load_json('marriages.json')
        partner = marriages.pop(uid, None)
        if partner:
            marriages.pop(partner, None)
        await save_json('marriages.json', marriages)
        reset_done.append('marriage')

    # Bounty
    if 'bounty' in targets:
        bounties = await load_json('bounties.json')
        bounties.pop(uid, None)
        await save_json('bounties.json', bounties)
        reset_done.append('bounty')

    # Persona
    if 'persona' in targets:
        personas = await load_json(PERSONAS_FILE)
        personas.pop(uid, None)
        await save_json(PERSONAS_FILE, personas)
        reset_done.append('persona')

    # Birthday
    if 'birthday' in targets:
        bdays = await load_json('birthdays.json')
        bdays.pop(uid, None)
        await save_json('birthdays.json', bdays)
        reset_done.append('birthday')

    # Background
    if 'bg' in targets:
        items_data = await load_json(ITEMS_FILE)
        items_data.get(uid, {}).pop('bg_url', None)
        await save_json(ITEMS_FILE, items_data)
        reset_done.append('bg')

    # Weekly
    if 'weekly' in targets:
        weekly = await load_json('weekly.json')
        weekly.pop(uid, None)
        await save_json('weekly.json', weekly)
        reset_done.append('weekly')

    # Quest
    if 'quest' in targets:
        quests = await load_json(QUESTS_FILE)
        quests.pop(uid, None)
        await save_json(QUESTS_FILE, quests)
        reset_done.append('quest')

    await write_audit('reset-player', uid, f'reset: {", ".join(reset_done)}')
    logging.info(f"[ADMIN] RESET pemain {name} ({uid}): {', '.join(reset_done)}")

    return web.json_response({'status': 'success', 'id': uid, 'reset': reset_done})


async def api_reset_all_players(request):
    # Reset SEMUA pemain sekaligus (koin, xp, level, items, crypto, dll).
    # TIDAK menghapus config bot (announce channels, config.json).
    # Ini operasi DESTRUKTIF tingkat server — admin darurat only.
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)

    player_count = 0
    try:
        # Reset semua DiscordStat
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT COUNT(*) FROM DiscordStat")
            row = await cur.fetchone()
            player_count = row[0] if row else 0
            await db.execute("UPDATE DiscordStat SET coins=0, xp=0, level=1, lastDaily=''")
            await db.commit()
    except Exception as e:
        logging.error("api_reset_all_players DB error exception=%s", type(e).__name__)

    # Reset semua users.json (hapus data game semua orang)
    await save_json('users.json', {})

    # Reset marriages
    await save_json('marriages.json', {})

    # Reset bounties
    await save_json('bounties.json', {})

    # Reset personas
    await save_json(PERSONAS_FILE, {})

    # Reset birthdays
    await save_json('birthdays.json', {})

    # Reset items/bg
    await save_json(ITEMS_FILE, {})

    # Reset weekly
    await save_json('weekly.json', {})

    # Reset quests
    await save_json(QUESTS_FILE, {})

    # TIDAK reset: config.json, announce_channels, treasury, market, boss

    await write_audit('reset-all-players', None, f'{player_count} pemain direset')
    logging.info(f"[ADMIN] RESET ALL PLAYERS: {player_count} pemain direset total")

    return web.json_response({'status': 'success', 'players_reset': player_count})


async def api_audit(request):
    # Audit log aksi admin. Token wajib (isinya jejak aksi sensitif).
    if not require_token(request):
        return web.json_response({'error': 'unauthorized'}, status=401)
    try:
        limit = int(request.query.get('limit', '100'))
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 500))
    entries = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, ts, action, target_id, detail, source FROM AuditLog ORDER BY id DESC LIMIT ?",
                (limit,)) as cur:
                rows = await cur.fetchall()
        for r in rows:
            entries.append({
                'id': r[0], 'ts': r[1], 'action': r[2],
                'target_id': r[3], 'detail': r[4], 'source': r[5],
            })
    except Exception as e:
        logging.error("api_audit error exception=%s", type(e).__name__)
        return web.json_response({'error': 'internal error'}, status=500)
    return web.json_response({'limit': limit, 'entries': entries})


async def api_level_distribution(request):
    # Distribusi jumlah pemain per level (untuk bar chart).
    buckets = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT level, COUNT(*) FROM DiscordStat GROUP BY level ORDER BY level") as cur:
                rows = await cur.fetchall()
        buckets = [{'level': r[0], 'count': r[1]} for r in rows]
    except Exception as e:
        logging.error("api_level_distribution error exception=%s", type(e).__name__)
        return web.json_response({'error': 'internal error'}, status=500)
    return web.json_response({'buckets': buckets})


async def api_bot_stats(request):
    # Statistik detail bot: latency, uptime, info guild, agregat ekonomi.
    guild = client.get_guild(ALLOWED_SERVER_ID)

    # Latency gateway (ms)
    latency_ms = None
    try:
        if client.latency and client.latency == client.latency:  # bukan NaN
            latency_ms = round(client.latency * 1000)
    except Exception:
        latency_ms = None

    # Uptime
    uptime_seconds = int((datetime.utcnow() - BOT_START_TIME).total_seconds())

    # Info guild
    guild_info = None
    if guild:
        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots if guild.member_count else None
        in_voice = sum(len([m for m in vc.members if not m.bot]) for vc in guild.voice_channels)
        guild_info = {
            'name': guild.name,
            'icon_url': str(guild.icon.url) if guild.icon else None,
            'member_count': guild.member_count,
            'humans': humans,
            'bots': bots,
            'members_in_voice': in_voice,
            'boosts': guild.premium_subscription_count,
            'boost_tier': guild.premium_tier,
            'text_channels': len(guild.text_channels),
            'voice_channels': len(guild.voice_channels),
            'roles': len(guild.roles),
        }

    # Agregat ekonomi dari DiscordStat
    economy = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*), COALESCE(SUM(coins),0), COALESCE(AVG(level),0), COALESCE(MAX(level),0), COALESCE(SUM(xp),0) FROM DiscordStat") as cur:
                row = await cur.fetchone()
        economy = {
            'players': row[0],
            'total_coins': int(row[1]),
            'average_level': round(row[2], 2),
            'max_level': row[3],
            'total_xp': int(row[4]),
        }
    except Exception as e:
        logging.error("api_bot_stats economy error exception=%s", type(e).__name__)

    treasury = await load_json(TREASURY_FILE)
    boss = await load_json(BOSS_FILE)

    # Jumlah kategori announce yang sudah dikonfigurasi
    cfg = _load_config()
    announce = cfg.get('announce_channels', {}) if isinstance(cfg, dict) else {}
    configured = sum(1 for k in (['default'] + ANNOUNCE_CATEGORIES) if announce.get(k))

    return web.json_response({
        'online': guild is not None,
        'latency_ms': latency_ms,
        'uptime_seconds': uptime_seconds,
        'guild': guild_info,
        'economy': economy,
        'treasury_balance': treasury.get('balance', 0) if isinstance(treasury, dict) else 0,
        'boss_active': bool(boss.get('active', False)) if isinstance(boss, dict) else False,
        'commands_registered': len(tree.get_commands()),
        'announce_channels_configured': configured,
        'prefix': BOT_PREFIX,
    })


def _json_without_duplicates(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise DashboardSecurityError('invalid_request', 400)
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DashboardSecurityError('invalid_request', 400)
    if not isinstance(value, dict):
        raise DashboardSecurityError('invalid_request', 400)
    canonical_json(value)
    return value


async def _internal_payload(request):
    if request.headers.get('Origin'):
        raise DashboardSecurityError('forbidden', 403)
    if request.content_type != 'application/json':
        raise DashboardSecurityError('invalid_request', 415)
    raw = await request.read()
    if len(raw) > 65536:
        raise DashboardSecurityError('invalid_request', 413)
    return _json_without_duplicates(raw)


def _assert_keys(payload, allowed, required=()):
    if set(payload) - set(allowed) or any(key not in payload for key in required):
        raise DashboardSecurityError('invalid_request', 400)


async def _current_dashboard_member(guild_id, actor_id):
    if str(guild_id) != str(ALLOWED_SERVER_ID):
        return None, False
    guild = client.get_guild(int(guild_id))
    if guild is None:
        return None, False
    member = guild.get_member(int(actor_id))
    return member, bool(member and member.guild_permissions.administrator)


@asynccontextmanager
async def _signed_internal(request, payload, *, permission='DASHBOARD_VIEW', session_required=True,
                           rate_limit=120):
    if not DASHBOARD_INTERNAL_SIGNING_KEY or not DASHBOARD_INTERNAL_KEY_ID:
        raise DashboardSecurityError('capability_unavailable', 503)
    envelope = envelope_from_headers(request.headers)
    if envelope.key_id != DASHBOARD_INTERNAL_KEY_ID or envelope.guild_id != str(ALLOWED_SERVER_ID):
        raise DashboardSecurityError('unauthenticated', 401)
    verify_envelope_signature(
        envelope, request.headers.get('X-W2E-Signature'), DASHBOARD_INTERNAL_SIGNING_KEY,
        method=request.method, route=request.path, payload=payload,
    )
    db = await aiosqlite.connect(DB_PATH, isolation_level=None)
    try:
        await db.execute('PRAGMA foreign_keys=ON')
        await db.execute('BEGIN IMMEDIATE')
        if not await phase9a_capability(db):
            raise DashboardSecurityError('capability_unavailable', 503)
        expected_fingerprint = hashlib.sha256(DASHBOARD_INTERNAL_SIGNING_KEY.encode('utf-8')).hexdigest()
        async with db.execute(
            "SELECT fingerprintSha256 FROM DashboardSigningKeyVersion WHERE keyId=? "
            "AND purpose='INTERNAL_REQUEST' AND status='ACTIVE'", (envelope.key_id,),
        ) as cursor:
            key_row = await cursor.fetchone()
        if not key_row or not hmac.compare_digest(key_row[0], expected_fingerprint):
            raise DashboardSecurityError('capability_unavailable', 503)
        await consume_internal_nonce(db, envelope)
        session = None
        if session_required:
            member, administrator = await _current_dashboard_member(envelope.guild_id, envelope.actor_id)
            session = await validate_session(
                db, token_hash=envelope.session_token_hash, required_permission=permission,
                discord_member=member is not None, discord_administrator=administrator,
                expected_version=envelope.session_version,
            )
            if session['guildId'] != envelope.guild_id or session['userId'] != envelope.actor_id:
                raise DashboardSecurityError('unauthenticated', 401)
            await enforce_rate_limit(
                db, scope_hash=envelope.session_token_hash, route_group='internal',
                limit=rate_limit, window_seconds=60,
            )
        yield db, envelope, session
        await db.commit()
    except DashboardSecurityError as exc:
        try:
            await db.rollback()
            await db.execute('BEGIN IMMEDIATE')
            await record_security_event(
                db, event_type='INTERNAL_REQUEST_REJECTED', code=exc.code, route=request.path,
                guild_id=getattr(envelope, 'guild_id', None), actor_id=getattr(envelope, 'actor_id', None),
                request_id=getattr(envelope, 'request_id', None),
            )
            await db.commit()
        except Exception:
            await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def public_health(request):
    return web.json_response({'status': 'ok'})


async def dashboard_root(request):
    if DASHBOARD_PUBLIC_URL.startswith('https://'):
        raise web.HTTPTemporaryRedirect(f"{DASHBOARD_PUBLIC_URL}/login")
    return web.json_response({'error': 'capability_unavailable'}, status=503)


async def legacy_dashboard_read_disabled(request):
    return web.json_response({'error': 'legacy_dashboard_read_disabled'}, status=410)


async def legacy_dashboard_write_disabled(request):
    return web.json_response({'error': 'legacy_dashboard_write_disabled'}, status=410)


async def internal_oauth_start(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'stateHash', 'pkceChallenge', 'ipHash', 'returnPath'},
                 {'stateHash', 'pkceChallenge', 'ipHash'})
    async with _signed_internal(request, payload, session_required=False) as (db, envelope, _):
        await enforce_rate_limit(db, scope_hash=str(payload['ipHash']), route_group='login',
                                 limit=10, window_seconds=600)
        attempt_id = await create_oauth_attempt(
            db, state_hash=str(payload['stateHash']), pkce_challenge=str(payload['pkceChallenge']),
            ip_hash=str(payload['ipHash']), return_path=str(payload.get('returnPath', '/')),
        )
        return web.json_response({'attemptId': attempt_id, 'expiresIn': 600})


async def internal_session_establish(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'tokenHash', 'stateHash', 'pkceChallenge', 'ipHash'},
                 {'tokenHash', 'stateHash', 'pkceChallenge', 'ipHash'})
    async with _signed_internal(request, payload, session_required=False) as (db, envelope, _):
        from economy.dashboard_auth import consume_oauth_attempt
        attempt = await consume_oauth_attempt(db, state_hash=str(payload['stateHash']),
                                              pkce_challenge=str(payload['pkceChallenge']))
        if not hmac.compare_digest(str(attempt['ipHash']), str(payload['ipHash'])):
            raise DashboardSecurityError('unauthenticated', 401)
        await enforce_rate_limit(db, scope_hash=str(payload['ipHash']), route_group='callback',
                                 limit=20, window_seconds=600)
        member, administrator = await _current_dashboard_member(envelope.guild_id, envelope.actor_id)
        if member is None:
            raise DashboardSecurityError('forbidden', 403)
        session_id = await establish_session(
            db, guild_id=envelope.guild_id, user_id=envelope.actor_id,
            token_hash=str(payload['tokenHash']), session_key_id=DASHBOARD_SESSION_KEY_ID,
            discord_administrator=administrator,
        )
        return web.json_response({'sessionId': session_id, 'sessionVersion': 0})


async def internal_session_validate(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, set())
    async with _signed_internal(request, payload, session_required=False) as (db, envelope, _):
        async with db.execute(
            "SELECT guildId,userId FROM DashboardSession WHERE tokenHash=? AND status='ACTIVE'",
            (envelope.session_token_hash,),
        ) as cursor:
            identity = await cursor.fetchone()
        if not identity or identity[0] != envelope.guild_id:
            raise DashboardSecurityError('unauthenticated', 401)
        member, administrator = await _current_dashboard_member(identity[0], identity[1])
        session = await validate_session(
            db, token_hash=envelope.session_token_hash, required_permission='DASHBOARD_VIEW',
            discord_member=member is not None, discord_administrator=administrator,
            expected_version=envelope.session_version,
        )
        return web.json_response({'session': session})


async def internal_csrf_issue(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'method', 'canonicalRoute', 'requestId'},
                 {'method', 'canonicalRoute', 'requestId'})
    async with _signed_internal(request, payload) as (db, _, session):
        if not DASHBOARD_SESSION_HASH_KEY:
            raise DashboardSecurityError('capability_unavailable', 503)
        result = await issue_csrf(
            db, session_id=session['sessionId'], method=str(payload['method']),
            canonical_route=str(payload['canonicalRoute']), request_id=str(payload['requestId']),
            session_hash_key=DASHBOARD_SESSION_HASH_KEY,
        )
        return web.json_response(result)


async def internal_session_logout(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'requestId', 'csrfToken'}, {'requestId', 'csrfToken'})
    async with _signed_internal(request, payload) as (db, _, session):
        await consume_csrf(
            db, raw_token=str(payload['csrfToken']), session_id=session['sessionId'], method='POST',
            canonical_route='/api/auth/logout', request_id=str(payload['requestId']),
            session_hash_key=DASHBOARD_SESSION_HASH_KEY,
        )
        await revoke_session(db, session_id=session['sessionId'], reason_code='USER_LOGOUT',
                             expected_version=session['version'])
        return web.json_response({'status': 'logged_out'})


async def internal_session_rotate(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'newTokenHash'}, {'newTokenHash'})
    async with _signed_internal(request, payload) as (db, _, session):
        version = await rotate_session(
            db, session_id=session['sessionId'], new_token_hash=str(payload['newTokenHash']),
            expected_version=session['version'],
        )
        return web.json_response({'sessionId': session['sessionId'], 'sessionVersion': version})


async def internal_operators_list(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'limit', 'cursor'})
    async with _signed_internal(request, payload, permission='DASHBOARD_SECURITY_ADMIN') as (db, _, _):
        limit = max(1, min(int(payload.get('limit', 100)), 200))
        async with db.execute(
            "SELECT assignmentId,guildId,userId,permissionClass,status,grantedAt,revokedAt,version "
            "FROM DashboardOperatorPermission ORDER BY grantedAt DESC,assignmentId DESC LIMIT ?", (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return web.json_response({'operators': [dict(zip(
            ('assignmentId','guildId','userId','permissionClass','status','grantedAt','revokedAt','version'), row
        )) for row in rows]})


async def _internal_permission_change(request, action):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'requestId','targetUserId','permissionClass','expectedVersion','csrfToken'},
                 {'requestId','targetUserId','permissionClass','expectedVersion','csrfToken'})
    async with _signed_internal(request, payload, permission='DASHBOARD_SECURITY_ADMIN', rate_limit=10) as (db, envelope, session):
        browser_route = f"/api/admin/operators/{action.lower()}"
        await consume_csrf(
            db, raw_token=str(payload['csrfToken']), session_id=session['sessionId'], method='POST',
            canonical_route=browser_route, request_id=str(payload['requestId']),
            session_hash_key=DASHBOARD_SESSION_HASH_KEY,
        )
        receipt = await change_permission(
            db, action=action, guild_id=envelope.guild_id, actor_id=envelope.actor_id,
            target_user_id=str(payload['targetUserId']), permission_class=str(payload['permissionClass']),
            request_id=str(payload['requestId']), expected_version=int(payload['expectedVersion']),
            source_route=browser_route,
        )
        return web.json_response(receipt)


async def internal_operators_grant(request):
    return await _internal_permission_change(request, 'GRANT')


async def internal_operators_revoke(request):
    return await _internal_permission_change(request, 'REVOKE')


async def internal_session_revoke(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'requestId','sessionId','expectedVersion','csrfToken'},
                 {'requestId','sessionId','expectedVersion','csrfToken'})
    async with _signed_internal(request, payload, permission='DASHBOARD_SECURITY_ADMIN', rate_limit=10) as (db, _, session):
        await consume_csrf(
            db, raw_token=str(payload['csrfToken']), session_id=session['sessionId'], method='POST',
            canonical_route='/api/admin/sessions/revoke', request_id=str(payload['requestId']),
            session_hash_key=DASHBOARD_SESSION_HASH_KEY,
        )
        receipt = await revoke_dashboard_session(
            db, guild_id=session['guildId'], actor_id=session['userId'],
            target_session_id=str(payload['sessionId']), request_id=str(payload['requestId']),
            expected_version=int(payload['expectedVersion']), source_route='/api/admin/sessions/revoke',
        )
        return web.json_response(receipt)


async def internal_operator_audit(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'limit'})
    async with _signed_internal(request, payload, permission='OPERATOR_AUDIT_READ') as (db, _, _):
        limit = max(1, min(int(payload.get('limit', 100)), 200))
        async with db.execute(
            "SELECT auditId,executorUserId,permissionClass,operationType,targetType,targetId,requestId,"
            "resultStatus,createdAt FROM DashboardOperatorAudit ORDER BY createdAt DESC,auditId DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        keys = ('auditId','executorUserId','permissionClass','operationType','targetType','targetId',
                'requestId','resultStatus','createdAt')
        return web.json_response({'entries': [dict(zip(keys, row)) for row in rows]})


async def internal_security_events(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'limit'})
    async with _signed_internal(request, payload, permission='DASHBOARD_SECURITY_ADMIN') as (db, _, _):
        limit = max(1, min(int(payload.get('limit', 100)), 200))
        async with db.execute(
            "SELECT eventId,eventType,safeErrorCode,route,createdAt FROM DashboardSecurityEvent "
            "ORDER BY createdAt DESC,eventId DESC LIMIT ?", (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return web.json_response({'events': [dict(zip(
            ('eventId','eventType','safeErrorCode','route','createdAt'), row
        )) for row in rows]})


async def internal_phase9a_health(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, set())
    async with _signed_internal(request, payload) as (db, _, _):
        async with db.execute(
            "SELECT purpose,COUNT(*) FROM DashboardSigningKeyVersion WHERE status='ACTIVE' GROUP BY purpose"
        ) as cursor:
            keys = {row[0]: row[1] for row in await cursor.fetchall()}
        return web.json_response({
            'schemaCapable': True,
            'internalRequestKeyReady': keys.get('INTERNAL_REQUEST') == 1,
            'sessionHashKeyReady': keys.get('SESSION_HASH') == 1,
            'migrationChecksum': PHASE9A_SCHEMA_CHECKSUM,
        })


class _InternalReadRequest:
    def __init__(self, query=None, params=None):
        self.query = {str(k): str(v) for k, v in (query or {}).items()}
        self.match_info = {str(k): str(v) for k, v in (params or {}).items()}


INTERNAL_READ_HANDLERS = {
    'server': get_server_data, 'radar': api_radar, 'channels': api_channels,
    'announce-config': get_announce_config_api, 'leaderboard': api_leaderboard,
    'user': api_user, 'market': api_market, 'treasury': api_treasury, 'boss': api_boss,
    'economy/stats': api_economy_stats, 'economy/supply': api_economy_v1_supply,
    'economy/profile': api_economy_v1_profile, 'economy/marketplace': api_marketplace_v1_status,
    'economy/casino': api_casino_v1_status, 'economy/crypto': api_crypto_v1_status,
    'economy/mining': api_mining_v1_status, 'economy/phase8': api_phase8_status,
    'marriages': api_marriages, 'stats/summary': api_stats_summary,
    'bot/stats': api_bot_stats, 'economy/level-distribution': api_level_distribution,
}


async def internal_dashboard_read(request):
    payload = await _internal_payload(request)
    _assert_keys(payload, {'query','params'})
    resource = request.match_info.get('resource', '')
    handler = INTERNAL_READ_HANDLERS.get(resource)
    if handler is None:
        raise DashboardSecurityError('invalid_request', 404)
    query = payload.get('query', {})
    params = payload.get('params', {})
    if not isinstance(query, dict) or not isinstance(params, dict):
        raise DashboardSecurityError('invalid_request', 400)
    allowed_query = {'sort','limit'} if resource == 'leaderboard' else set()
    allowed_params = {'id'} if resource in {'user','economy/profile'} else set()
    if set(query) - allowed_query or set(params) - allowed_params:
        raise DashboardSecurityError('invalid_request', 400)
    async with _signed_internal(request, payload) as (_, _, _):
        return await handler(_InternalReadRequest(query, params))


def build_web_application():
    app = web.Application(middlewares=[cors_middleware], client_max_size=65536)
    app.router.add_options('/{tail:.*}', handle_options)
    app.router.add_get('/healthz', public_health)
    app.router.add_get('/', dashboard_root)
    for route in (
        '/api/config','/api/server','/api/radar','/api/channels','/api/announce-config',
        '/api/leaderboard','/api/user/{id}','/api/market','/api/treasury','/api/boss',
        '/api/economy/stats','/api/economy/v1-supply','/api/economy/v1-profile/{id}',
        '/api/economy/v1-marketplace','/api/economy/v1-casino','/api/economy/v1-crypto',
        '/api/economy/v1-mining','/api/economy/v1-phase8','/api/marriages',
        '/api/stats/summary','/api/bot/stats','/api/economy/level-distribution','/api/audit',
    ):
        app.router.add_get(route, legacy_dashboard_read_disabled)
    for route in (
        '/api/config','/api/announce-config','/api/broadcast','/api/announce',
        '/api/user/{id}/coins','/api/user/{id}/xp','/api/user/{id}/give-item',
        '/api/user/{id}/reset-cooldown','/api/user/{id}/persona','/api/user/{id}/birthday',
        '/api/user/{id}/bg','/api/user/{id}/divorce','/api/user/{id}/bounty',
        '/api/user/{id}/reset-weekly','/api/user/{id}/reset-quest','/api/user/{id}/reset',
        '/api/reset-all-players','/api/boss/spawn','/api/boss/settle',
        '/api/economy/v1-marketplace/action',
    ):
        app.router.add_post(route, legacy_dashboard_write_disabled)
    app.router.add_post('/internal/phase9a/oauth/start', internal_oauth_start)
    app.router.add_post('/internal/phase9a/session/establish', internal_session_establish)
    app.router.add_post('/internal/phase9a/session/validate', internal_session_validate)
    app.router.add_post('/internal/phase9a/session/rotate', internal_session_rotate)
    app.router.add_post('/internal/phase9a/session/logout', internal_session_logout)
    app.router.add_post('/internal/phase9a/session/revoke', internal_session_revoke)
    app.router.add_post('/internal/phase9a/csrf/issue', internal_csrf_issue)
    app.router.add_post('/internal/phase9a/operators/list', internal_operators_list)
    app.router.add_post('/internal/phase9a/operators/grant', internal_operators_grant)
    app.router.add_post('/internal/phase9a/operators/revoke', internal_operators_revoke)
    app.router.add_post('/internal/phase9a/audit/list', internal_operator_audit)
    app.router.add_post('/internal/phase9a/security-events/list', internal_security_events)
    app.router.add_post('/internal/phase9a/health', internal_phase9a_health)
    app.router.add_post('/internal/phase9a/read/{resource:.+}', internal_dashboard_read)
    return app


async def start_web_server():
    app = build_web_application()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8081)
    await site.start()
    logging.info("Bot API started on port 8081")
    logging.info("Legacy dashboard routes disabled; Phase 9A internal routes fail closed.")

@client.event
async def on_voice_state_update(member, before, after):
    for callback in list(VOICE_STATE_CALLBACKS):
        try:
            await callback(member, before, after)
        except Exception as exc:
            logging.error("Voice state callback failed callback=%s exception=%s",
                          getattr(callback, "__name__", "callback"), type(exc).__name__)
    if before.channel is None and after.channel is not None:
        voice_join_times[member.id] = datetime.now()
        # 👑 Booster Voice Intro

        if member.premium_since and not member.bot:
            guild = member.guild
            notify_channel = get_announce_channel(guild, 'booster')

            if notify_channel:
                intros = [
                    f"👑 **{member.display_name}** (Donatur) telah bergabung ke VC **{after.channel.name}**.",
                    f"✨ **{member.display_name}** (Server Booster) telah bergabung ke VC **{after.channel.name}**.",
                    f"💎 **{member.display_name}** telah bergabung ke VC **{after.channel.name}**.",
                ]
                await notify_channel.send(random.choice(intros))

    elif before.channel is not None and after.channel is None:
        if member.id in voice_join_times:
            join_time = voice_join_times[member.id]
            del voice_join_times[member.id]
            
            # VC Farming Leveling System
            duration = datetime.now() - join_time
            minutes = int(duration.total_seconds() // 60)
            
            if minutes > 0 and not member.bot:
                uid = str(member.id)
                users = await load_json('users.json')
                if uid not in users:
                    users[uid] = {'items': {}, 'achievements': [], 'total_vc_minutes': 0}

                # Tambah XP & Koin
                xp_gained = minutes * 10
                coins_gained = minutes * 5
                users[uid]['total_vc_minutes'] = users[uid].get('total_vc_minutes', 0) + minutes

                # Koin masuk ke dompet asli (DiscordStat.coins) secara atomik,
                # bukan ke users.json['balance'] yang dulu cuma write-only.
                await add_coins(uid, coins_gained, member.display_name)

                # Check No-Lifer Achievement
                if users[uid]['total_vc_minutes'] >= 1440 and 'no_lifer' not in users[uid].get('achievements', []):
                    if 'achievements' not in users[uid]: users[uid]['achievements'] = []
                    users[uid]['achievements'].append('no_lifer')
                    # Send congrats message
                    guild = member.guild
                    for ch in guild.text_channels:
                        if ch.permissions_for(guild.me).send_messages:
                            asyncio.create_task(ch.send(f"🏆 **ACHIEVEMENT UNLOCKED!** {member.mention} mendapatkan gelar **🧟‍♂️ No-Lifer** karena sudah menghabiskan total 24 jam di Voice Channel!"))
                            break

                await save_json('users.json', users)

                # Tambah XP secara atomik (level-up di-resolve lazy oleh get_discord_stat).
                await add_xp(uid, member.display_name, xp_gained)

                # Optional: Send DM or channel message for XP gained if you want, but it might be spammy.
                logging.info(f"{member.display_name} earned {xp_gained} XP and {coins_gained} Coins from {minutes} mins in VC.")

async def send_long_message(channel, message):
    if len(message) <= 2000:
        await channel.send(message)
    else:
        for i in range(0, len(message), 2000):
            await channel.send(message[i:i+2000])

async def write_to_memory(content):
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO ChatMemory (timestamp, content) VALUES (?, ?)", (now, content))
            # Keep only the last 2000 log entries to prevent DB bloat
            await db.execute("DELETE FROM ChatMemory WHERE id NOT IN (SELECT id FROM ChatMemory ORDER BY id DESC LIMIT 2000)")
            await db.commit()
    except Exception as e:
        logging.error("Error saving chat memory to DB exception=%s", type(e).__name__)


# ── Audit log ────────────────────────────────────────────────────────────────
async def write_audit(action, target_id=None, detail=None, source="api"):
    # Catat aksi admin/write ke tabel AuditLog. Best-effort; jangan sampai gagal
    # audit menggagalkan aksi utamanya.
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO AuditLog (ts, action, target_id, detail, source) VALUES (?, ?, ?, ?, ?)",
                (now, action, str(target_id) if target_id is not None else None, detail, source))
            # Batasi 1000 baris terbaru biar DB tidak membengkak.
            await db.execute("DELETE FROM AuditLog WHERE id NOT IN (SELECT id FROM AuditLog ORDER BY id DESC LIMIT 1000)")
            await db.commit()
    except Exception as e:
        logging.error("write_audit error exception=%s", type(e).__name__)


def _audit_now():
    return datetime.utcnow().isoformat() + "Z"


def _audit_safe_text(value, max_length=180):
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_length:
        return text[: max_length - 1].rstrip() + "…"
    return text


def _audit_display(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [_audit_display(item) for item in value]
        return "\n".join(part for part in parts if part) or None
    mention = getattr(value, "mention", None)
    if mention:
        return mention
    display_name = getattr(value, "display_name", None) or getattr(value, "global_name", None) or getattr(value, "name", None)
    if display_name:
        return f"@{display_name}" if isinstance(value, (discord.Member, discord.User)) else str(display_name)
    text = str(value).strip()
    return text or None


async def get_deal_audit_log_config(guild_id):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guildId, channelId, enabled, createdAt, updatedAt FROM dealAuditLogConfig WHERE guildId=?",
                (str(guild_id),),
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None
        return {
            "guildId": row[0],
            "channelId": row[1],
            "enabled": bool(row[2]),
            "createdAt": row[3],
            "updatedAt": row[4],
        }
    except Exception as e:
        logging.error("get_deal_audit_log_config error exception=%s", type(e).__name__)
        return None


async def set_deal_audit_log_config(guild_id, channel_id, enabled=True):
    now = _audit_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO dealAuditLogConfig (guildId, channelId, enabled, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                channelId=excluded.channelId,
                enabled=excluded.enabled,
                updatedAt=excluded.updatedAt
            """,
            (str(guild_id), str(channel_id) if channel_id is not None else None, int(bool(enabled)), now, now),
        )
        await db.commit()
    return await get_deal_audit_log_config(guild_id)


async def disable_deal_audit_log(guild_id):
    now = _audit_now()
    current = await get_deal_audit_log_config(guild_id)
    channel_id = current.get("channelId") if current else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO dealAuditLogConfig (guildId, channelId, enabled, createdAt, updatedAt)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                enabled=0,
                updatedAt=excluded.updatedAt
            """,
            (str(guild_id), str(channel_id) if channel_id is not None else None, now, now),
        )
        await db.commit()
    return await get_deal_audit_log_config(guild_id)


async def send_deal_audit_log(
    guild,
    action,
    actor=None,
    target=None,
    deal_id=None,
    vouch_id=None,
    report_id=None,
    reason=None,
    note=None,
    metadata=None,
):
    try:
        if not guild:
            return
        config = await get_deal_audit_log_config(guild.id)
        if not config or not config.get("enabled") or not config.get("channelId"):
            return
        channel = guild.get_channel(int(config["channelId"]))
        if not channel:
            try:
                channel = await guild.fetch_channel(int(config["channelId"]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                return
        embed = discord.Embed(title="🛡️ Staff Audit Log", color=0x5865F2)
        embed.timestamp = datetime.utcnow()
        fields = [
            ("Action", _audit_safe_text(action, 100)),
            ("Actor", _audit_display(actor)),
            ("Target", _audit_display(target)),
            ("Deal ID", _audit_safe_text(deal_id, 80)),
            ("Vouch ID", _audit_safe_text(vouch_id, 40)),
            ("Report ID", _audit_safe_text(report_id, 40)),
            ("Reason", _audit_safe_text(reason)),
            ("Note", _audit_safe_text(note)),
        ]
        safe_metadata_keys = {"status", "old_status", "new_status", "final_status"}
        if isinstance(metadata, dict):
            safe_lines = []
            for key, value in metadata.items():
                key_text = str(key).strip().lower()
                if key_text in safe_metadata_keys:
                    safe_value = _audit_safe_text(value, 80)
                    if safe_value:
                        safe_lines.append(f"{key}: {safe_value}")
            if safe_lines:
                fields.append(("Metadata", "\n".join(safe_lines)))
        for name, value in fields:
            if value:
                embed.add_field(name=name, value=str(value), inline=False)
        embed.set_footer(text="W2E Deal Audit")
        await channel.send(embed=embed)
    except Exception as e:
        logging.error("send_deal_audit_log error exception=%s", type(e).__name__)


DEAL_STATUS_PENDING_FORM = "Menunggu Form"
DEAL_STATUS_WAITING_FUNDS = "Menunggu Dana Masuk"
DEAL_STATUS_FUNDS_RECEIVED = "Dana Masuk"
DEAL_STATUS_ITEM_SENT = "Item Sent"
DEAL_STATUS_BUYER_CONFIRMED = "Buyer Confirmed"
DEAL_STATUS_COMPLETED = "Completed"
DEAL_STATUS_DISPUTED = "Disputed"
DEAL_STATUS_CANCELLED = "Cancelled"
DEAL_ACTIVE_STATUSES = (
    DEAL_STATUS_PENDING_FORM,
    DEAL_STATUS_WAITING_FUNDS,
    DEAL_STATUS_FUNDS_RECEIVED,
    DEAL_STATUS_ITEM_SENT,
    DEAL_STATUS_BUYER_CONFIRMED,
    DEAL_STATUS_DISPUTED,
)
DEAL_CLOSED_STATUSES = ("Completed", DEAL_STATUS_CANCELLED, "Expired", "Voided/Duplicate")
DEAL_REQUIRED_PERMISSION_NAMES = (
    "view_channel",
    "send_messages",
    "read_message_history",
    "attach_files",
    "embed_links",
    "use_application_commands",
)
DEAL_SETUP_INCOMPLETE_MESSAGE = "Setup belum lengkap. Admin harus mengatur role staff deal terlebih dahulu."


def _load_deal_system_phase():
    try:
        phase = int(os.getenv("DEAL_SYSTEM_PHASE", "6"))
    except (TypeError, ValueError):
        phase = 6
    return min(6, max(1, phase))


DEAL_SYSTEM_PHASE = _load_deal_system_phase()
logging.info(f"[Deal System] DEAL_SYSTEM_PHASE = {DEAL_SYSTEM_PHASE}")


def deal_phase_at_least(phase):
    return DEAL_SYSTEM_PHASE >= int(phase)


DEAL_DEFAULT_REMINDER_INTERVALS = {
    "form_not_submitted_seconds": 2 * 60 * 60,
    "waiting_funds_seconds": 6 * 60 * 60,
    "funds_no_confirm_seconds": 24 * 60 * 60,
    "disputed_seconds": 24 * 60 * 60,
    "timeout_seconds": 7 * 24 * 60 * 60,
}
DEAL_COLUMNS = (
    "id", "dealId", "guildId", "ticketChannelId", "createdById", "buyerId",
    "sellerId", "middlemanId", "paymentPenjual", "paymentPembeli",
    "nominalItem", "feeType", "mmFee", "buyerPays", "sellerReceives",
    "description", "status", "warningMessageId", "summaryMessageId",
    "fundsReceivedStageMessageId", "buyerConfirmStageMessageId", "payoutStageMessageId",
    "doneStageMessageId", "completedSummaryMessageId", "vouchProgressMessageId",
    "cancelledById", "cancelledAt", "cancelReason",
    "disputedById", "disputedAt", "disputeReason", "disputeProofUrl",
    "disputePreviousStatus", "statusBeforeDispute", "disputeResolvedById", "disputeResolvedAt",
    "disputeResolution", "paymentProofUrl",
    "paymentProofNotes", "paymentProofMessageId", "paymentProofChannelId",
    "paymentProofSubmittedById", "paymentProofSubmittedAt",
    "paymentProofInvalidatedAt", "paymentProofInvalidatedById", "paymentProofInvalidationReason",
    "paymentProofConfirmationMessageId", "transferProofUrl",
    "transferProofNotes", "transferProofMessageId", "transferProofChannelId",
    "transferProofSubmittedById", "transferProofSubmittedAt", "sellerPayoutPlatform",
    "sellerPayoutAccount", "sellerPayoutName", "sellerPayoutSubmittedById",
    "sellerPayoutSubmittedAt", "formSubmittedById", "formSubmittedAt", "fundsReceivedNotes",
    "paymentInstructionOwnerId", "paymentInstructionMessageId", "paymentInstructionSentAt",
    "paymentInstructionPayloadHash", "fundsReceivedById", "fundsReceivedAt", "itemSentById", "itemSentAt",
    "buyerConfirmedById", "buyerConfirmedAt", "buyerConfirmationSource", "completedById", "completedAt",
    "isVouchEligible", "createdAt", "updatedAt",
)
DEAL_SELECT = ", ".join(DEAL_COLUMNS)
DEAL_PAYMENT_PROFILE_COLUMNS = (
    "id", "guildId", "userId", "title", "paymentText", "qrisNote", "note",
    "footerText", "imageUrl", "imageFilename", "enabled", "createdAt", "updatedAt",
)
DEAL_PAYMENT_PROFILE_SELECT = ", ".join(DEAL_PAYMENT_PROFILE_COLUMNS)
DEAL_ARCHIVE_COLUMNS = (
    "id", "guildId", "dealId", "channelId", "buyerId", "sellerId", "middlemanId",
    "finalStatus", "paymentProofSubmitted", "transferProofSubmitted", "vouchEligible",
    "disputeOpened", "disputeResolved", "cancelled", "completed", "finalActionById",
    "cancelledById", "completedById", "disputeOpenedById", "disputeResolvedById",
    "safeReason", "safeResolution", "createdAt", "finalizedAt", "archivedAt",
)
DEAL_ARCHIVE_SELECT = ", ".join(DEAL_ARCHIVE_COLUMNS)
VOUCH_COLUMNS = (
    "id", "guildId", "dealId", "reviewerId", "targetId", "reviewerRole",
    "targetRole", "rating", "review", "proofUrl", "verifiedDeal", "status",
    "removedBy", "removeReason", "createdAt", "updatedAt", "vouchType",
    "approvalStatus", "proofCount", "proofData", "proofSubmittedAt",
    "approvedById", "approvedAt", "rejectedById", "rejectedAt",
    "rejectionReason", "context", "staffNotes", "targetRaw", "targetResolved",
)
VOUCH_SELECT = ", ".join(VOUCH_COLUMNS)


def _deal_now():
    return datetime.utcnow().isoformat() + "Z"


def _json_id_list(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if str(x).strip()]


def _deal_reminder_intervals(raw):
    data = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            data = {}
    merged = dict(DEAL_DEFAULT_REMINDER_INTERVALS)
    for key, value in data.items():
        try:
            merged[key] = max(60, int(value))
        except (TypeError, ValueError):
            pass
    return merged


def _deal_row_to_dict(row):
    if not row:
        return None
    return dict(zip(DEAL_COLUMNS, row))


def _deal_archive_row_to_dict(row):
    if not row:
        return None
    data = dict(zip(DEAL_ARCHIVE_COLUMNS, row))
    for key in (
        "paymentProofSubmitted", "transferProofSubmitted", "vouchEligible",
        "disputeOpened", "disputeResolved", "cancelled", "completed",
    ):
        data[key] = bool(data.get(key))
    return data


def _safe_archive_text(value, max_length=300):
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"https?://\S+", "[link hidden]", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[email hidden]", text)
    text = re.sub(r"\b(?:\d[\s-]?){6,}\d\b", "[number hidden]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text or None


def _deal_archive_identifier(deal):
    if not deal:
        return None
    return str(deal.get("dealId") or f"ROW-{deal.get('id')}").strip()


def _deal_is_archivable_final_status(status):
    return str(status or "").strip() in DEAL_CLOSED_STATUSES


def _deal_finalized_at(deal):
    status = str(deal.get("status") or "")
    if status == DEAL_STATUS_COMPLETED:
        return deal.get("completedAt") or deal.get("updatedAt")
    if status == "Cancelled":
        return deal.get("cancelledAt") or deal.get("updatedAt")
    if status == DEAL_STATUS_DISPUTED and deal.get("disputeResolvedAt"):
        return deal.get("disputeResolvedAt")
    return deal.get("updatedAt") or deal.get("createdAt")


def _deal_final_action_by(deal, final_action_by=None):
    if final_action_by is not None:
        return str(final_action_by)
    return (
        deal.get("completedById")
        or deal.get("cancelledById")
        or deal.get("disputeResolvedById")
        or deal.get("middlemanId")
    )


async def get_deal_archive(guild_id, deal_id):
    token = str(deal_id or "").strip()
    if not token:
        return None
    candidates = [token]
    if token.upper() != token:
        candidates.append(token.upper())
    async with aiosqlite.connect(DB_PATH) as db:
        for candidate in candidates:
            async with db.execute(
                f"SELECT {DEAL_ARCHIVE_SELECT} FROM dealArchives WHERE guildId=? AND dealId=?",
                (str(guild_id), candidate),
            ) as cursor:
                archive = _deal_archive_row_to_dict(await cursor.fetchone())
                if archive:
                    return archive
        async with db.execute(
            f"SELECT {DEAL_ARCHIVE_SELECT} FROM dealArchives WHERE guildId=? AND id=?",
            (str(guild_id), token if token.isdigit() else -1),
        ) as cursor:
            return _deal_archive_row_to_dict(await cursor.fetchone())


async def list_recent_deal_archives(guild_id, limit=10):
    limit = max(1, min(10, int(limit or 10)))
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""
            SELECT {DEAL_ARCHIVE_SELECT}
            FROM dealArchives
            WHERE guildId=?
            ORDER BY archivedAt DESC, id DESC
            LIMIT ?
            """,
            (str(guild_id), limit),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_deal_archive_row_to_dict(row) for row in rows]


async def search_deal_archives_for_user(guild_id, user_id, limit=10):
    limit = max(1, min(10, int(limit or 10)))
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""
            SELECT {DEAL_ARCHIVE_SELECT}
            FROM dealArchives
            WHERE guildId=? AND (buyerId=? OR sellerId=? OR middlemanId=?)
            ORDER BY archivedAt DESC, id DESC
            LIMIT ?
            """,
            (str(guild_id), uid, uid, uid, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_deal_archive_row_to_dict(row) for row in rows]


async def archive_deal_if_final(deal_row_id, final_status=None, final_action_by=None, reason=None, resolution=None, *, audit=True):
    try:
        deal = await get_deal_by_id(deal_row_id)
        if not deal:
            return None, "not_found"
        final_status = str(final_status or deal.get("status") or "").strip()
        if not _deal_is_archivable_final_status(final_status):
            return None, "not_final"

        archive_deal_id = _deal_archive_identifier(deal)
        if not archive_deal_id:
            return None, "missing_deal_id"

        now = _deal_now()
        safe_reason = _safe_archive_text(reason or deal.get("cancelReason") or deal.get("disputeReason"))
        safe_resolution = _safe_archive_text(resolution or deal.get("disputeResolution"))
        final_action = _deal_final_action_by(deal, final_action_by)
        values = {
            "guildId": str(deal["guildId"]),
            "dealId": archive_deal_id,
            "channelId": str(deal.get("ticketChannelId") or ""),
            "buyerId": str(deal.get("buyerId") or ""),
            "sellerId": str(deal.get("sellerId") or ""),
            "middlemanId": str(deal.get("middlemanId") or ""),
            "finalStatus": final_status,
            "paymentProofSubmitted": int(bool(deal.get("paymentProofSubmittedAt") or deal.get("paymentProofMessageId") or deal.get("paymentProofUrl"))),
            "transferProofSubmitted": int(bool(deal.get("transferProofSubmittedAt") or deal.get("transferProofMessageId") or deal.get("transferProofUrl"))),
            "vouchEligible": int(bool(deal.get("isVouchEligible"))),
            "disputeOpened": int(bool(deal.get("disputedAt") or deal.get("disputedById"))),
            "disputeResolved": int(bool(deal.get("disputeResolvedAt") or deal.get("disputeResolvedById"))),
            "cancelled": int(final_status == "Cancelled"),
            "completed": int(final_status == DEAL_STATUS_COMPLETED),
            "finalActionById": str(final_action) if final_action is not None else None,
            "cancelledById": str(deal.get("cancelledById")) if deal.get("cancelledById") else None,
            "completedById": str(deal.get("completedById")) if deal.get("completedById") else None,
            "disputeOpenedById": str(deal.get("disputedById")) if deal.get("disputedById") else None,
            "disputeResolvedById": str(deal.get("disputeResolvedById")) if deal.get("disputeResolvedById") else None,
            "safeReason": safe_reason,
            "safeResolution": safe_resolution,
            "createdAt": deal.get("createdAt"),
            "finalizedAt": _deal_finalized_at(deal),
            "archivedAt": now,
        }
        insert_cols = [col for col in DEAL_ARCHIVE_COLUMNS if col != "id"]
        placeholders = ", ".join("?" for _ in insert_cols)
        update_clause = ", ".join(f"{col}=excluded.{col}" for col in insert_cols if col not in ("guildId", "dealId", "createdAt"))
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"""
                INSERT INTO dealArchives ({", ".join(insert_cols)})
                VALUES ({placeholders})
                ON CONFLICT(guildId, dealId) DO UPDATE SET {update_clause}
                """,
                tuple(values.get(col) for col in insert_cols),
            )
            await db.commit()
        archive = await get_deal_archive(deal["guildId"], archive_deal_id)
        await write_audit("deal_archived", archive_deal_id, final_status, source="deal")
        await on_public_trust_stats_changed(deal["guildId"])
        await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "middleman_status", "dispute_board"})
        if final_status == DEAL_STATUS_COMPLETED:
            await send_public_completed_deal_feed(deal["guildId"], deal["id"])
            if audit:
                guild = None
                try:
                    guild = client.get_guild(int(deal["guildId"]))
                except (TypeError, ValueError):
                    guild = None
                if guild:
                    await send_deal_audit_log(
                        guild,
                        "Deal Archived",
                        actor=final_action,
                        deal_id=archive_deal_id,
                        note="Safe archive record created",
                        metadata={"status": final_status},
                    )
        return archive, None
    except Exception as e:
        logging.error("archive_deal_if_final error exception=%s", type(e).__name__)
        return None, "error"


async def backfill_deal_archives(guild_id, actor_id=None):
    placeholders = ",".join("?" for _ in DEAL_CLOSED_STATUSES)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT id FROM Deal WHERE guildId=? AND status IN ({placeholders})",
            (str(guild_id), *DEAL_CLOSED_STATUSES),
        ) as cursor:
            rows = await cursor.fetchall()
    created = 0
    skipped = 0
    for (deal_row_id,) in rows:
        deal = await get_deal_by_id(deal_row_id)
        if not deal:
            skipped += 1
            continue
        existing = await get_deal_archive(guild_id, _deal_archive_identifier(deal))
        if existing:
            skipped += 1
            continue
        archive, error = await archive_deal_if_final(deal_row_id, final_action_by=actor_id, audit=False)
        if archive and not error:
            created += 1
        else:
            skipped += 1
    return created, skipped


STAFF_OPERATION_PANEL_TYPES = {"middleman_status", "active_deals", "dispute_board", "trust_warning"}
REFRESHABLE_DEAL_PANEL_TYPES = {"vouch_leaderboard", "trust_stats", *STAFF_OPERATION_PANEL_TYPES}
DEAL_PANEL_TYPES = {"vouch_leaderboard", "trust_stats", "recent_vouches", "completed_deals", *STAFF_OPERATION_PANEL_TYPES}
DEAL_PANEL_REST_TIMEOUT_SECONDS = 5
DEAL_PANEL_LABELS = {
    "vouch_leaderboard": "Trusted Vouch Leaderboard",
    "trust_stats": "Server Trust Stats",
    "recent_vouches": "Recent Vouches Feed",
    "completed_deals": "Completed Deals Feed",
    "middleman_status": "Middleman Status Panel",
    "active_deals": "Active Deal Queue",
    "dispute_board": "Dispute Board",
    "trust_warning": "Trust Warning / Report Panel",
}
MIDDLEMAN_STATUS_VALUES = {"available", "busy", "offline", "unavailable"}


def _deal_panel_row_to_dict(row):
    if not row:
        return None
    return {
        "id": row[0],
        "guildId": row[1],
        "panelType": row[2],
        "channelId": row[3],
        "messageId": row[4],
        "enabled": bool(row[5]),
        "lastPayloadHash": row[6],
        "createdAt": row[7],
        "updatedAt": row[8],
    }


def _deal_panel_hash(embed):
    payload = json.dumps(embed.to_dict(), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deal_payment_instruction_payload_hash(embed):
    payload = json.dumps(embed.to_dict(), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payment_profile_row_to_dict(row):
    if not row:
        return None
    data = dict(zip(DEAL_PAYMENT_PROFILE_COLUMNS, row))
    data["enabled"] = bool(data.get("enabled"))
    return data


def _sanitize_payment_profile_text(value, max_length):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None
    text = discord.utils.escape_mentions(text)
    return text[:max_length]


def deal_payment_profile_is_valid(profile):
    if not profile:
        return False
    return bool(str(profile.get("paymentText") or "").strip() or str(profile.get("imageUrl") or "").strip())


def resolve_deal_payment_instruction_owner_id(deal):
    if not deal:
        return None
    buyer_id = str(deal.get("buyerId") or "")
    seller_id = str(deal.get("sellerId") or "")
    for key in ("paymentInstructionOwnerId", "middlemanId", "adminId", "executorId", "createdById", "startedById"):
        value = str(deal.get(key) or "").strip()
        if value and value not in {buyer_id, seller_id}:
            return value
    return None


async def get_deal_payment_profile(guild_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT {DEAL_PAYMENT_PROFILE_SELECT} FROM dealPaymentProfiles WHERE guildId=? AND userId=?",
            (str(guild_id), str(user_id)),
        ) as cursor:
            return _payment_profile_row_to_dict(await cursor.fetchone())


async def save_deal_payment_profile(guild_id, user_id, **fields):
    allowed = {
        "title", "paymentText", "qrisNote", "note", "footerText",
        "imageUrl", "imageFilename", "enabled",
    }
    clean_fields = {k: v for k, v in dict(fields or {}).items() if k in allowed}
    if "title" in clean_fields:
        clean_fields["title"] = _sanitize_payment_profile_text(clean_fields.get("title"), 100)
    if "paymentText" in clean_fields:
        clean_fields["paymentText"] = _sanitize_payment_profile_text(clean_fields.get("paymentText"), 3000)
    if "qrisNote" in clean_fields:
        clean_fields["qrisNote"] = _sanitize_payment_profile_text(clean_fields.get("qrisNote"), 1000)
    if "note" in clean_fields:
        clean_fields["note"] = _sanitize_payment_profile_text(clean_fields.get("note"), 1000)
    if "footerText" in clean_fields:
        clean_fields["footerText"] = _sanitize_payment_profile_text(clean_fields.get("footerText"), 300)
    if "imageUrl" in clean_fields:
        clean_fields["imageUrl"] = str(clean_fields.get("imageUrl") or "").strip() or None
    if "imageFilename" in clean_fields:
        clean_fields["imageFilename"] = str(clean_fields.get("imageFilename") or "").strip()[:255] or None

    current = await get_deal_payment_profile(guild_id, user_id) or {}
    merged = dict(current)
    merged.update(clean_fields)
    if "enabled" in clean_fields:
        merged["enabled"] = bool(clean_fields["enabled"])
    elif "enabled" not in merged:
        merged["enabled"] = True
    if not deal_payment_profile_is_valid(merged):
        merged["enabled"] = False

    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO dealPaymentProfiles (
                guildId, userId, title, paymentText, qrisNote, note, footerText,
                imageUrl, imageFilename, enabled, createdAt, updatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guildId, userId) DO UPDATE SET
                title=excluded.title,
                paymentText=excluded.paymentText,
                qrisNote=excluded.qrisNote,
                note=excluded.note,
                footerText=excluded.footerText,
                imageUrl=excluded.imageUrl,
                imageFilename=excluded.imageFilename,
                enabled=excluded.enabled,
                updatedAt=excluded.updatedAt
            """,
            (
                str(guild_id), str(user_id), merged.get("title"), merged.get("paymentText"),
                merged.get("qrisNote"), merged.get("note"), merged.get("footerText"),
                merged.get("imageUrl"), merged.get("imageFilename"), int(bool(merged.get("enabled"))),
                merged.get("createdAt") or now, now,
            ),
        )
        await db.commit()
    return await get_deal_payment_profile(guild_id, user_id), None


async def set_deal_payment_profile_enabled(guild_id, user_id, enabled):
    profile = await get_deal_payment_profile(guild_id, user_id)
    if bool(enabled) and not deal_payment_profile_is_valid(profile):
        return profile, "invalid_profile"
    profile, _error = await save_deal_payment_profile(guild_id, user_id, enabled=bool(enabled))
    return profile, None


async def clear_deal_payment_profile_image(guild_id, user_id):
    profile, error = await save_deal_payment_profile(
        guild_id,
        user_id,
        imageUrl=None,
        imageFilename=None,
    )
    return profile, error


async def set_deal_payment_instruction_tracking(deal_row_id, message_id, payload_hash, owner_id=None):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE Deal
            SET paymentInstructionOwnerId=CASE
                    WHEN paymentInstructionOwnerId IS NULL OR paymentInstructionOwnerId='' THEN ?
                    ELSE paymentInstructionOwnerId
                END,
                paymentInstructionMessageId=?,
                paymentInstructionSentAt=?,
                paymentInstructionPayloadHash=?,
                updatedAt=?
            WHERE id=?
            """,
            (
                str(owner_id) if owner_id else None,
                str(message_id) if message_id else None,
                now,
                str(payload_hash) if payload_hash else None,
                now,
                int(deal_row_id),
            ),
        )
        await db.commit()
    return await get_deal_by_id(deal_row_id)


async def get_deal_panel_config(guild_id, panel_type):
    if panel_type not in DEAL_PANEL_TYPES:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, guildId, panelType, channelId, messageId, enabled, lastPayloadHash, createdAt, updatedAt FROM dealPanels WHERE guildId=? AND panelType=?",
            (str(guild_id), panel_type),
        ) as cursor:
            return _deal_panel_row_to_dict(await cursor.fetchone())


async def set_deal_panel_config(guild_id, panel_type, channel_id, message_id=None, enabled=True, last_payload_hash=None):
    if panel_type not in DEAL_PANEL_TYPES:
        return None
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO dealPanels (guildId, panelType, channelId, messageId, enabled, lastPayloadHash, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guildId, panelType) DO UPDATE SET
                channelId=excluded.channelId,
                messageId=COALESCE(excluded.messageId, dealPanels.messageId),
                enabled=excluded.enabled,
                lastPayloadHash=COALESCE(excluded.lastPayloadHash, dealPanels.lastPayloadHash),
                updatedAt=excluded.updatedAt
            """,
            (
                str(guild_id), panel_type, str(channel_id) if channel_id is not None else None,
                str(message_id) if message_id is not None else None, int(bool(enabled)),
                last_payload_hash, now, now,
            ),
        )
        await db.commit()
    return await get_deal_panel_config(guild_id, panel_type)


async def disable_deal_panel_config(guild_id, panel_type):
    current = await get_deal_panel_config(guild_id, panel_type)
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO dealPanels (guildId, panelType, channelId, messageId, enabled, lastPayloadHash, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, 0, NULL, ?, ?)
            ON CONFLICT(guildId, panelType) DO UPDATE SET
                enabled=0,
                updatedAt=excluded.updatedAt
            """,
            (
                str(guild_id), panel_type, current.get("channelId") if current else None,
                current.get("messageId") if current else None, now, now,
            ),
        )
        await db.commit()
    return await get_deal_panel_config(guild_id, panel_type)


async def list_enabled_deal_panel_configs(guild_id=None):
    query = "SELECT id, guildId, panelType, channelId, messageId, enabled, lastPayloadHash, createdAt, updatedAt FROM dealPanels WHERE enabled=1"
    params = []
    if guild_id is not None:
        query += " AND guildId=?"
        params.append(str(guild_id))
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()
    return [_deal_panel_row_to_dict(row) for row in rows]


async def _public_user_display(guild, user_id):
    uid = str(user_id or "").strip()
    if not uid:
        return "@Unknown"
    member = None
    if guild:
        try:
            member = guild.get_member(int(uid))
            if not member:
                member = await guild.fetch_member(int(uid))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
            member = None
    user = member
    if not user:
        try:
            user = client.get_user(int(uid)) or await client.fetch_user(int(uid))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
            user = None
    name = getattr(user, "display_name", None) or getattr(user, "global_name", None) or getattr(user, "name", None)
    if not name:
        return "@Unknown"
    return "@" + discord.utils.escape_markdown(str(name))[:80]


def _panel_rating(value):
    try:
        return f"{float(value):.1f}/5"
    except (TypeError, ValueError):
        return "0.0/5"


def _panel_age(value):
    dt = _parse_deal_datetime(value)
    if not dt:
        return "N/A"
    seconds = max(0, int((datetime.utcnow() - dt).total_seconds()))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _deal_next_step(status):
    return {
        DEAL_STATUS_PENDING_FORM: "Isi form deal",
        DEAL_STATUS_WAITING_FUNDS: "Menunggu payment / dana masuk",
        DEAL_STATUS_FUNDS_RECEIVED: "Buyer confirm",
        DEAL_STATUS_ITEM_SENT: "Buyer confirm",
        DEAL_STATUS_BUYER_CONFIRMED: "Data pencairan / transfer final",
        DEAL_STATUS_DISPUTED: "Staff review dispute",
    }.get(status, "Review status deal")


def _middleman_status_row(row):
    if not row:
        return None
    return {
        "guildId": row[0],
        "userId": row[1],
        "status": row[2] or "offline",
        "note": row[3],
        "updatedAt": row[4],
        "updatedById": row[5],
        "createdAt": row[6],
    }


async def get_middleman_status(guild_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guildId, userId, status, note, updatedAt, updatedById, createdAt FROM middlemanStatus WHERE guildId=? AND userId=?",
            (str(guild_id), str(user_id)),
        ) as cursor:
            return _middleman_status_row(await cursor.fetchone())


async def set_middleman_status(guild_id, user_id, status, note, updated_by_id):
    status = str(status or "").strip().lower()
    if status not in MIDDLEMAN_STATUS_VALUES:
        return None, "invalid_status"
    safe_note = _safe_archive_text(note, 120)
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO middlemanStatus (guildId, userId, status, note, updatedAt, updatedById, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guildId, userId) DO UPDATE SET
                status=excluded.status,
                note=excluded.note,
                updatedAt=excluded.updatedAt,
                updatedById=excluded.updatedById
            """,
            (str(guild_id), str(user_id), status, safe_note, now, str(updated_by_id), now),
        )
        await db.commit()
    await write_audit("middleman_status_updated", user_id, f"{status}: {safe_note or '-'}", source="deal")
    await refresh_staff_operation_panels(guild_id, {"middleman_status"})
    return await get_middleman_status(guild_id, user_id), None


async def clear_middleman_status(guild_id, user_id, updated_by_id):
    return await set_middleman_status(guild_id, user_id, "offline", None, updated_by_id)


async def _guild_middleman_member_ids(guild):
    config = await get_deal_config(guild.id)
    role_ids = []
    if config and config.get("middlemanRoleId"):
        role_ids.append(str(config["middlemanRoleId"]))
    members = {}
    for rid in role_ids:
        try:
            role = guild.get_role(int(rid))
        except (TypeError, ValueError):
            role = None
        if role:
            for member in role.members:
                members[str(member.id)] = member
    if not members and config:
        for rid in config.get("dealStaffRoleIds", []):
            try:
                role = guild.get_role(int(rid))
            except (TypeError, ValueError):
                role = None
            if role:
                for member in role.members:
                    members[str(member.id)] = member
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT middlemanId FROM Deal WHERE guildId=? AND middlemanId IS NOT NULL", (str(guild.id),)) as cursor:
            rows = await cursor.fetchall()
    for (uid,) in rows:
        if uid and uid not in members:
            try:
                member = guild.get_member(int(uid))
                if member:
                    members[str(uid)] = member
            except (TypeError, ValueError):
                pass
    return list(members.keys())


async def build_middleman_status_embed(guild):
    embed = discord.Embed(title="🛡️ Middleman Status Panel", color=0x5865F2)
    member_ids = await _guild_middleman_member_ids(guild)
    if not member_ids:
        embed.add_field(name="Belum ada middleman", value="Role middleman belum memiliki member atau belum ada data deal.", inline=False)
    for uid in member_ids[:15]:
        status_row = await get_middleman_status(guild.id, uid)
        status = (status_row or {}).get("status") or "offline"
        note = _safe_archive_text((status_row or {}).get("note"), 100) or "-"
        updated_at = (status_row or {}).get("updatedAt")
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                f"SELECT COUNT(*) FROM Deal WHERE guildId=? AND middlemanId=? AND status IN ({','.join('?' for _ in DEAL_ACTIVE_STATUSES)})",
                (str(guild.id), str(uid), *DEAL_ACTIVE_STATUSES),
            ) as cursor:
                active = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM Deal WHERE guildId=? AND middlemanId=? AND status=?", (str(guild.id), str(uid), DEAL_STATUS_COMPLETED)) as cursor:
                completed = (await cursor.fetchone())[0]
        rep = await get_user_reputation(guild.id, uid)
        value = (
            f"Status: **{status.title().replace('_', ' ')}**\n"
            f"Active Deals: **{int(active or 0)}**\n"
            f"Completed Deals: **{int(completed or 0)}**\n"
            f"Average Rating: **{_panel_rating(rep.get('averageRating') if rep else 0)}**\n"
            f"Note: {note}\n"
            f"Last Updated: {format_discord_ts(updated_at)}"
        )
        embed.add_field(name=await _public_user_display(guild, uid), value=value, inline=False)
    embed.set_footer(text=f"Auto-updated • Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    return embed


def format_discord_ts(value):
    dt = _parse_deal_datetime(value)
    if not dt:
        return "N/A"
    return f"<t:{int(dt.timestamp())}:R>"


async def build_active_deal_queue_embed(guild):
    deals = await list_active_deals(guild.id)
    embed = discord.Embed(title="📦 Active Deal Queue", color=0x5865F2)
    if not deals:
        embed.description = "No active deals."
    for deal in deals[:15]:
        value = (
            f"Status: **{deal.get('status') or '-'}**\n"
            f"Buyer: {await _public_user_display(guild, deal.get('buyerId'))}\n"
            f"Seller: {await _public_user_display(guild, deal.get('sellerId'))}\n"
            f"Middleman: {await _public_user_display(guild, deal.get('middlemanId'))}\n"
            f"Age: {_panel_age(deal.get('createdAt'))}\n"
            f"Next Step: {_deal_next_step(deal.get('status'))}"
        )
        embed.add_field(name=f"Deal {deal.get('dealId') or deal.get('id')}", value=value, inline=False)
    extra = max(0, len(deals) - 15)
    if extra:
        embed.add_field(name="More", value=f"+{extra} more active deals", inline=False)
    embed.set_footer(text=f"Auto-updated • Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    return embed


async def build_dispute_board_embed(guild):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT {DEAL_SELECT} FROM Deal WHERE guildId=? AND status=? ORDER BY disputedAt DESC, updatedAt DESC LIMIT 15",
            (str(guild.id), DEAL_STATUS_DISPUTED),
        ) as cursor:
            rows = await cursor.fetchall()
    deals = [_deal_row_to_dict(row) for row in rows]
    embed = discord.Embed(title="⚠️ Dispute Board", color=0xFEE75C)
    if not deals:
        embed.description = "No active disputes."
    for deal in deals:
        reason = _safe_archive_text(deal.get("disputeReason"), 180) or "-"
        value = (
            f"Buyer: {await _public_user_display(guild, deal.get('buyerId'))}\n"
            f"Seller: {await _public_user_display(guild, deal.get('sellerId'))}\n"
            f"Middleman: {await _public_user_display(guild, deal.get('middlemanId'))}\n"
            f"Opened By: {await _public_user_display(guild, deal.get('disputedById'))}\n"
            f"Reason: {reason}\n"
            f"Age: {_panel_age(deal.get('disputedAt'))}\n"
            f"Status: Unresolved"
        )
        embed.add_field(name=f"Deal {deal.get('dealId') or deal.get('id')}", value=value, inline=False)
    embed.set_footer(text=f"Auto-updated • Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    return embed


async def build_trust_warning_embed(guild):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT {SCAM_REPORT_SELECT} FROM scammerReports WHERE guildId=? AND status='pending' ORDER BY createdAt DESC LIMIT 5",
            (str(guild.id),),
        ) as cursor:
            pending_rows = await cursor.fetchall()
        async with db.execute("SELECT COUNT(*) FROM scammerReports WHERE guildId=? AND status='pending'", (str(guild.id),)) as cursor:
            pending_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT userId, reason, updatedAt FROM trustModerationStatus WHERE guildId=? AND status='under_review' ORDER BY updatedAt DESC LIMIT 5", (str(guild.id),)) as cursor:
            under_rows = await cursor.fetchall()
        async with db.execute("SELECT COUNT(*) FROM trustModerationStatus WHERE guildId=? AND status='under_review'", (str(guild.id),)) as cursor:
            under_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT userId, reason, updatedAt FROM trustModerationStatus WHERE guildId=? AND status='blacklisted' ORDER BY updatedAt DESC LIMIT 5", (str(guild.id),)) as cursor:
            black_rows = await cursor.fetchall()
        async with db.execute("SELECT COUNT(*) FROM trustModerationStatus WHERE guildId=? AND status='blacklisted'", (str(guild.id),)) as cursor:
            black_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT userId, status, reason, updatedAt FROM trustModerationStatus WHERE guildId=? ORDER BY updatedAt DESC LIMIT 5", (str(guild.id),)) as cursor:
            action_rows = await cursor.fetchall()

    embed = discord.Embed(title="🚨 Trust Warning / Report Panel", color=0xED4245)
    pending_lines = []
    for row in pending_rows:
        report = _scam_report_row_to_dict(row)
        target = await _public_user_display(guild, report.get("reportedUserId")) if report.get("reportedUserId") else _safe_archive_text(report.get("reportedRaw"), 80) or "Unresolved target"
        pending_lines.append(f"#{report.get('id')} {target} • {_panel_age(report.get('createdAt'))}")
    embed.add_field(name=f"Pending Scam Reports ({int(pending_count or 0)})", value="\n".join(pending_lines) or "None", inline=False)

    under_lines = [f"{await _public_user_display(guild, uid)} • {_panel_age(updated_at)}" for uid, _reason, updated_at in under_rows]
    embed.add_field(name=f"Under Review Users ({int(under_count or 0)})", value="\n".join(under_lines) or "None", inline=False)

    black_lines = [f"{await _public_user_display(guild, uid)} • {_panel_age(updated_at)}" for uid, _reason, updated_at in black_rows]
    embed.add_field(name=f"Blacklisted Users ({int(black_count or 0)})", value="\n".join(black_lines) or "None", inline=False)

    action_lines = []
    for uid, status, reason, updated_at in action_rows:
        safe_reason = _safe_archive_text(reason, 80) or "-"
        action_lines.append(f"{await _public_user_display(guild, uid)} → **{status}** • {safe_reason} • {_panel_age(updated_at)}")
    embed.add_field(name="Recent Trust Actions", value="\n".join(action_lines) or "N/A", inline=False)
    embed.set_footer(text=f"Auto-updated • Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    return embed


async def build_trusted_vouch_leaderboard_embed(guild):
    reps = await get_reputation_leaderboard(guild.id, 10)
    embed = discord.Embed(
        title="🏆 Trusted Vouch Leaderboard",
        description="Top trusted users based on verified and approved vouches.",
        color=0xFFD700,
    )
    if not reps:
        embed.add_field(name="Belum ada data", value="Belum ada vouch verified atau approved yang bisa ditampilkan.", inline=False)
    for idx, rep in enumerate(reps, start=1):
        name = await _public_user_display(guild, rep.get("userId"))
        value = (
            f"Verified Deal Vouches: **{int(rep.get('verifiedDealVouches') or 0)}**\n"
            f"Admin Approved Vouches: **{int(rep.get('manualApprovedVouches') or 0)}**\n"
            f"Average Rating: **{_panel_rating(rep.get('averageRating'))}**\n"
            f"Trust Rank: **{rep.get('trustLevel') or 'New User'}**"
        )
        embed.add_field(name=f"#{idx} {name}", value=value, inline=False)
    embed.set_footer(text=f"Auto-updated • Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    return embed


async def get_server_trust_stats(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async def one(query, params=()):
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

        completed = await one("SELECT COUNT(*) FROM Deal WHERE guildId=? AND status=?", (str(guild_id), DEAL_STATUS_COMPLETED))
        verified_vouches = await one(
            "SELECT COUNT(*) FROM Vouch WHERE guildId=? AND status='active' AND vouchType='verified_deal' AND approvalStatus='verified'",
            (str(guild_id),),
        )
        manual_vouches = await one(
            "SELECT COUNT(*) FROM Vouch WHERE guildId=? AND status='active' AND vouchType='manual' AND approvalStatus='approved'",
            (str(guild_id),),
        )
        active_traders = await one(
            """
            SELECT COUNT(DISTINCT v.targetId)
            FROM Vouch v
            LEFT JOIN trustModerationStatus t ON t.guildId=v.guildId AND t.userId=v.targetId
            WHERE v.guildId=? AND v.status='active' AND v.targetId IS NOT NULL
              AND ((v.vouchType='verified_deal' AND v.approvalStatus='verified') OR (v.vouchType='manual' AND v.approvalStatus='approved'))
              AND COALESCE(t.status, 'clear') != 'blacklisted'
            """,
            (str(guild_id),),
        )
        avg_rating = await one(
            """
            SELECT AVG(rating) FROM Vouch
            WHERE guildId=? AND status='active'
              AND ((vouchType='verified_deal' AND approvalStatus='verified') OR (vouchType='manual' AND approvalStatus='approved'))
            """,
            (str(guild_id),),
        )
        disputed = await one("SELECT COUNT(*) FROM Deal WHERE guildId=? AND disputedAt IS NOT NULL", (str(guild_id),))
        cancelled = await one("SELECT COUNT(*) FROM Deal WHERE guildId=? AND status='Cancelled'", (str(guild_id),))
        under_review = await one("SELECT COUNT(*) FROM trustModerationStatus WHERE guildId=? AND status='under_review'", (str(guild_id),))
        blacklisted = await one("SELECT COUNT(*) FROM trustModerationStatus WHERE guildId=? AND status='blacklisted'", (str(guild_id),))
    return {
        "completed": int(completed or 0),
        "verified_vouches": int(verified_vouches or 0),
        "manual_vouches": int(manual_vouches or 0),
        "active_traders": int(active_traders or 0),
        "avg_rating": float(avg_rating or 0),
        "disputed": int(disputed or 0),
        "cancelled": int(cancelled or 0),
        "under_review": int(under_review or 0),
        "blacklisted": int(blacklisted or 0),
    }


async def build_server_trust_stats_embed(guild):
    stats = await get_server_trust_stats(guild.id)
    embed = discord.Embed(title="📊 Server Trust Stats", color=0x5865F2)
    embed.add_field(name="Completed Deals", value=str(stats["completed"]), inline=True)
    embed.add_field(name="Verified Deal Vouches", value=str(stats["verified_vouches"]), inline=True)
    embed.add_field(name="Admin Approved Vouches", value=str(stats["manual_vouches"]), inline=True)
    embed.add_field(name="Active Traders", value=str(stats["active_traders"]), inline=True)
    embed.add_field(name="Average Rating", value=_panel_rating(stats["avg_rating"]), inline=True)
    embed.add_field(name="Disputed Deals", value=str(stats["disputed"]), inline=True)
    embed.add_field(name="Cancelled Deals", value=str(stats["cancelled"]), inline=True)
    embed.add_field(name="Under Review Users", value=str(stats["under_review"]), inline=True)
    embed.add_field(name="Blacklisted Users", value=str(stats["blacklisted"]), inline=True)
    embed.set_footer(text=f"Auto-updated • Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    return embed


async def _resolve_panel_channel(guild, config):
    if not guild or not config or not config.get("channelId"):
        return None
    try:
        channel = guild.get_channel(int(config["channelId"]))
        if channel:
            return channel
        return await asyncio.wait_for(
            guild.fetch_channel(int(config["channelId"])),
            timeout=DEAL_PANEL_REST_TIMEOUT_SECONDS,
        )
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, asyncio.TimeoutError, TypeError, ValueError):
        return None


async def refresh_deal_panel(guild, panel_type, *, force=False):
    try:
        if panel_type not in REFRESHABLE_DEAL_PANEL_TYPES:
            return None, "not_refreshable"
        config = await get_deal_panel_config(guild.id, panel_type)
        if not config or not config.get("enabled"):
            return None, "disabled"
        channel = await _resolve_panel_channel(guild, config)
        if not channel:
            return None, "missing_channel"
        builders = {
            "vouch_leaderboard": build_trusted_vouch_leaderboard_embed,
            "trust_stats": build_server_trust_stats_embed,
            "middleman_status": build_middleman_status_embed,
            "active_deals": build_active_deal_queue_embed,
            "dispute_board": build_dispute_board_embed,
            "trust_warning": build_trust_warning_embed,
        }
        embed = await builders[panel_type](guild)
        payload_hash = _deal_panel_hash(embed)
        message = None
        if config.get("messageId"):
            try:
                message = await asyncio.wait_for(
                    channel.fetch_message(int(config["messageId"])),
                    timeout=DEAL_PANEL_REST_TIMEOUT_SECONDS,
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, asyncio.TimeoutError, TypeError, ValueError):
                message = None
        if message and config.get("lastPayloadHash") == payload_hash:
            return message, "unchanged"
        if message:
            await asyncio.wait_for(
                message.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none()),
                timeout=DEAL_PANEL_REST_TIMEOUT_SECONDS,
            )
            await set_deal_panel_config(guild.id, panel_type, channel.id, message.id, enabled=True, last_payload_hash=payload_hash)
            return message, "updated"
        message = await asyncio.wait_for(
            channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none()),
            timeout=DEAL_PANEL_REST_TIMEOUT_SECONDS,
        )
        await set_deal_panel_config(guild.id, panel_type, channel.id, message.id, enabled=True, last_payload_hash=payload_hash)
        await send_deal_audit_log(guild, "Trust Panel Recovered Message", deal_id=None, note=DEAL_PANEL_LABELS.get(panel_type), metadata={"status": "recovered"})
        return message, "created"
    except Exception as e:
        logging.error("refresh_deal_panel error panel_type=%s exception=%s", panel_type, type(e).__name__)
        return None, "error"


async def setup_deal_panel(guild, panel_type, channel):
    if panel_type not in DEAL_PANEL_TYPES:
        return None, "invalid_type"
    await set_deal_panel_config(guild.id, panel_type, channel.id, None, enabled=True, last_payload_hash=None)
    if panel_type in REFRESHABLE_DEAL_PANEL_TYPES:
        return await refresh_deal_panel(guild, panel_type, force=True)
    return await get_deal_panel_config(guild.id, panel_type), "configured"


async def refresh_public_trust_panels(guild_id):
    try:
        guild = client.get_guild(int(guild_id))
    except (TypeError, ValueError):
        guild = None
    if not guild:
        return
    await refresh_deal_panel(guild, "vouch_leaderboard")
    await refresh_deal_panel(guild, "trust_stats")


async def refresh_all_public_trust_panels():
    configs = await list_enabled_deal_panel_configs()
    guild_ids = sorted({config["guildId"] for config in configs if config["panelType"] in {"vouch_leaderboard", "trust_stats"}})
    for guild_id in guild_ids:
        await refresh_public_trust_panels(guild_id)


async def refresh_staff_operation_panels(guild_id, panel_types=None):
    try:
        guild = client.get_guild(int(guild_id))
    except (TypeError, ValueError):
        guild = None
    if not guild:
        return
    target_types = set(panel_types or STAFF_OPERATION_PANEL_TYPES) & STAFF_OPERATION_PANEL_TYPES
    for panel_type in sorted(target_types):
        await refresh_deal_panel(guild, panel_type)


async def refresh_all_staff_operation_panels():
    configs = await list_enabled_deal_panel_configs()
    guild_ids = sorted({config["guildId"] for config in configs if config["panelType"] in STAFF_OPERATION_PANEL_TYPES})
    for guild_id in guild_ids:
        await refresh_staff_operation_panels(guild_id)


async def _panel_event_exists(guild_id, panel_type, event_key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM dealPanelEvents WHERE guildId=? AND panelType=? AND eventKey=?",
            (str(guild_id), panel_type, event_key),
        ) as cursor:
            return await cursor.fetchone() is not None


async def _record_panel_event(guild_id, panel_type, event_type, event_key, message_id, channel_id):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO dealPanelEvents (guildId, panelType, eventType, eventKey, messageId, channelId, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(guild_id), panel_type, event_type, event_key, str(message_id), str(channel_id), now),
        )
        await db.commit()


async def _send_panel_feed_embed(guild, panel_type, event_type, event_key, embed):
    try:
        config = await get_deal_panel_config(guild.id, panel_type)
        if not config or not config.get("enabled"):
            return None, "disabled"
        if await _panel_event_exists(guild.id, panel_type, event_key):
            return None, "duplicate"
        channel = await _resolve_panel_channel(guild, config)
        if not channel:
            return None, "missing_channel"
        message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await _record_panel_event(guild.id, panel_type, event_type, event_key, message.id, channel.id)
        return message, None
    except Exception as e:
        logging.error("_send_panel_feed_embed error panel_type=%s event_key=%s exception=%s", panel_type, event_key, type(e).__name__)
        return None, "error"


async def send_public_vouch_feed(guild_id, vouch_id):
    try:
        vouch = await get_vouch_by_id(guild_id, vouch_id)
        if not vouch or vouch.get("status") != "active":
            return None, "not_public"
        if vouch.get("vouchType") == "verified_deal":
            if vouch.get("approvalStatus") != "verified":
                return None, "not_public"
            title = "⭐ New Verified Deal Vouch"
            source = "Verified Deal Vouch"
            status = "Verified"
        elif vouch.get("vouchType") == "manual":
            if vouch.get("approvalStatus") != "approved":
                return None, "not_public"
            title = "⭐ New Admin Approved Vouch"
            source = "Admin Approved Manual Vouch"
            status = "Admin Approved"
        else:
            return None, "not_public"
        guild = client.get_guild(int(guild_id))
        if not guild:
            return None, "missing_guild"
        embed = discord.Embed(title=title, color=0xFFD700)
        embed.add_field(name="From", value=await _public_user_display(guild, vouch.get("reviewerId")), inline=True)
        embed.add_field(name="To", value=await _public_user_display(guild, vouch.get("targetId")), inline=True)
        embed.add_field(name="Rating", value=_panel_rating(vouch.get("rating")), inline=True)
        embed.add_field(name="Source", value=source, inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        if vouch.get("dealId"):
            embed.add_field(name="Deal ID", value=str(vouch.get("dealId")), inline=True)
        embed.add_field(name="Review", value=_safe_archive_text(vouch.get("review"), 220) or "-", inline=False)
        if vouch.get("vouchType") == "manual" and int(vouch.get("proofCount") or 0) > 0:
            embed.add_field(name="Proof", value="Available", inline=True)
        embed.set_footer(text="Trusted vouch system")
        return await _send_panel_feed_embed(guild, "recent_vouches", "vouch", f"vouch:{vouch_id}", embed)
    except Exception as e:
        logging.error("send_public_vouch_feed error exception=%s", type(e).__name__)
        return None, "error"


async def send_public_completed_deal_feed(guild_id, deal_row_id):
    try:
        deal = await get_deal_by_id(deal_row_id)
        if not deal or deal.get("status") != DEAL_STATUS_COMPLETED:
            return None, "not_completed"
        guild = client.get_guild(int(guild_id))
        if not guild:
            return None, "missing_guild"
        archive = await get_deal_archive(guild_id, deal.get("dealId") or f"ROW-{deal.get('id')}")
        embed = discord.Embed(
            title="✅ Deal Completed",
            description="A middleman deal has been completed successfully.",
            color=0x57F287,
        )
        embed.add_field(name="Deal ID", value=deal.get("dealId") or "-", inline=True)
        embed.add_field(name="Buyer", value=await _public_user_display(guild, deal.get("buyerId")), inline=True)
        embed.add_field(name="Seller", value=await _public_user_display(guild, deal.get("sellerId")), inline=True)
        embed.add_field(name="Middleman", value=await _public_user_display(guild, deal.get("middlemanId")), inline=True)
        embed.add_field(name="Status", value="Selesai", inline=True)
        embed.add_field(name="Vouch", value="Eligible" if deal.get("isVouchEligible") else "Not Eligible", inline=True)
        embed.add_field(name="Archived", value="Yes" if archive else "No", inline=True)
        embed.set_footer(text="Verified middleman transaction")
        return await _send_panel_feed_embed(guild, "completed_deals", "completed_deal", f"completed_deal:{deal.get('dealId') or deal.get('id')}", embed)
    except Exception as e:
        logging.error("send_public_completed_deal_feed error exception=%s", type(e).__name__)
        return None, "error"


async def on_public_trust_vouch_changed(guild_id, vouch_id=None):
    if vouch_id is not None:
        await send_public_vouch_feed(guild_id, vouch_id)
    await refresh_public_trust_panels(guild_id)


async def on_public_trust_stats_changed(guild_id):
    await refresh_public_trust_panels(guild_id)


async def get_deal_config(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guildId, middlemanRoleId, ownerRoleId, dealLogChannelId, vouchChannelId, "
            "dealStaffRoleIds, allowedTicketCategoryIds, dealIdPrefix, pingCooldownSeconds, "
            "reminderEnabled, reminderIntervals, requirePaymentProof, requireTransferProof, "
            "allowUserCancelRequest, autoTimeoutEnabled, trustedRoleThreshold "
            "FROM DealConfig WHERE guildId=?",
            (str(guild_id),),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "guildId": row[0],
        "middlemanRoleId": row[1],
        "ownerRoleId": row[2],
        "dealLogChannelId": row[3],
        "vouchChannelId": row[4],
        "dealStaffRoleIds": _json_id_list(row[5]),
        "allowedTicketCategoryIds": _json_id_list(row[6]),
        "allowedTicketChannelIds": [],
        "dealIdPrefix": row[7] or "MM",
        "pingCooldownSeconds": int(row[8] or 3600),
        "reminderEnabled": bool(row[9]),
        "reminderIntervals": _deal_reminder_intervals(row[10]),
        "requirePaymentProof": bool(row[11]),
        "requireTransferProof": bool(row[12]),
        "allowUserCancelRequest": bool(1 if row[13] is None else row[13]),
        "autoTimeoutEnabled": bool(row[14]),
        "trustedRoleThreshold": int(row[15] or 0),
    }


def is_deal_config_complete(config):
    return True


def is_deal_channel_allowed(channel, config):
    # Legacy helper retained for older config paths. /deal start no longer requires category validation.
    if not channel or not config:
        return False
    channel_ids = set(config.get("allowedTicketChannelIds") or [])
    if str(channel.id) in channel_ids:
        return True
    category_id = getattr(channel, "category_id", None)
    category_ids = set(config.get("allowedTicketCategoryIds") or [])
    return category_id is not None and str(category_id) in category_ids


def member_has_deal_role(member, config):
    if not member:
        return False
    configured_role_ids = set()
    if config:
        if config.get("middlemanRoleId"):
            configured_role_ids.add(str(config["middlemanRoleId"]))
        configured_role_ids.update(str(role_id) for role_id in config.get("dealStaffRoleIds", []))
    roles = getattr(member, "roles", [])
    if configured_role_ids:
        return any(str(role.id) in configured_role_ids for role in roles)
    default_names = {"middleman", "miserator"}
    return any(str(getattr(role, "name", "")).strip().lower() in default_names for role in roles)


def member_has_owner_role(member, config):
    if not member or not config or not config.get("ownerRoleId"):
        return False
    role_id = int(config["ownerRoleId"])
    return any(role.id == role_id for role in getattr(member, "roles", []))


def member_can_admin_override(member, config):
    return bool(getattr(member.guild_permissions, "administrator", False) or member_has_owner_role(member, config))


async def save_deal_config(
    guild_id,
    *,
    middleman_role_id=None,
    owner_role_id=None,
    deal_log_channel_id=None,
    vouch_channel_id=None,
    deal_staff_role_ids=None,
    allowed_ticket_category_ids=None,
    deal_id_prefix=None,
    ping_cooldown_seconds=None,
    reminder_enabled=None,
    reminder_intervals=None,
    require_payment_proof=None,
    require_transfer_proof=None,
    allow_user_cancel_request=None,
    auto_timeout_enabled=None,
    trusted_role_threshold=None,
):
    current = await get_deal_config(guild_id) or {}
    guild_id = str(guild_id)
    middleman_role_id = str(middleman_role_id) if middleman_role_id is not None else current.get("middlemanRoleId")
    owner_role_id = str(owner_role_id) if owner_role_id is not None else current.get("ownerRoleId")
    deal_log_channel_id = str(deal_log_channel_id) if deal_log_channel_id is not None else current.get("dealLogChannelId")
    vouch_channel_id = str(vouch_channel_id) if vouch_channel_id is not None else current.get("vouchChannelId")
    staff_role_ids = (
        [str(x) for x in deal_staff_role_ids]
        if deal_staff_role_ids is not None
        else current.get("dealStaffRoleIds", [])
    )
    allowed_ids = (
        [str(x) for x in allowed_ticket_category_ids]
        if allowed_ticket_category_ids is not None
        else current.get("allowedTicketCategoryIds", [])
    )
    prefix = (deal_id_prefix if deal_id_prefix is not None else current.get("dealIdPrefix")) or "MM"
    prefix = re.sub(r"[^A-Za-z0-9_-]", "", prefix).upper()[:12] or "MM"
    ping_cooldown_seconds = int(ping_cooldown_seconds if ping_cooldown_seconds is not None else current.get("pingCooldownSeconds", 3600))
    reminder_enabled = int(bool(reminder_enabled if reminder_enabled is not None else current.get("reminderEnabled", False)))
    reminder_intervals = (
        _deal_reminder_intervals(json.dumps(reminder_intervals))
        if reminder_intervals is not None
        else current.get("reminderIntervals", dict(DEAL_DEFAULT_REMINDER_INTERVALS))
    )
    require_payment_proof = int(bool(require_payment_proof if require_payment_proof is not None else current.get("requirePaymentProof", False)))
    require_transfer_proof = int(bool(require_transfer_proof if require_transfer_proof is not None else current.get("requireTransferProof", False)))
    allow_user_cancel_request = int(bool(allow_user_cancel_request if allow_user_cancel_request is not None else current.get("allowUserCancelRequest", True)))
    auto_timeout_enabled = int(bool(auto_timeout_enabled if auto_timeout_enabled is not None else current.get("autoTimeoutEnabled", False)))
    trusted_role_threshold = int(trusted_role_threshold if trusted_role_threshold is not None else current.get("trustedRoleThreshold", 0))
    now = _deal_now()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO DealConfig (
                guildId, middlemanRoleId, ownerRoleId, dealLogChannelId, vouchChannelId, dealStaffRoleIds,
                allowedTicketCategoryIds, dealIdPrefix, pingCooldownSeconds, reminderEnabled, reminderIntervals,
                requirePaymentProof, requireTransferProof, allowUserCancelRequest, autoTimeoutEnabled, trustedRoleThreshold,
                createdAt, updatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                middlemanRoleId=excluded.middlemanRoleId,
                ownerRoleId=excluded.ownerRoleId,
                dealLogChannelId=excluded.dealLogChannelId,
                vouchChannelId=excluded.vouchChannelId,
                dealStaffRoleIds=excluded.dealStaffRoleIds,
                allowedTicketCategoryIds=excluded.allowedTicketCategoryIds,
                dealIdPrefix=excluded.dealIdPrefix,
                pingCooldownSeconds=excluded.pingCooldownSeconds,
                reminderEnabled=excluded.reminderEnabled,
                reminderIntervals=excluded.reminderIntervals,
                requirePaymentProof=excluded.requirePaymentProof,
                requireTransferProof=excluded.requireTransferProof,
                allowUserCancelRequest=excluded.allowUserCancelRequest,
                autoTimeoutEnabled=excluded.autoTimeoutEnabled,
                trustedRoleThreshold=excluded.trustedRoleThreshold,
                updatedAt=excluded.updatedAt
            """,
            (
                guild_id, middleman_role_id, owner_role_id, deal_log_channel_id, vouch_channel_id,
                json.dumps(staff_role_ids), json.dumps(allowed_ids), prefix, ping_cooldown_seconds,
                reminder_enabled, json.dumps(reminder_intervals), require_payment_proof,
                require_transfer_proof, allow_user_cancel_request, auto_timeout_enabled,
                trusted_role_threshold, now, now,
            ),
        )
        await db.commit()
    await write_audit("deal_config_update", guild_id, f"prefix={prefix}, categories={','.join(allowed_ids)}", source="deal")
    return await get_deal_config(guild_id)


async def find_active_deal_for_channel(guild_id, channel_id):
    placeholders = ",".join("?" for _ in DEAL_ACTIVE_STATUSES)
    query = (
        f"SELECT {DEAL_SELECT} FROM Deal WHERE guildId=? AND ticketChannelId=? "
        f"AND status IN ({placeholders}) ORDER BY id DESC LIMIT 1"
    )
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, (str(guild_id), str(channel_id), *DEAL_ACTIVE_STATUSES)) as cursor:
            row = await cursor.fetchone()
    return _deal_row_to_dict(row)


async def get_deal_by_deal_id(guild_id, deal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT {DEAL_SELECT} FROM Deal WHERE guildId=? AND dealId=?",
            (str(guild_id), str(deal_id)),
        ) as cursor:
            row = await cursor.fetchone()
    return _deal_row_to_dict(row)


async def get_deal_by_id(row_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?",
            (int(row_id),),
        ) as cursor:
            row = await cursor.fetchone()
    return _deal_row_to_dict(row)


async def create_pending_deal(guild_id, channel_id, created_by_id, buyer_id, seller_id, middleman_id):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        placeholders = ",".join("?" for _ in DEAL_ACTIVE_STATUSES)
        async with db.execute(
            f"SELECT id FROM Deal WHERE guildId=? AND ticketChannelId=? AND status IN ({placeholders}) LIMIT 1",
            (str(guild_id), str(channel_id), *DEAL_ACTIVE_STATUSES),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            await db.rollback()
            return None
        cur = await db.execute(
            """
            INSERT INTO Deal (
                guildId, ticketChannelId, createdById, buyerId, sellerId, middlemanId,
                paymentInstructionOwnerId, status, createdAt, updatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(guild_id), str(channel_id), str(created_by_id), str(buyer_id),
                str(seller_id), str(middleman_id), str(middleman_id), DEAL_STATUS_PENDING_FORM, now, now,
            ),
        )
        row_id = cur.lastrowid
        await db.commit()
    await write_audit("deal_start", row_id, f"buyer={buyer_id}, seller={seller_id}, middleman={middleman_id}", source="deal")
    await add_deal_log(guild_id, None, "deal_start", created_by_id, None, DEAL_STATUS_PENDING_FORM, f"row_id={row_id}")
    await refresh_staff_operation_panels(guild_id, {"active_deals", "middleman_status"})
    return await get_deal_by_id(row_id)


async def set_deal_warning_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET warningMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def set_deal_summary_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET summaryMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def set_deal_payment_proof_confirmation_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET paymentProofConfirmationMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def set_deal_funds_received_stage_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET fundsReceivedStageMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def set_deal_buyer_confirm_stage_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET buyerConfirmStageMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def set_deal_payout_stage_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET payoutStageMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def set_deal_done_stage_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET doneStageMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def set_deal_completed_summary_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET completedSummaryMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def set_deal_vouch_progress_message(deal_row_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET vouchProgressMessageId=?, updatedAt=? WHERE id=?",
            (str(message_id), _deal_now(), int(deal_row_id)),
        )
        await db.commit()


async def add_deal_log(guild_id, deal_id, action, actor_id, old_value=None, new_value=None, reason=None):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(guild_id),
                str(deal_id) if deal_id is not None else None,
                str(action),
                str(actor_id) if actor_id is not None else None,
                old_value,
                new_value,
                reason,
                now,
            ),
        )
        await db.commit()


async def update_deal_status(
    deal_row_id,
    expected_statuses,
    new_status,
    actor_id,
    action,
    extra_fields=None,
    reason=None,
    *,
    bounded_post_commit=False,
):
    expected = tuple(expected_statuses)
    fields = dict(extra_fields or {})
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        if deal["status"] not in expected:
            await db.rollback()
            return deal, "invalid_status"

        fields["status"] = new_status
        fields["updatedAt"] = now
        set_clause = ", ".join(f"{key}=?" for key in fields.keys())
        values = [str(v) if key.endswith("Id") and v is not None else v for key, v in fields.items()]
        expected_placeholders = ",".join("?" for _ in expected)
        cursor = await db.execute(
            f"UPDATE Deal SET {set_clause} WHERE id=? AND status IN ({expected_placeholders})",
            (*values, int(deal_row_id), *expected),
        )
        if cursor.rowcount == 0:
            await db.rollback()
            return deal, "invalid_status"
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deal["guildId"],
                deal["dealId"],
                action,
                str(actor_id),
                deal["status"],
                new_status,
                reason,
                now,
            ),
        )
        await db.commit()

    async def run_post_commit(coro, *, label, timeout):
        if not bounded_post_commit:
            return await coro
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except Exception as exc:
            logging.warning(
                "Deal post-commit side effect failed "
                "(guild_id=%s, row_id=%s, action=%s, phase=%s, exception=%s)",
                deal["guildId"],
                deal_row_id,
                action,
                label,
                type(exc).__name__,
            )
            return None

    await run_post_commit(
        write_audit(action, deal_row_id, f"{deal['status']} -> {new_status}", source="deal"),
        label="audit",
        timeout=5,
    )
    if _deal_is_archivable_final_status(new_status):
        archive_reason = None if new_status == DEAL_STATUS_COMPLETED else reason
        await run_post_commit(
            archive_deal_if_final(deal_row_id, new_status, actor_id, reason=archive_reason),
            label="archive",
            timeout=10,
        )
    await run_post_commit(
        refresh_staff_operation_panels(
            deal["guildId"],
            {"active_deals", "middleman_status", "dispute_board"},
        ),
        label="panel_refresh",
        timeout=8,
    )
    return await get_deal_by_id(deal_row_id), None


def get_deal_participant_role(deal, user_id):
    uid = str(user_id)
    if uid == str(deal.get("buyerId")):
        return "Buyer"
    if uid == str(deal.get("sellerId")):
        return "Seller"
    if uid == str(deal.get("middlemanId")):
        return "Middleman"
    return None


def get_deal_role_user_id(deal, role):
    role = str(role or "").strip().lower()
    if role == "buyer":
        return str(deal.get("buyerId"))
    if role == "seller":
        return str(deal.get("sellerId"))
    if role == "middleman":
        return str(deal.get("middlemanId"))
    return None


def get_possible_deal_vouches(deal):
    return [
        ("Buyer", "Seller", str(deal.get("buyerId")), str(deal.get("sellerId"))),
        ("Buyer", "Middleman", str(deal.get("buyerId")), str(deal.get("middlemanId"))),
        ("Seller", "Buyer", str(deal.get("sellerId")), str(deal.get("buyerId"))),
        ("Seller", "Middleman", str(deal.get("sellerId")), str(deal.get("middlemanId"))),
        ("Middleman", "Buyer", str(deal.get("middlemanId")), str(deal.get("buyerId"))),
        ("Middleman", "Seller", str(deal.get("middlemanId")), str(deal.get("sellerId"))),
    ]


def can_deal_role_vouch_for(reviewer_role, target_role):
    return (reviewer_role, target_role) in {
        ("Buyer", "Seller"),
        ("Buyer", "Middleman"),
        ("Seller", "Buyer"),
        ("Seller", "Middleman"),
        ("Middleman", "Buyer"),
        ("Middleman", "Seller"),
    }


def _vouch_row_to_dict(row):
    if not row:
        return None
    return dict(zip(VOUCH_COLUMNS, row))


def _reputation_row_to_dict(row):
    if not row:
        return None
    cols = (
        "guildId", "userId", "totalVouches", "verifiedVouches", "verifiedDealVouches",
        "manualApprovedVouches", "averageRating", "trustScore", "buyerVouches", "sellerVouches", "middlemanVouches",
        "removedVouches", "reports", "trustLevel", "updatedAt",
    )
    return dict(zip(cols, row))


def calculate_trust_level(total_verified, avg_rating, reports, removed, buyer_vouches, seller_vouches, middleman_vouches, trust_score, blacklisted=False):
    if blacklisted:
        return "Blacklisted"
    if reports > 0:
        return "Under Review"
    if total_verified < 1:
        return "New User"
    if total_verified >= 500 and avg_rating >= 4.9:
        return "Legendary Trader"
    if total_verified >= 250 and avg_rating >= 4.85:
        return "Elite Trader"
    if total_verified >= 100 and avg_rating >= 4.8:
        return "Trusted Seller"
    if total_verified >= 60 and avg_rating >= 4.7:
        return "Established Seller"
    if total_verified >= 30 and avg_rating >= 4.6:
        return "Reliable Seller"
    if total_verified >= 10 and avg_rating >= 4.5:
        return "Active Trader"
    return "Verified User"


def calculate_trust_score(total_verified, avg_rating, reports, removed, recent_count=0):
    if total_verified <= 0:
        base = 0
    else:
        base = total_verified * (avg_rating / 5.0) * 5 + min(50, recent_count * 2)
    penalty = reports * 25 + removed * 8
    return round(max(0, base - penalty), 2)


async def list_deal_vouches(guild_id, deal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""
            SELECT {VOUCH_SELECT}
            FROM Vouch
            WHERE guildId=? AND dealId=? AND status='active'
              AND vouchType='verified_deal'
              AND approvalStatus='verified'
            ORDER BY id ASC
            """,
            (str(guild_id), str(deal_id)),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_vouch_row_to_dict(row) for row in rows]


async def list_user_vouches(guild_id, user_id, include_removed=False):
    status_filter = "" if include_removed else """
        AND status='active'
        AND (
            (vouchType='verified_deal' AND approvalStatus='verified')
            OR (vouchType='manual' AND approvalStatus='approved')
        )
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""
            SELECT {VOUCH_SELECT}
            FROM Vouch
            WHERE guildId=? AND targetId=? {status_filter}
            ORDER BY id DESC
            """,
            (str(guild_id), str(user_id)),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_vouch_row_to_dict(row) for row in rows]


async def get_vouch_by_id(guild_id, vouch_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""
            SELECT {VOUCH_SELECT}
            FROM Vouch WHERE guildId=? AND id=?
            """,
            (str(guild_id), int(vouch_id)),
        ) as cursor:
            row = await cursor.fetchone()
    return _vouch_row_to_dict(row)


async def get_user_reputation(guild_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT guildId, userId, totalVouches, verifiedVouches, verifiedDealVouches, manualApprovedVouches, averageRating, trustScore,
                   buyerVouches, sellerVouches, middlemanVouches, removedVouches, reports,
                   trustLevel, updatedAt
            FROM UserReputation WHERE guildId=? AND userId=?
            """,
            (str(guild_id), str(user_id)),
        ) as cursor:
            row = await cursor.fetchone()
    rep = _reputation_row_to_dict(row)
    if rep:
        return rep
    return await recalculate_user_reputation(guild_id, user_id)


async def recalculate_user_reputation(guild_id, user_id):
    guild_id = str(guild_id)
    user_id = str(user_id)
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(CASE WHEN vouchType='verified_deal' THEN 1 ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN vouchType='manual' THEN 1 ELSE 0 END),0),
                   COALESCE(AVG(rating),0),
                   COALESCE(SUM(CASE WHEN targetRole='Buyer' THEN 1 ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN targetRole='Seller' THEN 1 ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN targetRole='Middleman' THEN 1 ELSE 0 END),0)
            FROM Vouch
            WHERE guildId=? AND targetId=? AND status='active'
              AND (
                  (vouchType='verified_deal' AND approvalStatus='verified')
                  OR (vouchType='manual' AND approvalStatus='approved')
              )
            """,
            (guild_id, user_id),
        ) as cur:
            total, verified_deal, manual_approved, avg_rating, buyer_v, seller_v, mm_v = await cur.fetchone()
        async with db.execute(
            "SELECT COUNT(*) FROM Vouch WHERE guildId=? AND targetId=? AND status='removed'",
            (guild_id, user_id),
        ) as cur:
            removed = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT status FROM trustModerationStatus WHERE guildId=? AND userId=?",
            (guild_id, user_id),
        ) as cur:
            trust_status_row = await cur.fetchone()
        async with db.execute(
            """
            SELECT COUNT(*) FROM VouchReport r
            JOIN Vouch v ON v.id=r.vouchId AND v.guildId=r.guildId
            WHERE r.guildId=? AND v.targetId=? AND r.status='open'
            """,
            (guild_id, user_id),
        ) as cur:
            reports = (await cur.fetchone())[0]
        async with db.execute(
            """
            SELECT COUNT(*) FROM Vouch
            WHERE guildId=? AND targetId=? AND status='active' AND createdAt >= ?
              AND (
                  (vouchType='verified_deal' AND approvalStatus='verified')
                  OR (vouchType='manual' AND approvalStatus='approved')
              )
            """,
            (guild_id, user_id, (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"),
        ) as cur:
            recent = (await cur.fetchone())[0]

        total = int(total or 0)
        verified_deal = int(verified_deal or 0)
        manual_approved = int(manual_approved or 0)
        verified = verified_deal + manual_approved
        avg_rating = float(avg_rating or 0)
        buyer_v = int(buyer_v or 0)
        seller_v = int(seller_v or 0)
        mm_v = int(mm_v or 0)
        removed = int(removed or 0)
        reports = int(reports or 0)
        score = calculate_trust_score(verified, avg_rating, reports, removed, recent)
        moderation_status = (trust_status_row[0] if trust_status_row else "clear") or "clear"
        blacklisted = moderation_status == "blacklisted"
        level = calculate_trust_level(
            verified,
            avg_rating,
            reports if moderation_status != "under_review" else max(1, reports),
            removed,
            buyer_v,
            seller_v,
            mm_v,
            score,
            blacklisted=blacklisted,
        )
        await db.execute(
            """
            INSERT INTO UserReputation (
                guildId, userId, totalVouches, verifiedVouches, verifiedDealVouches, manualApprovedVouches, averageRating, trustScore,
                buyerVouches, sellerVouches, middlemanVouches, removedVouches, reports,
                trustLevel, updatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guildId, userId) DO UPDATE SET
                totalVouches=excluded.totalVouches,
                verifiedVouches=excluded.verifiedVouches,
                verifiedDealVouches=excluded.verifiedDealVouches,
                manualApprovedVouches=excluded.manualApprovedVouches,
                averageRating=excluded.averageRating,
                trustScore=excluded.trustScore,
                buyerVouches=excluded.buyerVouches,
                sellerVouches=excluded.sellerVouches,
                middlemanVouches=excluded.middlemanVouches,
                removedVouches=excluded.removedVouches,
                reports=excluded.reports,
                trustLevel=excluded.trustLevel,
                updatedAt=excluded.updatedAt
            """,
            (guild_id, user_id, total, verified, verified_deal, manual_approved, avg_rating, score, buyer_v, seller_v, mm_v, removed, reports, level, now),
        )
        await db.commit()
    return {
        "guildId": guild_id,
        "userId": user_id,
        "totalVouches": total,
        "verifiedVouches": verified,
        "verifiedDealVouches": verified_deal,
        "manualApprovedVouches": manual_approved,
        "averageRating": avg_rating,
        "trustScore": score,
        "buyerVouches": buyer_v,
        "sellerVouches": seller_v,
        "middlemanVouches": mm_v,
        "removedVouches": removed,
        "reports": reports,
        "trustLevel": level,
        "updatedAt": now,
    }


async def get_reputation_leaderboard(guild_id, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT DISTINCT targetId FROM Vouch
            WHERE guildId=? AND targetId IS NOT NULL AND status='active'
              AND (
                  (vouchType='verified_deal' AND approvalStatus='verified')
                  OR (vouchType='manual' AND approvalStatus='approved')
              )
            """,
            (str(guild_id),),
        ) as cur:
            rows = await cur.fetchall()
    reps = []
    for (uid,) in rows:
        reps.append(await recalculate_user_reputation(guild_id, uid))
    reps = [r for r in reps if r["trustLevel"] != "Blacklisted" and r["verifiedVouches"] > 0]
    reps.sort(key=lambda r: (r["trustScore"], r["averageRating"], r["verifiedVouches"]), reverse=True)
    return reps[:limit]


async def remove_vouch(guild_id, vouch_id, removed_by, reason):
    reason = str(reason or "").strip()
    if not reason:
        return None, "missing_reason"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            f"""
            SELECT {VOUCH_SELECT}
            FROM Vouch WHERE guildId=? AND id=?
            """,
            (str(guild_id), int(vouch_id)),
        ) as cur:
            row = await cur.fetchone()
        vouch = _vouch_row_to_dict(row)
        if not vouch:
            await db.rollback()
            return None, "not_found"
        if vouch["status"] == "removed":
            await db.rollback()
            return vouch, "already_removed"
        await db.execute(
            "UPDATE Vouch SET status='removed', approvalStatus='removed', removedBy=?, removeReason=?, updatedAt=? WHERE id=?",
            (str(removed_by), reason, now, int(vouch_id)),
        )
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, 'vouch_removed', ?, 'active', 'removed', ?, ?)
            """,
            (str(guild_id), vouch["dealId"], str(removed_by), reason, now),
        )
        await db.commit()
    await write_audit("vouch_removed", vouch_id, reason, source="deal")
    await recalculate_user_reputation(guild_id, vouch["targetId"])
    await on_public_trust_stats_changed(guild_id)
    return await get_vouch_by_id(guild_id, vouch_id), None


async def report_vouch(guild_id, vouch_id, reporter_id, reason, proof_url=None):
    reason = str(reason or "").strip()
    if not reason:
        return None, "missing_reason"
    vouch = await get_vouch_by_id(guild_id, vouch_id)
    if not vouch:
        return None, "not_found"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO VouchReport (guildId, vouchId, reporterId, reason, proofUrl, status, createdAt)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
            """,
            (str(guild_id), int(vouch_id), str(reporter_id), reason, str(proof_url).strip() if proof_url else None, now),
        )
        await db.commit()
        report_id = cur.lastrowid
    await write_audit("vouch_reported", vouch_id, reason, source="deal")
    await recalculate_user_reputation(guild_id, vouch["targetId"])
    return {"id": report_id, "vouch": vouch, "reason": reason, "proofUrl": proof_url, "createdAt": now}, None


async def get_manual_vouch_review_config(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guildId, reviewChannelId, enabled, createdAt, updatedAt FROM manualVouchReviewConfig WHERE guildId=?",
            (str(guild_id),),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "guildId": row[0],
        "reviewChannelId": row[1],
        "enabled": bool(row[2]),
        "createdAt": row[3],
        "updatedAt": row[4],
    }


async def set_manual_vouch_review_config(guild_id, channel_id, enabled=True):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO manualVouchReviewConfig (guildId, reviewChannelId, enabled, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                reviewChannelId=excluded.reviewChannelId,
                enabled=excluded.enabled,
                updatedAt=excluded.updatedAt
            """,
            (str(guild_id), str(channel_id) if channel_id is not None else None, int(bool(enabled)), now, now),
        )
        await db.commit()
    return await get_manual_vouch_review_config(guild_id)


async def disable_manual_vouch_review_config(guild_id):
    current = await get_manual_vouch_review_config(guild_id)
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO manualVouchReviewConfig (guildId, reviewChannelId, enabled, createdAt, updatedAt)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                enabled=0,
                updatedAt=excluded.updatedAt
            """,
            (str(guild_id), current.get("reviewChannelId") if current else None, now, now),
        )
        await db.commit()
    return await get_manual_vouch_review_config(guild_id)


async def get_manual_vouch_panel_config(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guildId, channelId, messageId, enabled, createdAt, updatedAt FROM manualVouchPanelConfig WHERE guildId=?",
            (str(guild_id),),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {
        "guildId": row[0],
        "channelId": row[1],
        "messageId": row[2],
        "enabled": bool(row[3]),
        "createdAt": row[4],
        "updatedAt": row[5],
    }


async def set_manual_vouch_panel_config(guild_id, channel_id, message_id, enabled=True):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO manualVouchPanelConfig (guildId, channelId, messageId, enabled, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                channelId=excluded.channelId,
                messageId=excluded.messageId,
                enabled=excluded.enabled,
                updatedAt=excluded.updatedAt
            """,
            (str(guild_id), str(channel_id) if channel_id is not None else None, str(message_id) if message_id is not None else None, int(bool(enabled)), now, now),
        )
        await db.commit()
    return await get_manual_vouch_panel_config(guild_id)


async def disable_manual_vouch_panel_config(guild_id):
    current = await get_manual_vouch_panel_config(guild_id)
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO manualVouchPanelConfig (guildId, channelId, messageId, enabled, createdAt, updatedAt)
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                enabled=0,
                updatedAt=excluded.updatedAt
            """,
            (
                str(guild_id),
                current.get("channelId") if current else None,
                current.get("messageId") if current else None,
                now,
                now,
            ),
        )
        await db.commit()
    return await get_manual_vouch_panel_config(guild_id)


async def cleanup_rate_limit_events(days=7):
    cutoff = (datetime.utcnow() - timedelta(days=int(days or 7))).isoformat() + "Z"
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM rateLimitEvents WHERE createdAt < ?", (cutoff,))
            await db.commit()
    except Exception as e:
        logging.error("cleanup_rate_limit_events error exception=%s", type(e).__name__)


async def seconds_since_rate_limit_event(guild_id, user_id, action_type):
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM rateLimitEvents WHERE createdAt < ?", (cutoff,))
        async with db.execute(
            """
            SELECT createdAt FROM rateLimitEvents
            WHERE guildId=? AND userId=? AND actionType=?
            ORDER BY createdAt DESC, id DESC
            LIMIT 1
            """,
            (str(guild_id), str(user_id), str(action_type)),
        ) as cursor:
            row = await cursor.fetchone()
        await db.commit()
    if not row or not row[0]:
        return None
    dt = _parse_deal_datetime(row[0])
    if not dt:
        return None
    return max(0, (datetime.utcnow() - dt).total_seconds())


async def record_rate_limit_event(guild_id, user_id, action_type, target_id=None, event_key=None):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO rateLimitEvents (guildId, userId, actionType, targetId, eventKey, createdAt)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(guild_id),
                str(user_id),
                str(action_type),
                str(target_id) if target_id is not None else None,
                str(event_key) if event_key is not None else None,
                now,
            ),
        )
        await db.commit()


async def manual_vouch_submit_guard(guild_id, reviewer_id, target_id=None):
    elapsed = await seconds_since_rate_limit_event(guild_id, reviewer_id, "manual_vouch_submit")
    if elapsed is not None and elapsed < 60:
        return "cooldown"
    reviewer_id = str(reviewer_id)
    target_id_text = str(target_id) if target_id is not None else None
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*) FROM Vouch
            WHERE guildId=? AND reviewerId=? AND vouchType='manual' AND approvalStatus='pending'
            """,
            (str(guild_id), reviewer_id),
        ) as cursor:
            pending_count = (await cursor.fetchone())[0]
        if int(pending_count or 0) >= 3:
            return "too_many_pending"
        if target_id_text:
            async with db.execute(
                """
                SELECT COUNT(*) FROM Vouch
                WHERE guildId=? AND reviewerId=? AND targetId=? AND vouchType='manual' AND approvalStatus='pending'
                """,
                (str(guild_id), reviewer_id, target_id_text),
            ) as cursor:
                duplicate = (await cursor.fetchone())[0]
            if int(duplicate or 0) > 0:
                return "duplicate_pending"
    return None


def _deal_proof_record_is_supported(record):
    if not isinstance(record, dict):
        return False
    content_type = str(record.get("contentType") or record.get("content_type") or "").lower()
    filename = str(record.get("filename") or "").lower()
    if content_type in {"image/png", "image/jpeg", "image/jpg", "image/webp", "application/pdf"}:
        return True
    return any(filename.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".pdf"))


async def create_pending_manual_vouch(guild_id, reviewer_id, target_id, target_raw, target_resolved, rating, review, context, notes, proofs):
    proofs = list(proofs or [])
    if not proofs:
        return None, "missing_proof"
    if len(proofs) > 15:
        return None, "too_many_proofs"
    if any(not _deal_proof_record_is_supported(proof) for proof in proofs):
        return None, "invalid_proof"
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return None, "invalid_rating"
    if rating < 1 or rating > 5:
        return None, "invalid_rating"
    review = str(review or "").strip()
    if len(review) < 3:
        return None, "short_review"
    reviewer_id = str(reviewer_id)
    target_id_text = str(target_id) if target_id is not None else None
    if target_id_text and reviewer_id == target_id_text:
        return None, "self"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            """
            SELECT COUNT(*) FROM Vouch
            WHERE guildId=? AND reviewerId=? AND vouchType='manual' AND approvalStatus='pending'
            """,
            (str(guild_id), reviewer_id),
        ) as cursor:
            pending_count = (await cursor.fetchone())[0]
        if int(pending_count or 0) >= 3:
            await db.rollback()
            return None, "too_many_pending"
        if target_id_text:
            async with db.execute(
                """
                SELECT COUNT(*) FROM Vouch
                WHERE guildId=? AND reviewerId=? AND targetId=? AND vouchType='manual' AND approvalStatus='pending'
                """,
                (str(guild_id), reviewer_id, target_id_text),
            ) as cursor:
                duplicate = (await cursor.fetchone())[0]
            if int(duplicate or 0) > 0:
                await db.rollback()
                return None, "duplicate_pending"
        cur = await db.execute(
            """
            INSERT INTO Vouch (
                guildId, dealId, reviewerId, targetId, reviewerRole, targetRole,
                rating, review, proofUrl, verifiedDeal, status, vouchType, approvalStatus,
                proofCount, proofData, proofSubmittedAt, context, staffNotes, targetRaw,
                targetResolved, createdAt, updatedAt
            )
            VALUES (?, NULL, ?, ?, 'Manual', 'Manual', ?, ?, NULL, 0, 'pending', 'manual', 'pending',
                    ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(guild_id),
                reviewer_id,
                target_id_text,
                rating,
                review,
                len(proofs),
                json.dumps(proofs, ensure_ascii=False),
                now,
                str(context or "").strip() or None,
                str(notes or "").strip() or None,
                str(target_raw or "").strip() or None,
                1 if target_resolved else 0,
                now,
                now,
            ),
        )
        await db.commit()
        row_id = cur.lastrowid
    await write_audit("manual_vouch_submitted", row_id, f"reviewer={reviewer_id}, target={target_id_text or target_raw}", source="deal")
    return await get_vouch_by_id(guild_id, row_id), None


async def approve_manual_vouch(guild_id, vouch_id, actor_id):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {VOUCH_SELECT} FROM Vouch WHERE guildId=? AND id=?", (str(guild_id), int(vouch_id))) as cursor:
            row = await cursor.fetchone()
        vouch = _vouch_row_to_dict(row)
        if not vouch:
            await db.rollback()
            return None, "not_found"
        if vouch.get("vouchType") != "manual" or vouch.get("approvalStatus") != "pending":
            await db.rollback()
            return vouch, "processed"
        if not vouch.get("targetId") or not vouch.get("targetResolved"):
            await db.rollback()
            return vouch, "unresolved_target"
        await db.execute(
            """
            UPDATE Vouch
            SET status='active', approvalStatus='approved', approvedById=?, approvedAt=?, updatedAt=?
            WHERE id=?
            """,
            (str(actor_id), now, now, int(vouch_id)),
        )
        await db.commit()
    updated = await get_vouch_by_id(guild_id, vouch_id)
    await recalculate_user_reputation(guild_id, updated["targetId"])
    await write_audit("manual_vouch_approved", vouch_id, f"approvedBy={actor_id}", source="deal")
    await on_public_trust_vouch_changed(guild_id, vouch_id)
    return updated, None


async def reject_manual_vouch(guild_id, vouch_id, actor_id, reason=None):
    now = _deal_now()
    reason = str(reason or "").strip() or None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {VOUCH_SELECT} FROM Vouch WHERE guildId=? AND id=?", (str(guild_id), int(vouch_id))) as cursor:
            row = await cursor.fetchone()
        vouch = _vouch_row_to_dict(row)
        if not vouch:
            await db.rollback()
            return None, "not_found"
        if vouch.get("vouchType") != "manual" or vouch.get("approvalStatus") != "pending":
            await db.rollback()
            return vouch, "processed"
        await db.execute(
            """
            UPDATE Vouch
            SET status='rejected', approvalStatus='rejected', rejectedById=?, rejectedAt=?,
                rejectionReason=?, updatedAt=?
            WHERE id=?
            """,
            (str(actor_id), now, reason, now, int(vouch_id)),
        )
        await db.commit()
    await write_audit("manual_vouch_rejected", vouch_id, f"rejectedBy={actor_id}", source="deal")
    return await get_vouch_by_id(guild_id, vouch_id), None


SCAM_REPORT_COLUMNS = (
    "id", "guildId", "reporterId", "reportedUserId", "reportedRaw", "reportedResolved",
    "reason", "chronology", "nominalItem", "notes", "proofCount", "proofData",
    "proofSubmittedAt", "status", "reviewMessageId", "reviewChannelId",
    "evidenceThreadId", "reviewedById", "rejectedById", "rejectedAt",
    "rejectionReason", "resolvedById", "resolvedAt", "resolution", "staffNotes",
    "createdAt", "updatedAt",
)
SCAM_REPORT_SELECT = ", ".join(SCAM_REPORT_COLUMNS)


def _scam_report_row_to_dict(row):
    if not row:
        return None
    return dict(zip(SCAM_REPORT_COLUMNS, row))


def _trust_status_row_to_dict(row):
    if not row:
        return None
    cols = ("guildId", "userId", "status", "reason", "sourceType", "sourceId", "updatedById", "updatedAt", "createdAt")
    return dict(zip(cols, row))


async def get_scam_report_review_config(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guildId, reviewChannelId, enabled, createdAt, updatedAt FROM scamReportReviewConfig WHERE guildId=?",
            (str(guild_id),),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {"guildId": row[0], "reviewChannelId": row[1], "enabled": bool(row[2]), "createdAt": row[3], "updatedAt": row[4]}


async def set_scam_report_review_config(guild_id, channel_id, enabled=True):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO scamReportReviewConfig (guildId, reviewChannelId, enabled, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                reviewChannelId=excluded.reviewChannelId,
                enabled=excluded.enabled,
                updatedAt=excluded.updatedAt
            """,
            (str(guild_id), str(channel_id) if channel_id is not None else None, int(bool(enabled)), now, now),
        )
        await db.commit()
    return await get_scam_report_review_config(guild_id)


async def disable_scam_report_review_config(guild_id):
    current = await get_scam_report_review_config(guild_id)
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO scamReportReviewConfig (guildId, reviewChannelId, enabled, createdAt, updatedAt)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET enabled=0, updatedAt=excluded.updatedAt
            """,
            (str(guild_id), current.get("reviewChannelId") if current else None, now, now),
        )
        await db.commit()
    return await get_scam_report_review_config(guild_id)


async def get_scam_report_panel_config(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guildId, channelId, messageId, enabled, createdAt, updatedAt FROM scamReportPanelConfig WHERE guildId=?",
            (str(guild_id),),
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    return {"guildId": row[0], "channelId": row[1], "messageId": row[2], "enabled": bool(row[3]), "createdAt": row[4], "updatedAt": row[5]}


async def set_scam_report_panel_config(guild_id, channel_id, message_id, enabled=True):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO scamReportPanelConfig (guildId, channelId, messageId, enabled, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET
                channelId=excluded.channelId,
                messageId=excluded.messageId,
                enabled=excluded.enabled,
                updatedAt=excluded.updatedAt
            """,
            (str(guild_id), str(channel_id) if channel_id is not None else None, str(message_id) if message_id is not None else None, int(bool(enabled)), now, now),
        )
        await db.commit()
    return await get_scam_report_panel_config(guild_id)


async def disable_scam_report_panel_config(guild_id):
    current = await get_scam_report_panel_config(guild_id)
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO scamReportPanelConfig (guildId, channelId, messageId, enabled, createdAt, updatedAt)
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT(guildId) DO UPDATE SET enabled=0, updatedAt=excluded.updatedAt
            """,
            (str(guild_id), current.get("channelId") if current else None, current.get("messageId") if current else None, now, now),
        )
        await db.commit()
    return await get_scam_report_panel_config(guild_id)


async def get_trust_moderation_status(guild_id, user_id):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guildId, userId, status, reason, sourceType, sourceId, updatedById, updatedAt, createdAt FROM trustModerationStatus WHERE guildId=? AND userId=?",
                (str(guild_id), str(user_id)),
            ) as cursor:
                row = await cursor.fetchone()
    except sqlite3.OperationalError as e:
        if "trustModerationStatus" not in str(e):
            raise
        row = None
    return _trust_status_row_to_dict(row) or {
        "guildId": str(guild_id),
        "userId": str(user_id),
        "status": "clear",
        "reason": None,
        "sourceType": None,
        "sourceId": None,
        "updatedById": None,
        "updatedAt": None,
        "createdAt": None,
    }


async def set_trust_moderation_status(guild_id, user_id, status, reason, updated_by_id, source_type=None, source_id=None):
    status = str(status or "").strip().lower()
    if status not in {"clear", "under_review", "blacklisted"}:
        return None, "invalid_status"
    reason = str(reason or "").strip()
    if not reason:
        return None, "missing_reason"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO trustModerationStatus (
                guildId, userId, status, reason, sourceType, sourceId, updatedById, updatedAt, createdAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guildId, userId) DO UPDATE SET
                status=excluded.status,
                reason=excluded.reason,
                sourceType=excluded.sourceType,
                sourceId=excluded.sourceId,
                updatedById=excluded.updatedById,
                updatedAt=excluded.updatedAt
            """,
            (str(guild_id), str(user_id), status, reason, source_type, str(source_id) if source_id is not None else None, str(updated_by_id), now, now),
        )
        await db.commit()
    await write_audit("trust_status_updated", user_id, f"{status}: {reason[:120]}", source="deal")
    await on_public_trust_stats_changed(guild_id)
    await refresh_staff_operation_panels(guild_id, {"trust_warning"})
    return await get_trust_moderation_status(guild_id, user_id), None


async def scam_report_submit_guard(guild_id, reporter_id, reported_user_id=None):
    elapsed = await seconds_since_rate_limit_event(guild_id, reporter_id, "scam_report_submit")
    if elapsed is not None and elapsed < 120:
        return "cooldown"
    reporter_id = str(reporter_id)
    reported_id_text = str(reported_user_id) if reported_user_id is not None else None
    if reported_id_text:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """
                SELECT COUNT(*) FROM scammerReports
                WHERE guildId=? AND reporterId=? AND reportedUserId=?
                  AND status IN ('pending', 'under_review')
                """,
                (str(guild_id), reporter_id, reported_id_text),
            ) as cursor:
                duplicate = (await cursor.fetchone())[0]
        if int(duplicate or 0) > 0:
            return "duplicate_pending"
    return None


async def create_pending_scam_report(guild_id, reporter_id, reported_user_id, reported_raw, reported_resolved, reason, chronology, nominal_item, notes, proofs):
    proofs = list(proofs or [])
    if not proofs:
        return None, "missing_proof"
    if len(proofs) > 15:
        return None, "too_many_proofs"
    if any(not _deal_proof_record_is_supported(proof) for proof in proofs):
        return None, "invalid_proof"
    reason = str(reason or "").strip()
    chronology = str(chronology or "").strip()
    if len(reason) < 3:
        return None, "short_reason"
    if len(chronology) < 5:
        return None, "short_chronology"
    reporter_id = str(reporter_id)
    reported_id_text = str(reported_user_id) if reported_user_id is not None else None
    if reported_id_text and reporter_id == reported_id_text:
        return None, "self"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        if reported_id_text:
            async with db.execute(
                """
                SELECT COUNT(*) FROM scammerReports
                WHERE guildId=? AND reporterId=? AND reportedUserId=? AND status IN ('pending', 'under_review')
                """,
                (str(guild_id), reporter_id, reported_id_text),
            ) as cursor:
                duplicate = (await cursor.fetchone())[0]
            if int(duplicate or 0) > 0:
                await db.rollback()
                return None, "duplicate_pending"
        cur = await db.execute(
            """
            INSERT INTO scammerReports (
                guildId, reporterId, reportedUserId, reportedRaw, reportedResolved,
                reason, chronology, nominalItem, notes, proofCount, proofData,
                proofSubmittedAt, status, createdAt, updatedAt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                str(guild_id), reporter_id, reported_id_text, str(reported_raw or "").strip() or None,
                1 if reported_resolved else 0, reason, chronology,
                str(nominal_item or "").strip() or None, str(notes or "").strip() or None,
                len(proofs), json.dumps(proofs, ensure_ascii=False), now, now, now,
            ),
        )
        await db.commit()
        row_id = cur.lastrowid
    await write_audit("scammer_report_submitted", row_id, f"reporter={reporter_id}, reported={reported_id_text or reported_raw}", source="deal")
    await refresh_staff_operation_panels(guild_id, {"trust_warning"})
    return await get_scam_report_by_id(guild_id, row_id), None


async def get_scam_report_by_id(guild_id, report_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"SELECT {SCAM_REPORT_SELECT} FROM scammerReports WHERE guildId=? AND id=?", (str(guild_id), int(report_id))) as cursor:
            row = await cursor.fetchone()
    return _scam_report_row_to_dict(row)


async def set_scam_report_review_message(guild_id, report_id, channel_id, message_id, thread_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE scammerReports SET reviewChannelId=?, reviewMessageId=?, evidenceThreadId=?, updatedAt=? WHERE guildId=? AND id=?",
            (str(channel_id), str(message_id), str(thread_id) if thread_id else None, _deal_now(), str(guild_id), int(report_id)),
        )
        await db.commit()
    return await get_scam_report_by_id(guild_id, report_id)


SCAM_REPORT_FINAL_STATUSES = {"blacklisted", "confirmed_scam", "rejected", "resolved", "closed"}


async def update_scam_report_status(guild_id, report_id, actor_id, status, reason=None, note=None, resolution=None, evidence_summary=None, duration=None):
    status = str(status or "").strip().lower()
    if status not in {"under_review", "confirmed_scam", "blacklisted", "rejected", "resolved", "closed"}:
        return None, "invalid_status"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {SCAM_REPORT_SELECT} FROM scammerReports WHERE guildId=? AND id=?", (str(guild_id), int(report_id))) as cursor:
            row = await cursor.fetchone()
        report = _scam_report_row_to_dict(row)
        if not report:
            await db.rollback()
            return None, "not_found"
        if report.get("status") in SCAM_REPORT_FINAL_STATUSES:
            await db.rollback()
            return report, "processed"
        if str(report.get("status") or "").lower() == status:
            await db.rollback()
            return report, "processed"
        if status in SCAM_REPORT_FINAL_STATUSES and report.get("status") in SCAM_REPORT_FINAL_STATUSES:
            await db.rollback()
            return report, "processed"
        staff_notes = "\n".join(part for part in (report.get("staffNotes"), note, evidence_summary, duration) if str(part or "").strip()) or None
        fields = {"status": status, "reviewedById": str(actor_id), "staffNotes": staff_notes, "updatedAt": now}
        if status == "rejected":
            fields.update({"rejectedById": str(actor_id), "rejectedAt": now, "rejectionReason": str(reason or "").strip() or None})
        if status in ("resolved", "closed"):
            fields.update({"resolvedById": str(actor_id), "resolvedAt": now, "resolution": str(resolution or reason or "").strip() or None})
        set_clause = ", ".join(f"{key}=?" for key in fields)
        await db.execute(
            f"UPDATE scammerReports SET {set_clause} WHERE guildId=? AND id=?",
            (*fields.values(), str(guild_id), int(report_id)),
        )
        await db.commit()
    updated = await get_scam_report_by_id(guild_id, report_id)
    if updated.get("reportedUserId") and status in ("under_review", "confirmed_scam", "blacklisted"):
        trust_status = "under_review" if status == "under_review" else "blacklisted"
        await set_trust_moderation_status(guild_id, updated["reportedUserId"], trust_status, reason or updated.get("reason") or status, actor_id, "scam_report", report_id)
        await recalculate_user_reputation(guild_id, updated["reportedUserId"])
    await write_audit(f"scam_report_{status}", report_id, str(reason or resolution or "")[:120], source="deal")
    await refresh_staff_operation_panels(guild_id, {"trust_warning"})
    return updated, None


async def add_scam_report_note(guild_id, report_id, actor_id, note):
    note = str(note or "").strip()
    if not note:
        return None, "missing_note"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {SCAM_REPORT_SELECT} FROM scammerReports WHERE guildId=? AND id=?", (str(guild_id), int(report_id))) as cursor:
            row = await cursor.fetchone()
        report = _scam_report_row_to_dict(row)
        if not report:
            await db.rollback()
            return None, "not_found"
        combined = "\n".join(part for part in (report.get("staffNotes"), f"{_deal_now()} <{actor_id}> {note}") if str(part or "").strip())
        await db.execute(
            "UPDATE scammerReports SET staffNotes=?, updatedAt=? WHERE guildId=? AND id=?",
            (combined, now, str(guild_id), int(report_id)),
        )
        await db.commit()
    await write_audit("scam_report_note_added", report_id, note[:120], source="deal")
    return await get_scam_report_by_id(guild_id, report_id), None


async def detect_suspicious_vouch(vouch):
    reasons = []
    review = str(vouch.get("review") or "").strip()
    if len(review) < 12:
        reasons.append("review terlalu pendek")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*) FROM Vouch
            WHERE guildId=? AND reviewerId=? AND targetId=? AND status='active'
            """,
            (vouch["guildId"], vouch["reviewerId"], vouch["targetId"]),
        ) as cur:
            same_pair = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM Vouch WHERE guildId=? AND reviewerId=? AND createdAt >= ?",
            (vouch["guildId"], vouch["reviewerId"], (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"),
        ) as cur:
            recent = (await cur.fetchone())[0]
        async with db.execute(
            """
            SELECT COUNT(*) FROM VouchReport r
            JOIN Vouch v ON v.id=r.vouchId AND v.guildId=r.guildId
            WHERE r.guildId=?
              AND (v.reviewerId IN (?, ?) OR v.targetId IN (?, ?))
              AND r.status='open'
            """,
            (
                vouch["guildId"],
                vouch["reviewerId"],
                vouch["targetId"],
                vouch["reviewerId"],
                vouch["targetId"],
            ),
        ) as cur:
            reports = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT nominalItem FROM Deal WHERE guildId=? AND dealId=?",
            (vouch["guildId"], vouch["dealId"]),
        ) as cur:
            deal_row = await cur.fetchone()
    if same_pair > 1:
        reasons.append("pasangan reviewer/target berulang")
    if recent >= 5:
        reasons.append("terlalu banyak vouch dalam waktu singkat")
    if reports > 0:
        reasons.append("user punya report terbuka")
    nominal = int(deal_row[0] or 0) if deal_row else 0
    if not vouch.get("proofUrl") and nominal >= 1_000_000:
        reasons.append("high-value deal tanpa proof")
    return reasons


async def create_verified_deal_vouch(deal, reviewer_id, target_id, rating, review, proof_url=None):
    if not deal or deal.get("status") != DEAL_STATUS_COMPLETED or not deal.get("isVouchEligible"):
        return None, "not_completed"
    reviewer_id = str(reviewer_id)
    target_id = str(target_id)
    if reviewer_id == target_id:
        return None, "self"
    reviewer_role = get_deal_participant_role(deal, reviewer_id)
    target_role = get_deal_participant_role(deal, target_id)
    if not reviewer_role or not target_role:
        return None, "not_participant"
    if not can_deal_role_vouch_for(reviewer_role, target_role):
        return None, "not_allowed"
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return None, "invalid_rating"
    if rating < 1 or rating > 5:
        return None, "invalid_rating"
    review = str(review or "").strip()
    if not review:
        return None, "empty_review"
    if len(review) < 3:
        return None, "short_review"
    proof_url = None

    now = _deal_now()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """
                INSERT INTO Vouch (
                    guildId, dealId, reviewerId, targetId, reviewerRole, targetRole,
                    rating, review, proofUrl, verifiedDeal, status, vouchType, approvalStatus,
                    proofCount, targetResolved, createdAt, updatedAt
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', 'verified_deal', 'verified', 0, 1, ?, ?)
                """,
                (
                    str(deal["guildId"]),
                    str(deal["dealId"]),
                    reviewer_id,
                    target_id,
                    reviewer_role,
                    target_role,
                    rating,
                    review,
                    str(proof_url).strip() if proof_url else None,
                    now,
                    now,
                ),
            )
            await db.execute(
                """
                INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
                VALUES (?, ?, 'deal_vouch_submitted', ?, NULL, ?, ?, ?)
                """,
                (
                    str(deal["guildId"]),
                    str(deal["dealId"]),
                    reviewer_id,
                    f"{reviewer_role}->{target_role}",
                    f"rating={rating}",
                    now,
                ),
            )
            await db.commit()
            row_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return None, "duplicate"

    await write_audit("deal_vouch_submitted", deal["dealId"], f"{reviewer_role}->{target_role} rating={rating}", source="deal")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""
            SELECT {VOUCH_SELECT}
            FROM Vouch WHERE id=?
            """,
            (row_id,),
        ) as cursor:
            row = await cursor.fetchone()
    vouch = _vouch_row_to_dict(row)
    await recalculate_user_reputation(deal["guildId"], target_id)
    await on_public_trust_vouch_changed(deal["guildId"], row_id)
    suspicious = await detect_suspicious_vouch(vouch)
    if suspicious:
        await add_deal_log(
            deal["guildId"],
            deal["dealId"],
            "vouch_suspicious",
            reviewer_id,
            None,
            f"vouch_id={vouch['id']}",
            ", ".join(suspicious),
        )
    return vouch, None


DEAL_EDIT_MAX_MONEY = 999_999_999_999_999
DEAL_EDIT_PAYMENT_METHOD_MAX_LENGTH = 200
DEAL_EDIT_DESCRIPTION_MAX_LENGTH = 1000
DEAL_FORCE_EDIT_REASON_MAX_LENGTH = 300


@dataclass
class DealEditMutationResult:
    code: str
    deal: dict = None
    committed: bool = False
    changed_fields: tuple = ()
    old_status: str = None
    new_status: str = None
    deal_log_written: bool = False


def _parse_deal_timestamp_utc(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def deal_payment_proof_is_active(deal):
    if not deal:
        return False
    has_proof = bool(
        str(deal.get("paymentProofUrl") or "").strip()
        or str(deal.get("paymentProofMessageId") or "").strip()
        or str(deal.get("paymentProofSubmittedAt") or "").strip()
    )
    if not has_proof:
        return False
    invalidated_raw = str(deal.get("paymentProofInvalidatedAt") or "").strip()
    if not invalidated_raw:
        return True
    submitted = _parse_deal_timestamp_utc(deal.get("paymentProofSubmittedAt"))
    invalidated = _parse_deal_timestamp_utc(invalidated_raw)
    if submitted is None or invalidated is None:
        return False
    return submitted > invalidated


# Compatibility alias for older internal call sites.
_deal_payment_proof_is_active = deal_payment_proof_is_active


def _contains_disallowed_control_characters(value, *, allow_newline=False):
    for char in value:
        if allow_newline and char == "\n":
            continue
        if unicodedata.category(char).startswith("C"):
            return True
    return False


def normalize_force_edit_reason(reason):
    text = str(reason or "").strip()
    if not text or len(text) > DEAL_FORCE_EDIT_REASON_MAX_LENGTH:
        return None
    if "\r" in text or "\n" in text or _contains_disallowed_control_characters(text):
        return None
    return " ".join(text.split())


def _normalize_deal_edit_single_line(value, *, max_length):
    text = str(value or "").strip()
    if not text or len(text) > max_length:
        return None
    if "\r" in text or "\n" in text or _contains_disallowed_control_characters(text):
        return None
    return text


def _normalize_deal_edit_description(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text or len(text) > DEAL_EDIT_DESCRIPTION_MAX_LENGTH:
        return None
    if _contains_disallowed_control_characters(text, allow_newline=True):
        return None
    return text


def _parse_deal_edit_nominal(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        amount = value
    else:
        text = str(value or "").strip()
        text = re.sub(r"(?i)^rp\s*", "", text).strip()
        if re.fullmatch(r"[0-9]+", text):
            digits = text
        elif re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{3})+", text):
            digits = text.replace(".", "")
        elif re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+", text):
            digits = text.replace(",", "")
        else:
            return None
        if len(digits) > 15:
            return None
        try:
            amount = int(digits)
        except (TypeError, ValueError, OverflowError):
            return None
    if amount <= 0 or amount > DEAL_EDIT_MAX_MONEY:
        return None
    return amount


def normalize_deal_edit_fields(payment_penjual, payment_pembeli, nominal_item, fee_type, description):
    payment_penjual = _normalize_deal_edit_single_line(
        payment_penjual,
        max_length=DEAL_EDIT_PAYMENT_METHOD_MAX_LENGTH,
    )
    payment_pembeli = _normalize_deal_edit_single_line(
        payment_pembeli,
        max_length=DEAL_EDIT_PAYMENT_METHOD_MAX_LENGTH,
    )
    nominal = _parse_deal_edit_nominal(nominal_item)
    normalized_fee_type = str(fee_type or "").strip().capitalize()
    normalized_description = _normalize_deal_edit_description(description)
    if payment_penjual is None or payment_pembeli is None or nominal is None or normalized_description is None:
        return None, "invalid_input"
    if normalized_fee_type not in ("Inc", "Exc"):
        return None, "invalid_input"
    mm_fee = calculate_middleman_fee(nominal)
    if normalized_fee_type == "Exc":
        buyer_pays = nominal + mm_fee
        seller_receives = nominal
    else:
        buyer_pays = nominal
        seller_receives = nominal - mm_fee
    if seller_receives < 0 or buyer_pays > DEAL_EDIT_MAX_MONEY:
        return None, "invalid_input"
    return {
        "paymentPenjual": payment_penjual,
        "paymentPembeli": payment_pembeli,
        "nominalItem": nominal,
        "feeType": normalized_fee_type,
        "mmFee": mm_fee,
        "buyerPays": buyer_pays,
        "sellerReceives": seller_receives,
        "description": normalized_description,
    }, None


def _canonical_existing_edit_value(field_name, value):
    if field_name in ("nominalItem", "mmFee", "buyerPays", "sellerReceives"):
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            return value
    if field_name == "feeType":
        return str(value or "").strip().capitalize()
    if field_name in ("paymentPenjual", "paymentPembeli"):
        return str(value or "").strip()
    if field_name == "description":
        return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return value


async def update_deal_editable_fields(
    deal_row_id,
    actor_id,
    *,
    payment_penjual,
    payment_pembeli,
    nominal_item,
    fee_type,
    description,
    force=False,
    force_reason=None,
):
    normalized, validation_error = normalize_deal_edit_fields(
        payment_penjual,
        payment_pembeli,
        nominal_item,
        fee_type,
        description,
    )
    if validation_error:
        return DealEditMutationResult(code=validation_error)
    safe_force_reason = normalize_force_edit_reason(force_reason) if force else None
    if force and safe_force_reason is None:
        return DealEditMutationResult(code="invalid_input")
    now = _deal_now()
    deal = None
    changed_fields = ()
    action = "deal_force_edit" if force else "deal_edit"
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
                row = await cursor.fetchone()
            deal = _deal_row_to_dict(row)
            if not deal:
                await db.rollback()
                return DealEditMutationResult(code="not_found")
            active_payment_proof = deal_payment_proof_is_active(deal)
            if not force and (deal["status"] != DEAL_STATUS_WAITING_FUNDS or active_payment_proof):
                await db.rollback()
                return DealEditMutationResult(code="invalid_status", deal=deal, old_status=deal.get("status"), new_status=deal.get("status"))

            changed_fields = tuple(
                key for key, value in normalized.items()
                if _canonical_existing_edit_value(key, deal.get(key)) != value
            )
            if not changed_fields:
                await db.rollback()
                return DealEditMutationResult(
                    code="no_change",
                    deal=deal,
                    old_status=deal.get("status"),
                    new_status=deal.get("status"),
                )

            financial_fields = {
                "paymentPenjual", "paymentPembeli", "nominalItem", "feeType",
                "mmFee", "buyerPays", "sellerReceives",
            }
            financial_changed = any(field in financial_fields for field in changed_fields)
            fields = dict(normalized)
            fields["updatedAt"] = now
            log_reason = "force edit fields updated" if force else "deal details edited"

            if force and financial_changed and deal["status"] == DEAL_STATUS_WAITING_FUNDS and active_payment_proof:
                fields.update({
                    "paymentProofInvalidatedAt": now,
                    "paymentProofInvalidatedById": str(actor_id),
                    "paymentProofInvalidationReason": safe_force_reason,
                })
                action = "deal_force_edit_proof_invalidated"
                log_reason = "force financial edit invalidated active payment proof"
            elif force and financial_changed and deal["status"] == DEAL_STATUS_DISPUTED:
                previous_status = infer_dispute_restore_status(deal)
                if previous_status == DEAL_STATUS_WAITING_FUNDS and active_payment_proof:
                    fields.update({
                        "paymentProofInvalidatedAt": now,
                        "paymentProofInvalidatedById": str(actor_id),
                        "paymentProofInvalidationReason": safe_force_reason,
                    })
                action = "deal_force_edit_disputed_record"
                log_reason = "force financial edit updated disputed deal"
            elif force and financial_changed and deal["status"] not in (
                DEAL_STATUS_WAITING_FUNDS,
                DEAL_STATUS_COMPLETED,
                DEAL_STATUS_CANCELLED,
                "Voided/Duplicate",
                "Expired",
            ):
                fields.update({
                    "status": DEAL_STATUS_DISPUTED,
                    "disputedById": str(actor_id),
                    "disputedAt": now,
                    "disputeReason": safe_force_reason,
                    "disputeProofUrl": None,
                    "disputePreviousStatus": deal["status"],
                    "statusBeforeDispute": deal["status"],
                    "isVouchEligible": 0,
                })
                action = "deal_force_edit_disputed"
                log_reason = "force financial edit moved deal to manual review"

            set_clause = ", ".join(f"{key}=?" for key in fields.keys())
            values = [str(v) if key.endswith("Id") and v is not None else v for key, v in fields.items()]
            cursor = await db.execute(
                f"UPDATE Deal SET {set_clause} WHERE id=? AND status=?",
                (*values, int(deal_row_id), deal["status"]),
            )
            if cursor.rowcount != 1:
                await db.rollback()
                return DealEditMutationResult(
                    code="stale",
                    deal=deal,
                    changed_fields=changed_fields,
                    old_status=deal.get("status"),
                    new_status=deal.get("status"),
                )
            await db.execute(
                """
                INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
                VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    deal["guildId"],
                    deal["dealId"],
                    action,
                    str(actor_id),
                    json.dumps({"changedFields": list(changed_fields)}, ensure_ascii=False),
                    log_reason,
                    now,
                ),
            )
            async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
                updated_row = await cursor.fetchone()
            updated = _deal_row_to_dict(updated_row)
            await db.commit()
    except Exception as exc:
        logging.warning(
            "Deal edit database operation failed (row_id=%s, force=%s, exception=%s)",
            deal_row_id,
            bool(force),
            type(exc).__name__,
        )
        return DealEditMutationResult(
            code="database_failure",
            deal=deal,
            changed_fields=changed_fields,
            old_status=(deal or {}).get("status"),
            new_status=(deal or {}).get("status"),
        )

    postprocess_failed = False
    try:
        await write_audit(
            action,
            deal_row_id,
            f"changed_fields={','.join(changed_fields)}",
            source="deal",
        )
    except Exception as exc:
        logging.warning(
            "Deal edit audit failed after commit (guild_id=%s, row_id=%s, action=%s, exception=%s)",
            deal["guildId"],
            deal_row_id,
            action,
            type(exc).__name__,
        )
        postprocess_failed = True
    try:
        await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "middleman_status", "dispute_board"})
    except Exception as exc:
        logging.warning(
            "Deal edit panel refresh failed after commit (guild_id=%s, row_id=%s, action=%s, exception=%s)",
            deal["guildId"],
            deal_row_id,
            action,
            type(exc).__name__,
        )
        postprocess_failed = True
    return DealEditMutationResult(
        code="committed_postprocess_failed" if postprocess_failed else "changed",
        deal=updated,
        committed=True,
        changed_fields=changed_fields,
        old_status=deal.get("status"),
        new_status=(updated or {}).get("status"),
        deal_log_written=True,
    )


async def cancel_deal(deal_row_id, actor_id, reason):
    reason = str(reason or "").strip()
    if not reason:
        return None, "missing_reason"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        if deal["status"] in (DEAL_STATUS_COMPLETED, "Cancelled", "Voided/Duplicate"):
            await db.rollback()
            return deal, "invalid_status"
        cursor = await db.execute(
            """
            UPDATE Deal
            SET status=?, cancelledById=?, cancelledAt=?, cancelReason=?,
                isVouchEligible=0, updatedAt=?
            WHERE id=? AND status NOT IN (?, ?, ?)
            """,
            (
                DEAL_STATUS_CANCELLED, str(actor_id), now, reason, now, int(deal_row_id),
                DEAL_STATUS_COMPLETED, DEAL_STATUS_CANCELLED, "Voided/Duplicate",
            ),
        )
        if cursor.rowcount == 0:
            await db.rollback()
            return deal, "invalid_status"
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, 'deal_cancel', ?, ?, ?, ?, ?)
            """,
            (deal["guildId"], deal["dealId"], str(actor_id), deal["status"], DEAL_STATUS_CANCELLED, reason, now),
        )
        await db.commit()
    await write_audit("deal_cancel", deal_row_id, reason, source="deal")
    await archive_deal_if_final(deal_row_id, DEAL_STATUS_CANCELLED, actor_id, reason=reason)
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "middleman_status", "dispute_board"})
    return await get_deal_by_id(deal_row_id), None


async def request_deal_cancel(deal_row_id, actor_id, reason):
    reason = str(reason or "").strip()
    if not reason:
        return None, "missing_reason"
    deal = await get_deal_by_id(deal_row_id)
    if not deal:
        return None, "not_found"
    if deal["status"] in (DEAL_STATUS_COMPLETED, "Cancelled", "Voided/Duplicate"):
        return deal, "invalid_status"
    await add_deal_log(deal["guildId"], deal["dealId"], "deal_cancel_requested", actor_id, deal["status"], deal["status"], reason)
    await write_audit("deal_cancel_requested", deal_row_id, reason, source="deal")
    return deal, None


async def dispute_deal(deal_row_id, actor_id, reason, proof_url=None):
    reason = str(reason or "").strip()
    if not reason:
        return None, "missing_reason"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        if deal["status"] in (DEAL_STATUS_COMPLETED, "Cancelled", "Voided/Duplicate", DEAL_STATUS_DISPUTED):
            await db.rollback()
            return deal, "invalid_status"
        cursor = await db.execute(
            """
            UPDATE Deal
            SET status=?, disputedById=?, disputedAt=?, disputeReason=?, disputeProofUrl=?,
                disputePreviousStatus=?, statusBeforeDispute=?, isVouchEligible=0, updatedAt=?
            WHERE id=? AND status NOT IN (?, ?, ?, ?)
            """,
            (
                DEAL_STATUS_DISPUTED, str(actor_id), now, reason,
                str(proof_url).strip() if proof_url else None,
                deal["status"], deal["status"], now, int(deal_row_id),
                DEAL_STATUS_COMPLETED, DEAL_STATUS_CANCELLED, "Voided/Duplicate", DEAL_STATUS_DISPUTED,
            ),
        )
        if cursor.rowcount == 0:
            await db.rollback()
            return deal, "invalid_status"
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, 'deal_dispute', ?, ?, ?, ?, ?)
            """,
            (deal["guildId"], deal["dealId"], str(actor_id), deal["status"], DEAL_STATUS_DISPUTED, reason, now),
        )
    await db.commit()
    await write_audit("deal_dispute", deal_row_id, reason, source="deal")
    await on_public_trust_stats_changed(deal["guildId"])
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "dispute_board"})
    return await get_deal_by_id(deal_row_id), None


def infer_dispute_restore_status(deal):
    if not deal:
        return DEAL_STATUS_PENDING_FORM
    if deal.get("statusBeforeDispute"):
        return DEAL_STATUS_FUNDS_RECEIVED if deal["statusBeforeDispute"] == DEAL_STATUS_ITEM_SENT else deal["statusBeforeDispute"]
    if deal.get("disputePreviousStatus"):
        return DEAL_STATUS_FUNDS_RECEIVED if deal["disputePreviousStatus"] == DEAL_STATUS_ITEM_SENT else deal["disputePreviousStatus"]
    if deal.get("completedAt"):
        return None
    if deal.get("buyerConfirmedAt"):
        return DEAL_STATUS_BUYER_CONFIRMED
    if deal.get("itemSentAt"):
        return DEAL_STATUS_FUNDS_RECEIVED
    if deal.get("fundsReceivedAt"):
        return DEAL_STATUS_FUNDS_RECEIVED
    if deal.get("formSubmittedAt") or deal.get("dealId"):
        return DEAL_STATUS_WAITING_FUNDS
    return DEAL_STATUS_PENDING_FORM


async def resolve_deal_dispute(deal_row_id, actor_id, resolution):
    resolution = str(resolution or "").strip()
    if not resolution:
        return None, "missing_resolution"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        if deal["status"] != DEAL_STATUS_DISPUTED:
            await db.rollback()
            return deal, "invalid_status"
        previous = infer_dispute_restore_status(deal)
        if not previous:
            await db.rollback()
            return deal, "missing_previous_status"
        new_status = previous
        cursor = await db.execute(
            """
            UPDATE Deal
            SET status=?, disputeResolvedById=?, disputeResolvedAt=?, disputeResolution=?, updatedAt=?
            WHERE id=? AND status=?
            """,
            (new_status, str(actor_id), now, resolution, now, int(deal_row_id), DEAL_STATUS_DISPUTED),
        )
        if cursor.rowcount == 0:
            await db.rollback()
            return deal, "invalid_status"
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, 'deal_dispute_resolved', ?, ?, ?, ?, ?)
            """,
            (deal["guildId"], deal["dealId"], str(actor_id), DEAL_STATUS_DISPUTED, new_status, resolution, now),
        )
    await db.commit()
    await write_audit("deal_dispute_resolved", deal_row_id, resolution, source="deal")
    await on_public_trust_stats_changed(deal["guildId"])
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "dispute_board"})
    return await get_deal_by_id(deal_row_id), None


async def force_deal_status(deal_row_id, actor_id, status, reason):
    status = str(status or "").strip()
    reason = str(reason or "").strip()
    if not status or not reason:
        return None, "missing"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        vouch_ok = 1 if status == DEAL_STATUS_COMPLETED else 0 if status in ("Cancelled", "Voided/Duplicate", DEAL_STATUS_DISPUTED) else deal.get("isVouchEligible", 0)
        await db.execute(
            "UPDATE Deal SET status=?, isVouchEligible=?, updatedAt=? WHERE id=?",
            (status, vouch_ok, now, int(deal_row_id)),
        )
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, 'deal_force_status', ?, ?, ?, ?, ?)
            """,
            (deal["guildId"], deal["dealId"], str(actor_id), deal["status"], status, reason, now),
        )
        await db.commit()
    await write_audit("deal_force_status", deal_row_id, f"{status}: {reason}", source="deal")
    if _deal_is_archivable_final_status(status):
        await archive_deal_if_final(deal_row_id, status, actor_id, reason=reason)
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "middleman_status", "dispute_board"})
    return await get_deal_by_id(deal_row_id), None


async def mark_deal_void_duplicate(deal_row_id, actor_id, reason):
    reason = str(reason or "").strip()
    if not reason:
        return None, "missing_reason"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        await db.execute(
            "UPDATE Deal SET status='Voided/Duplicate', isVouchEligible=0, updatedAt=? WHERE id=?",
            (now, int(deal_row_id)),
        )
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, 'deal_void_duplicate', ?, ?, 'Voided/Duplicate', ?, ?)
            """,
            (deal["guildId"], deal["dealId"], str(actor_id), deal["status"], reason, now),
        )
        await db.commit()
    await write_audit("deal_void_duplicate", deal_row_id, reason, source="deal")
    await archive_deal_if_final(deal_row_id, "Voided/Duplicate", actor_id, reason=reason)
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "middleman_status", "dispute_board"})
    return await get_deal_by_id(deal_row_id), None


async def add_deal_note(guild_id, deal_id, actor_id, note):
    note = str(note or "").strip()
    if not note:
        return None, "empty_note"
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO DealNote (guildId, dealId, actorId, note, createdAt) VALUES (?, ?, ?, ?, ?)",
            (str(guild_id), str(deal_id), str(actor_id), note, now),
        )
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, 'deal_note_added', ?, NULL, NULL, ?, ?)
            """,
            (str(guild_id), str(deal_id), str(actor_id), note, now),
        )
        await db.commit()
        row_id = cur.lastrowid
    await write_audit("deal_note_added", deal_id, f"note_id={row_id}", source="deal")
    return row_id, None


async def list_deal_notes(guild_id, deal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, guildId, dealId, actorId, note, createdAt FROM DealNote WHERE guildId=? AND dealId=? ORDER BY id ASC",
            (str(guild_id), str(deal_id)),
        ) as cursor:
            rows = await cursor.fetchall()
    return [
        {"id": r[0], "guildId": r[1], "dealId": r[2], "actorId": r[3], "note": r[4], "createdAt": r[5]}
        for r in rows
    ]


async def list_deal_logs(guild_id, deal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, action, actorId, oldValue, newValue, reason, createdAt FROM DealLog WHERE guildId=? AND dealId=? ORDER BY id ASC",
            (str(guild_id), str(deal_id)),
        ) as cursor:
            rows = await cursor.fetchall()
    return [
        {"id": r[0], "action": r[1], "actorId": r[2], "oldValue": r[3], "newValue": r[4], "reason": r[5], "createdAt": r[6]}
        for r in rows
    ]


async def list_active_deals(guild_id):
    placeholders = ",".join("?" for _ in DEAL_ACTIVE_STATUSES)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT {DEAL_SELECT} FROM Deal WHERE guildId=? AND status IN ({placeholders}) ORDER BY updatedAt DESC, id DESC",
            (str(guild_id), *DEAL_ACTIVE_STATUSES),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_deal_row_to_dict(row) for row in rows]


def _parse_deal_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


async def _get_deal_reminder_last_sent(guild_id, deal_id, reminder_type):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT sentAt FROM DealReminderLog WHERE guildId=? AND dealId=? AND reminderType=?",
            (str(guild_id), str(deal_id), str(reminder_type)),
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


async def _mark_deal_reminder_sent(guild_id, deal_id, reminder_type):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO DealReminderLog (guildId, dealId, reminderType, sentAt)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guildId, dealId, reminderType) DO UPDATE SET sentAt=excluded.sentAt
            """,
            (str(guild_id), str(deal_id), str(reminder_type), now),
        )
        await db.commit()


async def should_send_deal_reminder(config, deal, reminder_type, anchor_time, interval_seconds):
    anchor = _parse_deal_datetime(anchor_time)
    if not anchor:
        return False
    now = datetime.utcnow()
    if (now - anchor).total_seconds() < int(interval_seconds):
        return False
    last_sent = await _get_deal_reminder_last_sent(deal["guildId"], deal["dealId"] or deal["id"], reminder_type)
    last_dt = _parse_deal_datetime(last_sent)
    cooldown = int(config.get("pingCooldownSeconds", 3600))
    return not last_dt or (now - last_dt).total_seconds() >= cooldown


async def expire_deal_for_timeout(deal, reason):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Deal SET status='Expired', isVouchEligible=0, updatedAt=? WHERE id=? AND status NOT IN ('Completed','Cancelled','Expired','Voided/Duplicate')",
            (now, int(deal["id"])),
        )
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, 'deal_auto_expired', NULL, ?, 'Expired', ?, ?)
            """,
            (deal["guildId"], deal["dealId"], deal["status"], reason, now),
        )
        await db.commit()
    await write_audit("deal_auto_expired", deal["dealId"] or deal["id"], reason, source="deal")
    await archive_deal_if_final(deal["id"], "Expired", None, reason=reason)
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "middleman_status", "dispute_board"})


async def cancel_pending_deal(deal_row_id, cancelled_by_id):
    now = _deal_now()
    reason = "Cancelled before form submission"
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            UPDATE Deal
            SET status='Cancelled', cancelledById=?, cancelledAt=?, cancelReason=?, updatedAt=?
            WHERE id=? AND status=?
            """,
            (str(cancelled_by_id), now, reason, now, int(deal_row_id), DEAL_STATUS_PENDING_FORM),
        )
        await db.commit()
        ok = cur.rowcount > 0
    if ok:
        await write_audit("deal_cancel_pending", deal_row_id, f"cancelledBy={cancelled_by_id}", source="deal")
        await archive_deal_if_final(deal_row_id, "Cancelled", cancelled_by_id, reason=reason)
        deal = await get_deal_by_id(deal_row_id)
        if deal:
            await refresh_staff_operation_panels(deal["guildId"], {"active_deals", "middleman_status"})
    return ok


async def finalize_deal_from_form(
    deal_row_id,
    *,
    submitted_by_id=None,
    payment_penjual,
    payment_pembeli,
    nominal_item,
    fee_type,
    mm_fee,
    buyer_pays,
    seller_receives,
    description,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute("SELECT guildId, status FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        if not row or row[1] != DEAL_STATUS_PENDING_FORM:
            await db.rollback()
            return None

        guild_id = row[0]
        async with db.execute("SELECT dealIdPrefix FROM DealConfig WHERE guildId=?", (guild_id,)) as cursor:
            cfg_row = await cursor.fetchone()
        prefix = (cfg_row[0] if cfg_row and cfg_row[0] else "MM").upper()

        async with db.execute(
            "SELECT dealId FROM Deal WHERE guildId=? AND dealId LIKE ?",
            (guild_id, f"{prefix}-%"),
        ) as cursor:
            rows = await cursor.fetchall()
        max_number = 0
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        for existing in rows:
            if existing[0]:
                match = pattern.match(existing[0])
                if match:
                    max_number = max(max_number, int(match.group(1)))

        next_number = max_number + 1
        now = _deal_now()
        while True:
            deal_id = f"{prefix}-{next_number:04d}"
            try:
                await db.execute(
                    """
                    UPDATE Deal
                    SET dealId=?, paymentPenjual=?, paymentPembeli=?, nominalItem=?, feeType=?,
                        mmFee=?, buyerPays=?, sellerReceives=?, description=?, status=?,
                        formSubmittedById=?, formSubmittedAt=?, updatedAt=?
                    WHERE id=? AND status=?
                    """,
                    (
                        deal_id, payment_penjual, payment_pembeli, int(nominal_item), fee_type,
                        int(mm_fee), int(buyer_pays), int(seller_receives), description,
                        DEAL_STATUS_WAITING_FUNDS, str(submitted_by_id) if submitted_by_id else None,
                        now, now, int(deal_row_id), DEAL_STATUS_PENDING_FORM,
                    ),
                )
                await db.commit()
                await add_deal_log(guild_id, deal_id, "deal_form_submit", submitted_by_id, DEAL_STATUS_PENDING_FORM, DEAL_STATUS_WAITING_FUNDS, None)
                await write_audit("deal_form_submit", deal_row_id, f"dealId={deal_id}", source="deal")
                await refresh_staff_operation_panels(guild_id, {"active_deals"})
                return await get_deal_by_id(deal_row_id)
            except sqlite3.IntegrityError:
                next_number += 1


async def update_deal_fields(deal_row_id, actor_id, fields, action, reason=None):
    fields = dict(fields or {})
    if not fields:
        return await get_deal_by_id(deal_row_id), None
    now = _deal_now()
    fields["updatedAt"] = now
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        set_clause = ", ".join(f"{key}=?" for key in fields.keys())
        values = [str(v) if key.endswith("Id") and v is not None else v for key, v in fields.items()]
        cursor = await db.execute(f"UPDATE Deal SET {set_clause} WHERE id=?", (*values, int(deal_row_id)))
        if cursor.rowcount == 0:
            await db.rollback()
            return deal, "not_found"
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (deal["guildId"], deal["dealId"], action, str(actor_id) if actor_id else None, reason, now),
        )
        await db.commit()
    await write_audit(action, deal_row_id, reason, source="deal")
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals"})
    return await get_deal_by_id(deal_row_id), None


async def update_deal_payout_atomic(
    deal_row_id,
    actor_id,
    platform,
    account,
    account_name,
    *,
    expected_status,
    action,
    reason=None,
    require_no_transfer_proof=True,
):
    now = _deal_now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        if deal.get("status") != expected_status:
            await db.rollback()
            return deal, "invalid_status"
        if require_no_transfer_proof and (
            str(deal.get("transferProofUrl") or "").strip()
            or str(deal.get("transferProofMessageId") or "").strip()
            or str(deal.get("transferProofSubmittedAt") or "").strip()
        ):
            await db.rollback()
            return deal, "transfer_proof_exists"

        proof_guard = ""
        params = [
            platform,
            account,
            account_name,
            str(actor_id) if actor_id is not None else None,
            now,
            now,
            int(deal_row_id),
            expected_status,
        ]
        if require_no_transfer_proof:
            proof_guard = """
            AND COALESCE(TRIM(CAST(transferProofUrl AS TEXT)), '') = ''
            AND COALESCE(TRIM(CAST(transferProofMessageId AS TEXT)), '') = ''
            AND COALESCE(TRIM(CAST(transferProofSubmittedAt AS TEXT)), '') = ''
            """
        cursor = await db.execute(
            f"""
            UPDATE Deal
            SET sellerPayoutPlatform=?,
                sellerPayoutAccount=?,
                sellerPayoutName=?,
                sellerPayoutSubmittedById=?,
                sellerPayoutSubmittedAt=?,
                updatedAt=?
            WHERE id=? AND status=?
            {proof_guard}
            """,
            tuple(params),
        )
        if cursor.rowcount == 0:
            await db.rollback()
            return deal, "invalid_status"
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (deal["guildId"], deal["dealId"], action, str(actor_id) if actor_id else None, reason, now),
        )
        await db.commit()
    await write_audit(action, deal_row_id, reason, source="deal")
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals"})
    return await get_deal_by_id(deal_row_id), None


async def update_deal_payment_proof_atomic(
    deal_row_id,
    actor_id,
    fields,
    action,
    reason=None,
    *,
    expected_invalidation_at=None,
):
    fields = dict(fields or {})
    if not fields:
        return await get_deal_by_id(deal_row_id), None
    now = _deal_now()
    fields["paymentProofInvalidatedAt"] = None
    fields["paymentProofInvalidatedById"] = None
    fields["paymentProofInvalidationReason"] = None
    fields["updatedAt"] = now
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(f"SELECT {DEAL_SELECT} FROM Deal WHERE id=?", (int(deal_row_id),)) as cursor:
            row = await cursor.fetchone()
        deal = _deal_row_to_dict(row)
        if not deal:
            await db.rollback()
            return None, "not_found"
        if deal.get("status") != DEAL_STATUS_WAITING_FUNDS:
            await db.rollback()
            return deal, "invalid_status"
        current_invalidation = str(deal.get("paymentProofInvalidatedAt") or "").strip() or None
        expected_invalidation = str(expected_invalidation_at or "").strip() or None
        if current_invalidation != expected_invalidation:
            await db.rollback()
            return deal, "stale_proof_context"
        set_clause = ", ".join(f"{key}=?" for key in fields.keys())
        values = [str(v) if key.endswith("Id") and v is not None else v for key, v in fields.items()]
        cursor = await db.execute(f"UPDATE Deal SET {set_clause} WHERE id=? AND status=?", (*values, int(deal_row_id), DEAL_STATUS_WAITING_FUNDS))
        if cursor.rowcount == 0:
            await db.rollback()
            return deal, "invalid_status"
        await db.execute(
            """
            INSERT INTO DealLog (guildId, dealId, action, actorId, oldValue, newValue, reason, createdAt)
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (deal["guildId"], deal["dealId"], action, str(actor_id) if actor_id else None, reason, now),
        )
        await db.commit()
    await write_audit(action, deal_row_id, reason, source="deal")
    await refresh_staff_operation_panels(deal["guildId"], {"active_deals"})
    return await get_deal_by_id(deal_row_id), None



async def patch_deal_channel_permissions(channel, target, reason=None):
    overwrite = channel.overwrites_for(target)
    for permission_name in DEAL_REQUIRED_PERMISSION_NAMES:
        setattr(overwrite, permission_name, True)
    await channel.set_permissions(target, overwrite=overwrite, reason=reason)


def parse_rupiah_amount(value):
    text = str(value or "").strip()
    text = re.sub(r"(?i)^rp\s*", "", text).strip()
    if re.search(r"[A-Za-z]", text):
        return None
    if not re.fullmatch(r"[0-9][0-9.,]*", text):
        return None
    digits = re.sub(r"[.,]", "", text)
    if not digits:
        return None
    amount = int(digits)
    return amount if amount > 0 else None


def format_rupiah(amount):
    return f"Rp{int(amount):,}".replace(",", ".")


def calculate_middleman_fee(nominal_item):
    nominal_item = int(nominal_item)
    if nominal_item <= 99_999:
        return 3_000
    if nominal_item <= 199_999:
        return 6_000
    if nominal_item <= 999_999:
        return 10_000
    if nominal_item <= 1_999_999:
        return 20_000
    if nominal_item <= 2_999_999:
        return 30_000
    return 40_000


# ── Reminder persistence ──────────────────────────────────────────────────────
async def add_reminder(user_id, channel_id, message, fire_at):
    try:
        now = datetime.utcnow().isoformat() + "Z"
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO Reminder (user_id, channel_id, message, fire_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(user_id), str(channel_id), message, fire_at.isoformat(), now))
            await db.commit()
            return cur.lastrowid
    except Exception as e:
        logging.error("add_reminder error exception=%s", type(e).__name__)
        return None


async def delete_reminder(rid):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM Reminder WHERE id=?", (rid,))
            await db.commit()
    except Exception as e:
        logging.error("delete_reminder error exception=%s", type(e).__name__)


async def _fire_reminder(rid, user_id, channel_id, message, delay):
    # Tunggu `delay` detik (boleh 0 untuk yang sudah lewat), kirim, lalu hapus baris.
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        channel = client.get_channel(int(channel_id))
        if channel:
            await channel.send(f"🔔 <@{user_id}> **REMINDER:** {message}")
    except Exception as e:
        logging.error("_fire_reminder error exception=%s", type(e).__name__)
    finally:
        await delete_reminder(rid)


def schedule_reminder(rid, user_id, channel_id, message, fire_at):
    delay = (fire_at - datetime.utcnow()).total_seconds()
    client.loop.create_task(_fire_reminder(rid, user_id, channel_id, message, max(0, delay)))


# ── Giveaway persistence ──────────────────────────────────────────────────────
async def add_giveaway(channel_id, message_id, prize, host_id, end_at):
    if ECONOMY_PHASE8_ENABLED:
        return None
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "INSERT INTO Giveaway (channel_id, message_id, prize, host_id, end_at, ended) VALUES (?, ?, ?, ?, ?, 0)",
                (str(channel_id), str(message_id), prize, str(host_id), end_at.isoformat()))
            await db.commit()
            return cur.lastrowid
    except Exception as e:
        logging.error("add_giveaway error exception=%s", type(e).__name__)
        return None


async def _end_giveaway(gid, channel_id, message_id, prize, delay):
    if ECONOMY_PHASE8_ENABLED:
        return
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        channel = client.get_channel(int(channel_id))
        if channel:
            try:
                msg = await channel.fetch_message(int(message_id))
                reaction = discord.utils.get(msg.reactions, emoji="🎉")
                entrants = [u async for u in reaction.users() if not u.bot] if reaction else []
            except Exception:
                entrants = []
            if not entrants:
                await channel.send(f"🎉 Giveaway **{prize}** selesai — tidak ada yang ikut.")
            else:
                winner = random.choice(entrants)
                await channel.send(f"🎊 Selamat {winner.mention}! Kamu memenangkan **{prize}**!")
    except Exception as e:
        logging.error("_end_giveaway error exception=%s", type(e).__name__)
    finally:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE Giveaway SET ended=1 WHERE id=?", (gid,))
                await db.commit()
        except Exception as e:
            logging.error("_end_giveaway cleanup error exception=%s", type(e).__name__)


def schedule_giveaway(gid, channel_id, message_id, prize, end_at):
    if ECONOMY_PHASE8_ENABLED:
        return None
    delay = (end_at - datetime.utcnow()).total_seconds()
    client.loop.create_task(_end_giveaway(gid, channel_id, message_id, prize, max(0, delay)))


async def resume_scheduled_jobs():
    # Dipanggil di on_ready: re-schedule reminder & giveaway yang tersimpan.
    # Reminder/giveaway yang sudah lewat fire_at langsung dieksekusi (delay 0).
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id, user_id, channel_id, message, fire_at FROM Reminder") as cur:
                reminders = await cur.fetchall()
            if ECONOMY_PHASE8_ENABLED:
                giveaways = []
            else:
                async with db.execute("SELECT id, channel_id, message_id, prize, end_at FROM Giveaway WHERE ended=0") as cur:
                    giveaways = await cur.fetchall()
        for rid, uid, cid, msg, fire_at in reminders:
            try:
                schedule_reminder(rid, uid, cid, msg, datetime.fromisoformat(fire_at))
            except Exception as e:
                logging.error("resume reminder id=%s error exception=%s", rid, type(e).__name__)
        for gid, cid, mid, prize, end_at in giveaways:
            try:
                schedule_giveaway(gid, cid, mid, prize, datetime.fromisoformat(end_at))
            except Exception as e:
                logging.error("resume giveaway id=%s error exception=%s", gid, type(e).__name__)
        if reminders or giveaways:
            logging.info(f"[RESUME] {len(reminders)} reminder & {len(giveaways)} giveaway dijadwalkan ulang")
    except Exception as e:
        logging.error("resume_scheduled_jobs error exception=%s", type(e).__name__)


async def finished_callback(sink, channel: discord.TextChannel, *args):
    recorded_users = [
        f"<@{user_id}>"
        for user_id, audio in sink.audio_data.items()
    ]
    if not recorded_users:
        await channel.send("Tidak ada suara yang terekam.")
        return

    await channel.send(f"Selesai merekam {', '.join(recorded_users)}. Memproses audio ke Gemini AI...")

    for user_id, audio in sink.audio_data.items():
        file_path = f"rekaman_{user_id}.wav"
        with open(file_path, "wb") as f:
            f.write(audio.file.read())

        try:
            uploaded_file = client.files.upload(file=file_path)
            prompt = "Ini adalah rekaman suara dari percakapan Discord. Tuliskan transkripnya, lalu berikan balasan singkat dalam bahasa Indonesia kasual berdasarkan ucapan tersebut."
            response = await asyncio.to_thread(gemini_client.models.generate_content, model='gemini-2.5-flash', contents=[uploaded_file, prompt])
            await channel.send(f"🎙️ **AI Merespons Suara <@{user_id}>:**\n{response.text}")
            uploaded_file.delete()
        except Exception as e:
            logging.error(f"Error processing audio: {str(e)}")
            await channel.send(f"Gagal memproses suara <@{user_id}> dengan AI.")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

async def get_gemini_response(query, user_id=None, user_name=None):
    try:
        final_query = query
        system_prefix = (
            "[SYSTEM INSTRUCTION: Kamu W2E Bot. Balas dalam bahasa Indonesia kasual — singkat, natural, dan to-the-point. "
            "Boleh lucu atau sarkastik kalau cocok konteksnya, tapi jangan dipaksain. "
            "Jangan formal, tapi jangan juga lebay. Bayangkan kamu ngobrol di Discord sama temen biasa. "
            "Maksimal 2-3 kalimat. Jangan pakai pembuka khas AI seperti 'Tentu!', 'Mari kita...', 'Sebagai AI...'. "
            "Langsung jawab inti pertanyaannya.]\n"
        )
        
        # Inject user's server nickname/display name so AI recognizes them
        if user_name:
            system_prefix += f"[SYSTEM: Kamu sedang berbicara dengan user bernama '{user_name}'. Panggil nama atau sapa mereka jika relevan.]\n"
            
        if user_id:
            personas = await load_json(PERSONAS_FILE)
            if str(user_id) in personas:
                system_prefix += f"[SYSTEM INSTRUCTION: Mulai sekarang kamu HARUS berbicara dan bertingkah sepenuhnya dengan persona/gaya ini: '{personas[str(user_id)]}'. Jangan pernah keluar dari karakter.]\n"
            
            final_query = f"{system_prefix}\nPesan User: {query}"
                
            if user_id not in chat_sessions:
                chat_sessions[user_id] = gemini_client.chats.create(model='gemini-2.5-flash')
            response = await asyncio.to_thread(chat_sessions[user_id].send_message, final_query)
        else:
            final_query = f"{system_prefix}\nPesan User: {query}"
            chat_session = gemini_client.chats.create(model='gemini-2.5-flash')
            response = await asyncio.to_thread(chat_session.send_message, final_query)
        return response.text or "Hmm, aku gak bisa jawab itu sekarang. Coba tanya yang lain."
    except Exception as e:
        logging.error(f"Error getting Gemini response: {str(e)}")
        return "Error getting response from Gemini."


async def send_msg_embed(target, *args, reply=False, **kwargs):
    content = kwargs.pop('content', None)
    if args:
        content = args[0]
        args = args[1:]
        
    func = target.reply if reply else target.send
        
    if 'embed' in kwargs or 'embeds' in kwargs or not content:
        if content:
            return await func(content, *args, **kwargs)
        return await func(*args, **kwargs)
        
    text = str(content)
    color = discord.Color.blurple()
    t_lower = text.lower()
    if "❌" in text or "kalah" in t_lower or "busted" in t_lower or "gagal" in t_lower or "hangus" in t_lower or "hilang" in t_lower:
        color = discord.Color.red()
    elif "✅" in text or "menang" in t_lower or "berhasil" in t_lower or "selamat" in t_lower or "claimed" in t_lower:
        color = discord.Color.green()
    elif "💰" in text or "koin" in t_lower or "market" in t_lower or "gacha" in t_lower or "box" in t_lower:
        color = discord.Color.gold()
        
    embed = discord.Embed(description=text, color=color)
    return await func(embed=embed, *args, **kwargs)


async def send_embed(interaction, text, color=None, title=None, ephemeral=False, view=None):
    if color is None:
        t_lower = text.lower()
        if "❌" in text or "kalah" in t_lower or "busted" in t_lower or "gagal" in t_lower or "hangus" in t_lower or "hilang" in t_lower:
            color = discord.Color.red()
        elif "✅" in text or "menang" in t_lower or "berhasil" in t_lower or "selamat" in t_lower or "claimed" in t_lower or "berkah" in t_lower:
            color = discord.Color.green()
        elif "💰" in text or "koin" in t_lower or "market" in t_lower or "gacha" in t_lower or "box" in t_lower or "jual" in t_lower or "beli" in t_lower:
            color = discord.Color.gold()
        elif "💍" in text or "keluarga" in t_lower or "menikah" in t_lower or "cerai" in t_lower or "adopsi" in t_lower:
            color = discord.Color.purple()
        else:
            color = discord.Color.blurple()

    embed = discord.Embed(description=text, color=color)
    if title:
        embed.title = title
    embed.set_footer(text="W2E Official Bot")
    try:
        if interaction.user:
            icon_url = interaction.user.display_avatar.url if interaction.user.display_avatar else None
            embed.set_author(name=interaction.user.display_name, icon_url=icon_url)
    except Exception:
        pass
        
    kwargs = {'embed': embed}
    if view: kwargs['view'] = view
    if ephemeral: kwargs['ephemeral'] = True

    try:
        if interaction.response.is_done():
            return await interaction.followup.send(**kwargs)
        else:
            return await interaction.response.send_message(**kwargs)
    except Exception as e:
        logging.error("Embed send error exception=%s", type(e).__name__)

# ============================================================================
# SLASH COMMANDS (APP COMMANDS)

@client.event
async def on_interaction(interaction: discord.Interaction):
    # Log tiap pemakaian slash command ke console (prefix di-log di on_message).
    try:
        if interaction.type == discord.InteractionType.application_command:
            data = interaction.data or {}
            name = data.get('name', '?')
            opts = data.get('options', []) or []
            # Jangan log nilai option: reason, note, proof, dan data konfigurasi
            # dapat berisi informasi sensitif. Nama option saja cukup untuk audit.
            arg_str = " ".join(str(o.get('name') or "?") for o in opts)
            user = interaction.user
            logging.info(
                "[CMD] (slash) actor_id=%s command=%s options=%s",
                getattr(user, "id", None),
                name,
                arg_str,
            )
    except Exception as e:
        logging.error("on_interaction log error exception=%s", type(e).__name__)

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    invocation_id = getattr(interaction, "_deal_invocation_id", None) or os.urandom(6).hex()
    logging.error(
        "App Command Error invocation_id=%s command=%s exception=%s",
        invocation_id,
        getattr(getattr(interaction, "command", None), "qualified_name", None),
        type(error).__name__,
    )
    # Jangan bocorkan detail exception ke user; cukup pesan generik.
    user_msg = '❌ Terjadi kesalahan saat menjalankan perintah. Coba lagi nanti ya.'
    responded = False
    try:
        if interaction.response.is_done() and hasattr(interaction, "edit_original_response"):
            await asyncio.wait_for(interaction.edit_original_response(content=user_msg), timeout=8)
        elif interaction.response.is_done():
            await asyncio.wait_for(interaction.followup.send(user_msg, ephemeral=True), timeout=8)
        else:
            await asyncio.wait_for(interaction.response.send_message(user_msg, ephemeral=True), timeout=8)
        responded = True
    except Exception as exc:
        logging.error(
            "App Command Error finalizer failed invocation_id=%s exception=%s",
            invocation_id,
            type(exc).__name__,
        )
    logging.info("App Command Error finalized invocation_id=%s responded=%s", invocation_id, responded)


# ============================================================================

@client.event
async def on_guild_join(guild):
    if guild.id != ALLOWED_SERVER_ID:
        logging.warning(f"Invited to unauthorized server {guild.name}. Leaving automatically.")
        await guild.leave()



from discord.ext import tasks
import time

@tasks.loop(minutes=5)
async def deal_reminder_loop():
    if not deal_phase_at_least(5):
        return
    now = datetime.utcnow()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT DISTINCT guildId FROM DealConfig") as cur:
                guild_rows = await cur.fetchall()
        for (guild_id,) in guild_rows:
            config = await get_deal_config(guild_id)
            if not config:
                continue
            intervals = config.get("reminderIntervals", DEAL_DEFAULT_REMINDER_INTERVALS)
            deals = await list_active_deals(guild_id)
            guild = client.get_guild(int(guild_id))
            if not guild:
                continue
            for deal in deals:
                channel = guild.get_channel(int(deal["ticketChannelId"]))
                if not channel:
                    continue
                reminder_type = None
                anchor_time = None
                interval_seconds = None
                message = None

                if deal["status"] == DEAL_STATUS_PENDING_FORM:
                    reminder_type = "form_not_submitted"
                    anchor_time = deal.get("createdAt")
                    interval_seconds = intervals.get("form_not_submitted_seconds", DEAL_DEFAULT_REMINDER_INTERVALS["form_not_submitted_seconds"])
                    message = f"⏰ Reminder deal `{deal.get('dealId') or deal['id']}`: form belum diisi. Middleman: <@{deal['middlemanId']}>"
                elif deal["status"] == DEAL_STATUS_WAITING_FUNDS:
                    reminder_type = "waiting_funds"
                    anchor_time = deal.get("updatedAt") or deal.get("createdAt")
                    interval_seconds = intervals.get("waiting_funds_seconds", DEAL_DEFAULT_REMINDER_INTERVALS["waiting_funds_seconds"])
                    message = f"⏰ Reminder deal `{deal['dealId']}`: masih menunggu Dana Masuk. Buyer: <@{deal['buyerId']}>, Middleman: <@{deal['middlemanId']}>"
                elif deal["status"] in (DEAL_STATUS_FUNDS_RECEIVED, DEAL_STATUS_ITEM_SENT):
                    reminder_type = "funds_no_confirm"
                    anchor_time = deal.get("fundsReceivedAt") or deal.get("updatedAt")
                    interval_seconds = intervals.get("funds_no_confirm_seconds", DEAL_DEFAULT_REMINDER_INTERVALS["funds_no_confirm_seconds"])
                    message = f"⏰ Reminder deal `{deal['dealId']}`: buyer belum confirm. Buyer: <@{deal['buyerId']}>, Middleman: <@{deal['middlemanId']}>"
                elif deal["status"] == DEAL_STATUS_DISPUTED:
                    reminder_type = "disputed"
                    anchor_time = deal.get("disputedAt") or deal.get("updatedAt")
                    interval_seconds = intervals.get("disputed_seconds", DEAL_DEFAULT_REMINDER_INTERVALS["disputed_seconds"])
                    role_ping = f"<@&{config['middlemanRoleId']}>" if config.get("middlemanRoleId") else "Staff"
                    message = f"⏰ Reminder dispute deal `{deal['dealId']}`: {role_ping} mohon cek dan resolve dispute."

                if config.get("reminderEnabled") and reminder_type and await should_send_deal_reminder(config, deal, reminder_type, anchor_time, interval_seconds):
                    await channel.send(message)
                    await _mark_deal_reminder_sent(guild_id, deal.get("dealId") or deal["id"], reminder_type)
                    await add_deal_log(guild_id, deal.get("dealId"), f"deal_reminder_{reminder_type}", None, None, deal["status"], message)

                if config.get("autoTimeoutEnabled"):
                    timeout_seconds = intervals.get("timeout_seconds", DEAL_DEFAULT_REMINDER_INTERVALS["timeout_seconds"])
                    updated = _parse_deal_datetime(deal.get("updatedAt") or deal.get("createdAt"))
                    if updated and (now - updated).total_seconds() >= timeout_seconds and deal["status"] not in (DEAL_STATUS_COMPLETED, "Cancelled", "Expired", "Voided/Duplicate"):
                        await expire_deal_for_timeout(deal, f"inactive >= {timeout_seconds}s")
                        try:
                            await channel.send(f"⌛ Deal `{deal.get('dealId') or deal['id']}` otomatis ditandai **Expired** karena inactive.")
                        except discord.HTTPException:
                            pass
    except Exception as e:
        logging.error("deal_reminder_loop error exception=%s", type(e).__name__)


@tasks.loop(minutes=15)
async def public_trust_panel_loop():
    try:
        await refresh_all_public_trust_panels()
    except Exception as e:
        logging.error("public_trust_panel_loop error exception=%s", type(e).__name__)


@tasks.loop(minutes=15)
async def staff_operation_panel_loop():
    try:
        await refresh_all_staff_operation_panels()
    except Exception as e:
        logging.error("staff_operation_panel_loop error exception=%s", type(e).__name__)


@tasks.loop(minutes=30)
async def clean_caches():
    now = datetime.now()
    # clean voice_join_times
    expired_voice = [k for k, v in voice_join_times.items() if (now - v).total_seconds() > 3600]
    for k in expired_voice: del voice_join_times[k]
    
    # rob_cooldowns (30 min)
    expired_rob = [k for k, v in rob_cooldowns.items() if (now - v).total_seconds() > 1800]
    for k in expired_rob: del rob_cooldowns[k]

    # boss_cooldowns (30 sec)
    expired_boss = [k for k, v in boss_cooldowns.items() if (now - v).total_seconds() > 30]
    for k in expired_boss: del boss_cooldowns[k]

    # work_cooldowns (1 hour)
    expired_work = [k for k, v in work_cooldowns.items() if (now - v).total_seconds() > 3600]
    for k in expired_work: del work_cooldowns[k]


# ── PREFIX COMMAND SYSTEM (FakeInteraction) ──────────────────────────────────
PREFIX_COMMAND_HANDLERS = {}
DEAL_PREFIX_RESERVED_TOP_LEVEL = {
    "rep",
    "trank",
    "trustlb",
    "vouch",
    "vouchleaderboard",
    "vouchremove",
    "vouchreport",
    "vouches",
    "rank",
    "removevouch",
    "reportvouch",
}


def register_prefix_command_handler(name, handler):
    PREFIX_COMMAND_HANDLERS[str(name).lower()] = handler


class FakeResponse:
    def __init__(self, message):
        self.message = message
        self._done = False
    def is_done(self):
        return self._done
    async def defer(self, ephemeral=False, thinking=False):
        self._done = True
    async def send_message(self, *args, **kwargs):
        kwargs.pop("ephemeral", None)
        kwargs.pop("wait", None)
        self._done = True
        return await self.message.reply(*args, **kwargs)
    async def send_modal(self, modal):
        raise RuntimeError("Modal Discord harus dibuka lewat button interaction, bukan prefix text.")

class FakeFollowup:
    def __init__(self, message):
        self.message = message
    async def send(self, *args, **kwargs):
        # Prefix message tidak punya ephemeral; ubah jadi reply biasa.
        kwargs.pop("ephemeral", None)
        kwargs.pop("wait", None)
        return await self.message.reply(*args, **kwargs)

class FakeInteraction:
    def __init__(self, message):
        self.message = message
        self.id = getattr(message, "id", None)
        self.user = message.author
        self.guild = message.guild
        self.channel = message.channel
        self.response = FakeResponse(message)
        self.followup = FakeFollowup(message)
    
    # Meniru fungsi-fungsi Interaction dasar yang sering dipakai
    @property
    def client(self):
        return client

    @property
    def guild_id(self):
        return getattr(self.guild, "id", None)

    @property
    def channel_id(self):
        return getattr(self.channel, "id", None)

    async def send(self, *args, **kwargs):
        kwargs.pop("ephemeral", None)
        kwargs.pop("wait", None)
        return await self.message.channel.send(*args, **kwargs)

        
@client.event
async def on_message(message):
    if message.author.bot:
        return



    # Auto-detect payment proof
    if message.attachments:
        try:
            from cogs.deal import handle_deal_message
            if await handle_deal_message(client, message):
                return
        except Exception as e:
            logging.error("Error in handle_deal_message exception=%s", type(e).__name__)
    # duplicate bot check removed
        # duplicate return removed

    # Auto-read prefix commands
    if message.content.startswith(BOT_PREFIX):
        parts = message.content[len(BOT_PREFIX):].strip().split()
        if not parts:
            return
            
        cmd_name = parts[0].lower()
        args_list = parts[1:]

        interaction = None
        prefix_handler = PREFIX_COMMAND_HANDLERS.get(cmd_name)
        if prefix_handler:
            logging.info(
                "[CMD] (prefix) actor_id=%s command=%s arg_count=%s",
                getattr(message.author, "id", None),
                cmd_name,
                len(args_list),
            )
            try:
                await prefix_handler(message, args_list)
            except Exception as e:
                logging.error("Error executing custom prefix command command=%s exception=%s", cmd_name, type(e).__name__)
                if getattr(message, "channel", None):
                    await message.channel.send("âŒ Gagal mengeksekusi perintah. Cek format argumennya ya.")
            return

        if cmd_name in DEAL_PREFIX_RESERVED_TOP_LEVEL:
            return

        # Check if the command exists in the CommandTree
        cmd = tree.get_command(cmd_name)
        if cmd:
            logging.info(
                "[CMD] (prefix) actor_id=%s command=%s arg_count=%s",
                getattr(message.author, "id", None),
                cmd_name,
                len(args_list),
            )
            interaction = FakeInteraction(message)
            
            # Sangat basic argument parsing (untuk command yg butuh target dll)
            # Karena argumen slash command memiliki typing, kita lewati validasi dan passing string mentah 
            # untuk diatasi oleh fallback code atau biarkan bot mencoba parsing sendiri.
            
            # We must use kwargs based on function signature if possible, or just pass args for text
            # However, app_commands callback signatures are strict.
            import inspect
            sig = inspect.signature(cmd.callback)
            
            kwargs = {}
            params = list(sig.parameters.values())[1:] # Skip interaction
            
            try:
                for i, param in enumerate(params):
                    if i < len(args_list):
                        val = args_list[i]
                        
                        # Parsing primitive types
                        if param.annotation == int:
                            val = int(val)
                        elif param.annotation == float:
                            val = float(val)
                        elif param.annotation == discord.Member:
                            # Parse <@id> or <@!id>
                            match = re.match(r'<@!?([0-9]+)>', val)
                            if match:
                                user_id = int(match.group(1))
                                val = message.guild.get_member(user_id)
                                if not val:
                                    val = await message.guild.fetch_member(user_id)
                            else:
                                # Not a mention, maybe an ID?
                                try:
                                    val = message.guild.get_member(int(val))
                                except ValueError:
                                    pass
                        elif param.annotation == discord.Role:
                            match = re.match(r'<@&([0-9]+)>', val)
                            if match:
                                role_id = int(match.group(1))
                                val = message.guild.get_role(role_id)
                        
                        kwargs[param.name] = val
                    else:
                        break
                        
                await cmd.callback(interaction, **kwargs)
            except Exception as e:
                logging.error("Error executing prefix command command=%s exception=%s", cmd_name, type(e).__name__)
                if interaction is not None and interaction.response.is_done():
                    await interaction.followup.send("Gagal mengeksekusi perintah. Silakan coba lagi.")
                    return
                await message.channel.send("❌ Gagal mengeksekusi perintah. Cek format argumennya ya.")
        return

    # ── Update Quest Progress ────────────────────────────────────────────────
    await update_quest_progress(str(message.author.id), 'send_msg', 1)

    # ── Chat XP reward (5 XP / 30s cooldown) ─────────────────────────────────
    uid_chat = str(message.author.id)
    now_chat = datetime.now()
    last_chat_xp = chat_xp_cooldowns.get(uid_chat)
    if last_chat_xp is None or (now_chat - last_chat_xp).total_seconds() >= ECON_CHAT_XP_COOLDOWN:
        chat_xp_cooldowns[uid_chat] = now_chat
        await add_xp(uid_chat, message.author.display_name, ECON_CHAT_XP)

    # ── AI auto-reply in the dedicated channel ───────────────────────────────
    if message.channel.id == AI_AUTO_REPLY_CHANNEL_ID:
        nick = getattr(message.author, 'nick', None) or message.author.display_name
        response = await get_gemini_response(message.content, message.author.id, nick)
        await send_long_message(message.channel, response)
        await write_to_memory(f'User: {message.content}\nBot: {response}')
        return

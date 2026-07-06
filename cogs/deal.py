import discord
from discord import app_commands
from datetime import datetime
from core import *


DEAL_V1_PLACEHOLDER_MESSAGE = "Fitur ini akan aktif di V2."
PAYMENT_PROOF_SESSIONS = set()
TRANSFER_PROOF_SESSIONS = set()
MANUAL_VOUCH_PROOF_SESSIONS = {}
SCAM_REPORT_PROOF_SESSIONS = {}
CRITICAL_ACTION_LOCKS = {}
REQUIRE_SELLER_PAYOUT_INFO = True
ALLOWED_PROOF_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
ALLOWED_PROOF_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "application/pdf"}


def _is_admin(interaction: discord.Interaction):
    return bool(interaction.user.guild_permissions.administrator)


def _now():
    return datetime.utcnow().isoformat() + "Z"


def _action_lock_key(action_type, guild_id, target_id):
    return (str(action_type), str(guild_id), str(target_id))


def _acquire_action_lock(action_type, guild_id, target_id, actor_id=None, ttl=20):
    key = _action_lock_key(action_type, guild_id, target_id)
    now = datetime.utcnow().timestamp()
    active = CRITICAL_ACTION_LOCKS.get(key)
    if active and active.get("expires", 0) > now:
        return None
    CRITICAL_ACTION_LOCKS[key] = {
        "expires": now + int(ttl or 20),
        "actorId": str(actor_id) if actor_id is not None else None,
    }
    return key


def _release_action_lock(key):
    if key:
        CRITICAL_ACTION_LOCKS.pop(key, None)


async def _send_lock_collision_audit(interaction, action_type, target_id):
    try:
        await send_deal_audit_log(
            interaction.guild,
            "Action Lock Collision",
            actor=interaction.user,
            note=f"{action_type}:{target_id}",
        )
    except Exception:
        pass


async def _send_abuse_guard_audit(guild, action, actor=None, target=None, note=None):
    try:
        await send_deal_audit_log(guild, action, actor=actor, target=target, note=note)
    except Exception:
        pass


def _is_terminal_deal_status(status):
    return status in ("Cancelled", "Voided/Duplicate", "Expired", DEAL_STATUS_COMPLETED, DEAL_STATUS_DISPUTED)


def _clear_deal_upload_sessions(deal_row_id):
    try:
        row_id = int(deal_row_id)
    except (TypeError, ValueError):
        return
    PAYMENT_PROOF_SESSIONS.discard(row_id)
    TRANSFER_PROOF_SESSIONS.discard(row_id)


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def format_discord_timestamp(value, style="R"):
    dt = _parse_dt(value) if not isinstance(value, datetime) else value
    if not dt:
        return "-"
    return f"<t:{int(dt.timestamp())}:{style}>"


def format_stars(rating):
    try:
        rounded = int(round(float(rating)))
    except (TypeError, ValueError):
        rounded = 0
    rounded = max(0, min(5, rounded))
    return "★" * rounded + "☆" * (5 - rounded)


def format_rating(rating):
    try:
        return f"{float(rating):.2f}/5"
    except (TypeError, ValueError):
        return "0.00/5"


def format_score(score):
    try:
        return str(int(round(float(score))))
    except (TypeError, ValueError):
        return "0"


def truncate_review(text, max_length=120):
    text = str(text or "").strip()
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 1)].rstrip() + "…"


def normalize_user_id(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("<@") and text.endswith(">"):
        text = text[2:-1].strip()
        if text.startswith("!"):
            text = text[1:].strip()
    if not text.isdigit():
        return None
    user_id = int(text)
    return user_id if user_id > 0 else None


async def format_leaderboard_user(bot, guild, user_id):
    normalized_id = normalize_user_id(user_id)
    if normalized_id is None:
        return "Unknown User"

    member = guild.get_member(normalized_id) if guild else None
    if not member and guild:
        try:
            member = await guild.fetch_member(normalized_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            member = None
    if member:
        return f"@{member.display_name}"

    user = bot.get_user(normalized_id) if bot else None
    if not user and bot:
        try:
            user = await bot.fetch_user(normalized_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            user = None
    if user:
        display_name = getattr(user, "global_name", None) or getattr(user, "name", None)
        return f"@{display_name}" if display_name is not None else "Unknown User"
    return "Unknown User"


def format_user(guild, bot, user_id):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return "Unknown User"
    member = guild.get_member(uid) if guild else None
    if member:
        return member.mention
    user = bot.get_user(uid) if bot else None
    if user:
        return getattr(user, "global_name", None) or getattr(user, "name", None) or "Unknown User"
    return "Unknown User"


async def format_user_display(bot, guild, user_id, *, fallback="Unknown User"):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return fallback
    member = guild.get_member(uid) if guild else None
    if not member and guild:
        try:
            member = await guild.fetch_member(uid)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            member = None
    if member:
        return member.mention
    user = bot.get_user(uid) if bot else None
    if not user and bot:
        try:
            user = await bot.fetch_user(uid)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            user = None
    return getattr(user, "global_name", None) or getattr(user, "name", None) or fallback


def _attachment_is_valid_proof(attachment):
    content_type = str(getattr(attachment, "content_type", "") or "").lower()
    if content_type in ALLOWED_PROOF_CONTENT_TYPES:
        return True
    filename = str(getattr(attachment, "filename", "") or "").lower()
    return any(filename.endswith(ext) for ext in ALLOWED_PROOF_EXTENSIONS)


async def handle_deal_message(client, message: discord.Message) -> bool:
    if message.author.bot:
        return False
    if not message.guild or not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        return False
    if not message.attachments:
        return False

    try:
        deal = await find_active_deal_for_channel(message.guild.id, message.channel.id)
        if not deal:
            return False
            
        if deal.get("status") != DEAL_STATUS_WAITING_FUNDS:
            return False
            
        if str(message.author.id) != str(deal.get("buyerId")):
            return False
            
        valid_attachment = None
        for att in message.attachments:
            if _attachment_is_valid_proof(att):
                valid_attachment = att
                break
                
        if not valid_attachment:
            await message.reply("Mohon kirim gambar (bukan file lain) untuk bukti pembayaran.")
            return True
            
        now = _now()
        fields = {
            "paymentProofUrl": valid_attachment.url,
            "paymentProofMessageId": str(message.id),
            "paymentProofChannelId": str(message.channel.id),
            "paymentProofSubmittedById": str(message.author.id),
            "paymentProofSubmittedAt": now,
        }
        
        updated, error = await update_deal_payment_proof_atomic(
            deal["id"],
            message.author.id,
            fields,
            "deal_payment_proof_submitted",
            message.jump_url,
        )
        
        if error:
            if error == "invalid_status":
                await message.reply("Gagal menyimpan bukti: Status deal sudah berubah.")
            else:
                await message.reply("Gagal menyimpan bukti. Coba lagi nanti.")
            return True
            
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass
            
        await message.channel.send(
            embed=await _payment_proof_embed(updated, message.guild, client, valid_attachment),
            view=PaymentProofActionView(updated["id"]),
        )
        await _update_summary_message(message.guild, updated)
        return True
    except Exception as e:
        logging.exception(f"Error in handle_deal_message: {e}")
        return False


def _manual_vouch_session_key(guild_id, channel_id, user_id):
    return (str(guild_id), str(channel_id), str(user_id))


def _source_label(vouch):
    if vouch.get("vouchType") == "manual":
        return "Admin Approved Manual Vouch" if vouch.get("approvalStatus") == "approved" else "Manual Vouch"
    return "Verified Deal Vouch"


async def _resolve_manual_vouch_target(guild, text):
    raw = str(text or "").strip()
    user_id = normalize_user_id(raw)
    if user_id:
        member = guild.get_member(user_id) if guild else None
        if not member and guild:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                member = None
        if member:
            return member, raw, True
        return None, raw, False
    lowered = raw.lower()
    if guild and lowered:
        for member in guild.members:
            names = {
                str(getattr(member, "name", "")).lower(),
                str(getattr(member, "display_name", "")).lower(),
                str(getattr(member, "global_name", "") or "").lower(),
            }
            if lowered in names:
                return member, raw, True
    return None, raw, False


def _manual_vouch_panel_embed():
    embed = discord.Embed(
        title="⭐ Submit Manual Vouch",
        description=(
            "Gunakan tombol di bawah untuk mengirim vouch manual kepada member lain.\n\n"
            "Manual vouch wajib memiliki proof dan akan direview oleh staff terlebih dahulu.\n"
            "Vouch yang belum di-approve tidak akan masuk reputasi."
        ),
        color=0xFFD700,
    )
    embed.set_footer(text="W2E Manual Vouch")
    return embed


def _proof_jump_url(deal, prefix):
    url = deal.get(f"{prefix}ProofUrl")
    message_id = deal.get(f"{prefix}ProofMessageId")
    channel_id = deal.get(f"{prefix}ProofChannelId") or deal.get("ticketChannelId")
    guild_id = deal.get("guildId")
    if guild_id and channel_id and message_id:
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    return url or "-"


def _proof_link(deal, prefix):
    url = _proof_jump_url(deal, prefix)
    return f"[Open Proof]({url})" if str(url).startswith("http") else "-"


async def _warning_embed(deal, guild=None, bot=None):
    embed = discord.Embed(
        title="⚠️ PERINGATAN!!",
        description=(
            "Sebelum memulai transaksi, pastikan kalian sudah yakin dengan pilihan kalian dan lawan transaksi kalian.\n\n"
            "Harap baca ketentuan fee, delay, dan aturan middleman dengan menekan tombol “Ketentuan” sebelum melanjutkan transaksi.\n\n"
            "Jika sudah paham, tekan tombol “Form” untuk mengisi data transaksi.\n\n"
            "Jangan kirim payment, password, email recovery, OTP, atau data sensitif sebelum middleman memberi arahan."
        ),
        color=0xFEE75C,
    )
    embed.add_field(name="Buyer", value=await format_user_display(bot, guild, deal.get("buyerId")), inline=True)
    embed.add_field(name="Seller", value=await format_user_display(bot, guild, deal.get("sellerId")), inline=True)
    embed.add_field(name="Middleman", value=await format_user_display(bot, guild, deal.get("middlemanId")), inline=True)
    embed.add_field(name="Status", value=deal.get("status") or DEAL_STATUS_PENDING_FORM, inline=False)
    embed.set_footer(text="W2E Middleman")
    return embed


def _terms_embed():
    embed = discord.Embed(
        title="ℹ️ INFO LENGKAP, KETENTUAN, FEE DLL!",
        description=(
            "⏱ KETENTUAN DELAY\n"
            "✦ 1–3 hari → 3k\n"
            "✦ 3–7 hari → 5k\n"
            "✦ 7–14 hari → 7k\n"
            "✦ Seterusnya → 10k\n\n"
            "KETENTUAN TUKAR TAMBAH / BARTER\n"
            "✦ Jika middleman mengamankan akun → 10k / akun\n\n"
            "⚠️ KETENTUAN TRANSAKSI & LIST FEE\n"
            "✦ Transaksi Rp0 – Rp99K → Fee: Rp3K\n"
            "✦ Transaksi Rp100K – Rp199K → Fee: Rp6K\n"
            "✦ Transaksi Rp200K – Rp999K → Fee: Rp10K\n"
            "✦ Transaksi Rp1.000K – Rp1.999K → Fee: Rp20K\n"
            "✦ Transaksi Rp2.000K – Rp2.999K → Fee: Rp30K\n"
            "✦ Transaksi > Rp3.000K → Fee: Rp40K\n\n"
            "QRIS ALL PAYMENT\n"
            "✦ Max 500K / 1x Scan\n\n"
            "✦ Cancel = Fee hangus / cari seller baru"
        ),
        color=0x5865F2,
    )
    embed.set_footer(text="W2E Middleman")
    return embed


async def _summary_embed(deal, guild=None, bot=None):
    embed = discord.Embed(title="📋 Middleman Deal Created", color=0x57F287)
    if deal.get("status") == DEAL_STATUS_WAITING_FUNDS:
        if deal.get("paymentProofMessageId"):
            embed.description = "📎 **Bukti pembayaran telah diterima. Menunggu konfirmasi Dana Masuk oleh Middleman.**"
        else:
            embed.description = "📣 **Buyer, silakan kirim gambar/PDF bukti pembayaran langsung di channel ini.**"

    fields = [
        ("Deal ID", deal["dealId"]),
        ("Buyer", await format_user_display(bot, guild, deal.get("buyerId"))),
        ("Seller", await format_user_display(bot, guild, deal.get("sellerId"))),
        ("Middleman", await format_user_display(bot, guild, deal.get("middlemanId"))),
        ("Payment Penjual", deal["paymentPenjual"]),
        ("Payment Pembeli", deal["paymentPembeli"]),
        ("Nominal Item", format_rupiah(deal["nominalItem"])),
        ("Fee Type", deal["feeType"]),
        ("MM Fee", format_rupiah(deal["mmFee"])),
        ("Buyer Pays", format_rupiah(deal["buyerPays"])),
        ("Seller Receives", format_rupiah(deal["sellerReceives"])),
        ("Deskripsi Item", deal["description"] or "-"),
        ("Status", deal["status"]),
    ]
    if deal.get("formSubmittedById"):
        fields.append(("Form Submitted By", await format_user_display(bot, guild, deal.get("formSubmittedById"))))
    for name, value in fields:
        embed.add_field(name=name, value=str(value), inline=False)
    embed.set_footer(text="W2E Middleman")
    return embed


def _proof_value(url_value, notes_value):
    if url_value and notes_value:
        return f"{url_value}\n{notes_value}"
    return url_value or notes_value or "-"


def _split_proof(value, optional_notes=None):
    text = str(value or "").strip()
    notes = str(optional_notes or "").strip()
    if text.lower().startswith(("http://", "https://")):
        return text, notes or None
    combined = "\n".join(part for part in (text, notes) if part)
    return None, combined or None


def _transition_embed(title, description, color=0x57F287):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="W2E Middleman")
    return embed


def _disable_view(view):
    for child in view.children:
        child.disabled = True
    return view


async def _disable_source_message(interaction: discord.Interaction, view):
    source_message = getattr(interaction, "message", None)
    if not source_message:
        return
    try:
        await source_message.edit(view=_disable_view(view))
    except discord.HTTPException:
        pass


def _clean_payout_value(value):
    return str(value or "").strip()


def _has_seller_payout_info(deal):
    return all(
        _clean_payout_value(deal.get(field))
        for field in ("sellerPayoutPlatform", "sellerPayoutAccount", "sellerPayoutName")
    )


async def _buyer_confirm_embed(deal, guild=None, bot=None):
    embed = discord.Embed(
        title="✅ Buyer Confirm",
        description=(
            "Buyer telah mengonfirmasi bahwa item/data sudah diterima sesuai deal.\n\n"
            "Seller sekarang diminta untuk mengirim data pencairan dana.\n"
            "Middleman dapat melanjutkan transfer setelah data pencairan seller diterima."
        ),
        color=0x57F287,
    )
    embed.add_field(name="Deal ID", value=deal.get("dealId") or "-", inline=False)
    embed.add_field(name="Buyer", value=await format_user_display(bot, guild, deal.get("buyerId")), inline=True)
    embed.add_field(name="Seller", value=await format_user_display(bot, guild, deal.get("sellerId")), inline=True)
    embed.add_field(name="Middleman", value=await format_user_display(bot, guild, deal.get("middlemanId")), inline=True)
    embed.add_field(name="Status", value="Menunggu Data Pencairan Seller", inline=False)
    embed.set_footer(text="W2E Middleman")
    return embed


def _seller_payout_instruction_embed():
    embed = discord.Embed(
        title="💸 DATA PENCAIRAN DANA (MM → SELLER)",
        description=(
            "Silakan seller mengirim data pencairan dana untuk proses transfer dari Middleman ke seller.\n\n"
            "**Template Pengisian:**\n\n"
            "✦ PLATFORM               : (Dana / OVO / Gopay / BCA / dll)\n"
            "✦ NO REK / NO HP / EMAIL  : (E-WALLET / M-BANKING)\n"
            "✦ ATAS NAMA              : (Nama pemilik rekening)"
        ),
        color=0x5865F2,
    )
    embed.set_footer(text="Pastikan data benar. Salah input = risiko seller.")
    return embed


async def _seller_payout_received_embed(deal, guild=None, bot=None):
    embed = discord.Embed(
        title="🏦 Data Pencairan Seller Diterima",
        description="Data pencairan seller sudah dikirim untuk proses transfer dana.",
        color=0x57F287,
    )
    embed.add_field(name="Deal ID", value=deal.get("dealId") or "-", inline=False)
    embed.add_field(name="Seller", value=await format_user_display(bot, guild, deal.get("sellerId")), inline=True)
    embed.add_field(name="Platform", value=_clean_payout_value(deal.get("sellerPayoutPlatform")) or "-", inline=False)
    embed.add_field(name="No Rek / No HP / Email", value=_clean_payout_value(deal.get("sellerPayoutAccount")) or "-", inline=False)
    embed.add_field(name="Atas Nama", value=_clean_payout_value(deal.get("sellerPayoutName")) or "-", inline=False)
    embed.add_field(name="Submitted By", value=await format_user_display(bot, guild, deal.get("sellerPayoutSubmittedById")), inline=True)
    embed.add_field(name="Status", value="Menunggu transfer dari Middleman", inline=False)
    embed.set_footer(text="W2E Middleman")
    return embed


async def _final_summary_embed(deal, guild=None, bot=None):
    embed = discord.Embed(title="✅ Deal Completed", color=0x57F287)
    fields = [
        ("Deal ID", deal["dealId"]),
        ("Buyer", await format_user_display(bot, guild, deal.get("buyerId"))),
        ("Seller", await format_user_display(bot, guild, deal.get("sellerId"))),
        ("Middleman", await format_user_display(bot, guild, deal.get("middlemanId"))),
        ("Item / Deskripsi", deal["description"] or "-"),
        ("Nominal Item", format_rupiah(deal["nominalItem"])),
        ("MM Fee", format_rupiah(deal["mmFee"])),
        ("Buyer Paid", format_rupiah(deal["buyerPays"])),
        ("Seller Received", format_rupiah(deal["sellerReceives"])),
        ("Fee Type", deal["feeType"]),
        ("Payment Penjual", deal["paymentPenjual"]),
        ("Payment Pembeli", deal["paymentPembeli"]),
        ("Seller Payout Platform", _clean_payout_value(deal.get("sellerPayoutPlatform")) or "-"),
        ("Seller Payout Account", _clean_payout_value(deal.get("sellerPayoutAccount")) or "-"),
        ("Seller Payout Name", _clean_payout_value(deal.get("sellerPayoutName")) or "-"),
        ("Completed At", format_discord_timestamp(deal.get("completedAt"), "f")),
        ("Payment Proof", _proof_link(deal, "payment")),
        ("Transfer Proof", _proof_link(deal, "transfer")),
        ("Status", "Completed"),
    ]
    for name, value in fields:
        embed.add_field(name=name, value=str(value), inline=False)
    embed.set_footer(text="W2E Middleman")
    return embed


def _target_id_for_role(deal, role):
    return get_deal_role_user_id(deal, role)


async def _vouch_success_embed(vouch, guild=None, bot=None):
    source = _source_label(vouch)
    embed = discord.Embed(
        title=f"⭐ {source} Submitted",
        description="A new approved vouch has been added to marketplace reputation.",
        color=0xFFD700,
    )
    embed.add_field(name="Source", value=source, inline=False)
    embed.add_field(name="Deal", value=f"`{vouch['dealId']}`" if vouch.get("dealId") else "-", inline=True)
    embed.add_field(name="From", value=await format_user_display(bot, guild, vouch.get("reviewerId")), inline=True)
    embed.add_field(name="To", value=await format_user_display(bot, guild, vouch.get("targetId")), inline=True)
    embed.add_field(name="Rating", value=f"{format_stars(vouch['rating'])} {int(vouch['rating'])}/5", inline=True)
    embed.add_field(name="Role", value=f"{vouch['reviewerRole']} → {vouch['targetRole']}", inline=True)
    embed.add_field(name="Status", value=f"✅ {source}", inline=True)
    embed.add_field(name="Review", value=truncate_review(vouch["review"], 500), inline=False)
    embed.add_field(name="Submitted", value=format_discord_timestamp(vouch.get("createdAt")), inline=True)
    embed.set_footer(text=f"Vouch ID #{vouch['id']}")
    return embed


async def _reputation_profile_embed(user: discord.Member, rep, latest_vouches, bot=None):
    guild = getattr(user, "guild", None)
    embed = discord.Embed(
        title=f"🛡️ Trust Profile — {user.display_name}",
        description="Verified marketplace reputation from completed middleman deals.",
        color=0xFFD700,
    )
    embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
    embed.add_field(
        name="Main Stats",
        value=(
            f"> ⭐ **Average Rating:** {format_rating(rep['averageRating'])}\n"
            f"> ✅ **Verified Vouches:** {rep['verifiedVouches']}\n"
            f"> 🛡️ **Verified Deal Vouches:** {rep.get('verifiedDealVouches', 0)}\n"
            f"> 📝 **Admin Approved Vouches:** {rep.get('manualApprovedVouches', 0)}\n"
            f"> 📈 **Trust Score:** {format_score(rep['trustScore'])}\n"
            f"> 🏷️ **Trust Level:** {rep['trustLevel']}"
        ),
        inline=False,
    )
    safety = []
    if rep.get("reports"):
        safety.append(f"> ⚠️ **Reports:** {rep['reports']}")
    if rep.get("removedVouches"):
        safety.append(f"> 🧾 **Removed Vouches:** {rep['removedVouches']}")
    if safety:
        embed.add_field(name="Safety", value="\n".join(safety), inline=False)
    embed.add_field(
        name="Breakdown",
        value=(
            f"> 🛒 Buyer Vouches: {rep['buyerVouches']}\n"
            f"> 🏪 Seller Vouches: {rep['sellerVouches']}\n"
            f"> 🛡️ Middleman Vouches: {rep['middlemanVouches']}"
        ),
        inline=False,
    )
    if latest_vouches:
        lines = []
        for v in latest_vouches[:5]:
            reviewer = await format_user_display(bot, guild, v.get("reviewerId"))
            lines.append(f"`#{v['id']}` {format_stars(v['rating'])} {_source_label(v)} from {reviewer} — “{truncate_review(v['review'], 80)}”")
        embed.add_field(name="Latest Reviews", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Latest Reviews", value="Belum ada review.", inline=False)
    embed.set_footer(text=f"Use /vouches user:{user.display_name} or w!deal vouches @{user.display_name} to view full history")
    return embed


def _next_rank_requirement(rep):
    next_rank, required, rating = _next_rank_target(rep)
    if not next_rank:
        return "Kamu sudah di rank tertinggi."
    return f"{required} verified vouches + {rating:.2f} average rating"


def _next_rank_target(rep):
    verified = int(rep.get("verifiedVouches", 0) or 0)
    ladder = [
        ("Verified User", 1, 0),
        ("Active Trader", 10, 4.5),
        ("Reliable Seller", 30, 4.6),
        ("Established Seller", 60, 4.7),
        ("Trusted Seller", 100, 4.8),
        ("Elite Trader", 250, 4.85),
        ("Legendary Trader", 500, 4.9),
    ]
    for name, required, rating in ladder:
        if verified < required or float(rep.get("averageRating", 0) or 0) < rating:
            return name, required, rating
    return None, None, None


def _progress_bar(current, target, width=10):
    if not target:
        return "█" * width
    filled = max(0, min(width, int((current / target) * width)))
    return "█" * filled + "░" * (width - filled)


def _rank_embed(user: discord.Member, rep):
    next_rank, required, rating = _next_rank_target(rep)
    verified = int(rep.get("verifiedVouches", 0) or 0)
    embed = discord.Embed(title=f"📈 Trust Rank — {user.display_name}", color=0x5865F2)
    embed.add_field(name="Current Rank", value=rep["trustLevel"], inline=False)
    embed.add_field(name="Verified Vouches", value=str(verified), inline=True)
    embed.add_field(name="Average Rating", value=format_rating(rep["averageRating"]), inline=True)
    embed.add_field(name="Trust Score", value=format_score(rep["trustScore"]), inline=True)
    if next_rank:
        embed.add_field(name="Next Rank", value=next_rank, inline=True)
        embed.add_field(name="Requirement", value=f"{required} verified vouches + {rating:g} average rating", inline=False)
        embed.add_field(name="Progress", value=f"`{_progress_bar(min(verified, required), required)}` {verified}/{required}", inline=False)
    else:
        embed.add_field(name="Next Rank", value="Rank tertinggi", inline=True)
    embed.set_footer(text="Trusted Seller requires 100+ verified vouches and strong rating.")
    return embed


async def _leaderboard_embed(guild, bot, reps):
    embed = discord.Embed(
        title="🏆 Trusted Leaderboard",
        description="Top trusted users based on verified middleman deal reputation.",
        color=0xFFD700,
    )
    if not reps:
        embed.description = "No verified vouches yet.\nComplete middleman deals and submit vouches to appear here."
        return embed
    medals = ["🥇", "🥈", "🥉"]
    for idx, rep in enumerate(reps, start=1):
        prefix = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
        lines = [
            f"> 🏷️ **Trust Level:** {rep['trustLevel']}" if idx <= 3 else f"> 🏷️ Trust Level: {rep['trustLevel']}",
            f"> ⭐ **Rating:** {format_rating(rep['averageRating'])}" if idx <= 3 else f"> ⭐ Rating: {format_rating(rep['averageRating'])}",
            f"> ✅ **Verified Vouches:** {rep['verifiedVouches']}" if idx <= 3 else f"> ✅ Verified Vouches: {rep['verifiedVouches']}",
            f"> 📝 **Admin Approved:** {rep.get('manualApprovedVouches', 0)}" if idx <= 3 else f"> 📝 Admin Approved: {rep.get('manualApprovedVouches', 0)}",
            f"> 📈 **Trust Score:** {format_score(rep['trustScore'])}" if idx <= 3 else f"> 📈 Trust Score: {format_score(rep['trustScore'])}",
        ]
        if rep.get("reports"):
            lines.append(f"> ⚠️ Reports: {rep['reports']}")
        if rep.get("removedVouches"):
            lines.append(f"> 🧾 Removed Vouches: {rep['removedVouches']}")
        user_display = await format_leaderboard_user(bot, guild, rep.get("userId"))
        embed.add_field(name=f"{prefix} **{user_display}**", value="\n".join(lines), inline=False)
    embed.set_footer(text=f"Updated {format_discord_timestamp(datetime.utcnow())} • Page 1/1")
    return embed


async def _vouch_leaderboard_embed(guild, bot, reps):
    embed = discord.Embed(
        title="🏆 Trusted Vouch Leaderboard",
        description="Top trusted users based on verified middleman deal reputation.",
        color=0xFFD700,
    )
    if not reps:
        embed.description = "No verified vouches yet.\nComplete middleman deals and submit vouches to appear here."
        return embed
    medals = ["🥇", "🥈", "🥉"]
    for idx, rep in enumerate(reps, start=1):
        prefix = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
        user_display = await format_leaderboard_user(bot, guild, rep.get("userId"))
        if idx <= 3:
            value = (
                f"> 🏷️ **Trust Level:** {rep['trustLevel']}\n"
                f"> ⭐ **Rating:** {format_rating(rep['averageRating'])}\n"
                f"> ✅ **Verified Vouches:** {rep['verifiedVouches']}\n"
                f"> 📝 **Admin Approved:** {rep.get('manualApprovedVouches', 0)}\n"
                f"> 📈 **Trust Score:** {format_score(rep['trustScore'])}"
            )
        else:
            value = (
                f"> 🏷️ Trust Level: {rep['trustLevel']}\n"
                f"> ⭐ Rating: {format_rating(rep['averageRating'])}\n"
                f"> ✅ Verified Vouches: {rep['verifiedVouches']}\n"
                f"> 📝 Admin Approved: {rep.get('manualApprovedVouches', 0)}\n"
                f"> 📈 Trust Score: {format_score(rep['trustScore'])}"
            )
        embed.add_field(name=f"{prefix} **{user_display}**", value=value, inline=False)
    return embed


def _legacy_next_rank_requirement_unused(rep):
    level = rep["trustLevel"]
    if level == "New User":
        return "Butuh 2 vouch Buyer atau Seller verified."
    if level == "Verified Buyer":
        return "Butuh minimal 2 seller vouch untuk Verified Seller."
    if level == "Verified Seller":
        return "Butuh 8 seller vouch dan rating rata-rata 4.5 untuk Trusted Seller."
    if level == "Trusted Seller":
        return "Butuh 10 middleman vouch dan rating rata-rata 4.7 untuk Trusted Middleman, atau 25 verified vouch rating 4.8 untuk Elite Trader."
    if level == "Trusted Middleman":
        return "Butuh 25 verified vouch dan rating rata-rata 4.8 untuk Elite Trader."
    if level == "Elite Trader":
        return "Kamu sudah di rank tertinggi."
    if level == "Under Review":
        return "Kurangi report/removed vouch dengan review staff."
    if level == "Blacklisted":
        return "Blacklist hanya bisa dipulihkan oleh staff."
    return "-"


def _legacy_rank_embed_unused(user: discord.Member, rep):
    embed = discord.Embed(title=f"Reputation Rank: {user.display_name}", color=0x5865F2)
    embed.add_field(name="Current Rank", value=rep["trustLevel"], inline=False)
    embed.add_field(name="Total Vouches", value=str(rep["totalVouches"]), inline=True)
    embed.add_field(name="Verified Vouches", value=str(rep["verifiedVouches"]), inline=True)
    embed.add_field(name="Average Rating", value=f"{rep['averageRating']:.2f} / 5", inline=True)
    embed.add_field(name="Trust Score", value=f"{rep['trustScore']:.2f}", inline=True)
    embed.add_field(name="Next Rank Requirement", value=_next_rank_requirement(rep), inline=False)
    return embed


class VouchesListView(discord.ui.View):
    def __init__(self, user: discord.Member, vouches, page=0):
        super().__init__(timeout=180)
        self.user = user
        self.vouches = vouches
        self.page = page
        self.page_size = 5
        self._sync_buttons()

    def _sync_buttons(self):
        max_page = max(0, (len(self.vouches) - 1) // self.page_size)
        for child in self.children:
            if getattr(child, "custom_id", None) == "vouches_prev":
                child.disabled = self.page <= 0
            elif getattr(child, "custom_id", None) == "vouches_next":
                child.disabled = self.page >= max_page

    async def embed(self, bot=None):
        total = len(self.vouches)
        avg = sum(int(v.get("rating") or 0) for v in self.vouches) / total if total else 0
        embed = discord.Embed(
            title=f"⭐ Vouches for {self.user.display_name}",
            description="Verified reputation history based on completed middleman deals.",
            color=0xFFD700,
        )
        start = self.page * self.page_size
        items = self.vouches[start:start + self.page_size]
        if not items:
            embed.description = "No vouches yet.\nThis user has not received any verified deal vouches."
        for v in items:
            label = f"✅ {_source_label(v)}" if v.get("approvalStatus") in ("verified", "approved") else "📝 Manual Vouch"
            reviewer = await format_user_display(bot, getattr(self.user, "guild", None), v.get("reviewerId"))
            target = await format_user_display(bot, getattr(self.user, "guild", None), v.get("targetId"))
            approved_by = await format_user_display(bot, getattr(self.user, "guild", None), v.get("approvedById")) if v.get("approvedById") else None
            proof_text = "Available" if int(v.get("proofCount") or 0) else "-"
            deal_text = f"`{v['dealId']}`" if v.get("dealId") else "-"
            role_text = f"{v['reviewerRole']} → {v['targetRole']}" if v.get("vouchType") != "manual" else "Manual"
            value = (
                f"> **From:** {reviewer}\n"
                f"> **To:** {target}\n"
                f"> **Deal:** {deal_text}\n"
                f"> **Role:** {role_text}\n"
                f"> **Review:** {truncate_review(v['review'], 180)}\n"
                f"> **Proof:** {proof_text}\n"
                f"> **Date:** {format_discord_timestamp(v.get('createdAt'))}"
            )
            if approved_by:
                value += f"\n> **Approved By:** {approved_by}"
            embed.add_field(
                name=f"`#{v['id']}` {format_stars(v['rating'])} **{label}**",
                value=value,
                inline=False,
            )
        max_page = max(0, (len(self.vouches) - 1) // self.page_size)
        embed.set_footer(text=f"Page {self.page + 1}/{max_page + 1} • Total {total} vouches • Average {avg:.1f}★")
        return embed

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="vouches_prev")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=await self.embed(interaction.client), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="vouches_next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, (len(self.vouches) - 1) // self.page_size)
        self.page = min(max_page, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=await self.embed(interaction.client), view=self)


async def _manual_vouch_target_display(bot, guild, vouch):
    if vouch.get("targetId"):
        return await format_user_display(bot, guild, vouch.get("targetId"))
    return f"unresolved: {vouch.get('targetRaw') or '-'}"


async def _manual_vouch_review_embed(vouch, guild=None, bot=None, *, status_text=None, evidence=None):
    embed = discord.Embed(title="📝 Pending Manual Vouch", color=0xFEE75C)
    if vouch.get("approvalStatus") == "approved":
        embed.title = "✅ Manual Vouch Approved"
        embed.color = 0x57F287
    elif vouch.get("approvalStatus") == "rejected":
        embed.title = "❌ Manual Vouch Rejected"
        embed.color = 0xED4245
    embed.add_field(name="Vouch ID", value=str(vouch.get("id")), inline=True)
    embed.add_field(name="From", value=await format_user_display(bot, guild, vouch.get("reviewerId")), inline=True)
    embed.add_field(name="To", value=await _manual_vouch_target_display(bot, guild, vouch), inline=True)
    embed.add_field(name="Rating", value=f"{format_stars(vouch.get('rating'))} {int(vouch.get('rating') or 0)}/5", inline=True)
    embed.add_field(name="Review", value=truncate_review(vouch.get("review"), 500), inline=False)
    embed.add_field(name="Context", value=truncate_review(vouch.get("context") or "-", 200), inline=False)
    if vouch.get("staffNotes"):
        embed.add_field(name="Notes", value=truncate_review(vouch.get("staffNotes"), 200), inline=False)
    embed.add_field(name="Proof Count", value=str(vouch.get("proofCount") or 0), inline=True)
    if evidence:
        embed.add_field(name="Evidence", value=truncate_review(evidence, 900), inline=False)
    status_value = status_text
    if not status_value:
        status_map = {
            "pending": "Pending Staff Review",
            "approved": "Approved",
            "rejected": "Rejected",
        }
        status_value = status_map.get(vouch.get("approvalStatus"), vouch.get("approvalStatus") or "-")
    embed.add_field(name="Status", value=status_value, inline=False)
    if vouch.get("rejectionReason"):
        embed.add_field(name="Reject Reason", value=truncate_review(vouch.get("rejectionReason"), 250), inline=False)
    embed.set_footer(text="Manual vouch requires staff approval.")
    return embed


async def _post_manual_vouch_evidence(review_message, vouch):
    try:
        proofs = json.loads(vouch.get("proofData") or "[]")
    except Exception:
        proofs = []
    if not proofs:
        return None
    lines = []
    for idx, proof in enumerate(proofs, start=1):
        jump_url = proof.get("messageJumpUrl") or proof.get("attachmentUrl")
        filename = proof.get("filename") or f"proof-{idx}"
        if jump_url:
            lines.append(f"{idx}. [{filename}]({jump_url})")
    if not lines:
        return None
    try:
        thread = await review_message.create_thread(
            name=f"manual-vouch-{vouch.get('id')}-proof",
            auto_archive_duration=1440,
        )
        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > 1800:
                chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}".strip()
        if current:
            chunks.append(current)
        for chunk in chunks:
            await thread.send(chunk)
        return getattr(thread, "mention", None) or f"Thread: {thread.name}"
    except discord.HTTPException:
        return "\n".join(lines[:8])


class ManualVouchReviewView(discord.ui.View):
    def __init__(self, vouch_id: int):
        super().__init__(timeout=86400)
        self.vouch_id = int(vouch_id)

    async def _require_reviewer(self, interaction):
        if await _can_configure_audit_log(interaction):
            return True
        await interaction.response.send_message("Kamu tidak punya permission untuk review vouch.", ephemeral=True)
        return False

    async def _update_review_message(self, interaction, vouch, status_text):
        evidence = None
        message = getattr(interaction, "message", None)
        if message:
            for embed in getattr(message, "embeds", []) or []:
                for field in getattr(embed, "fields", []) or []:
                    if field.name == "Evidence":
                        evidence = field.value
                        break
        try:
            await interaction.message.edit(
                embed=await _manual_vouch_review_embed(vouch, interaction.guild, interaction.client, status_text=status_text, evidence=evidence),
                view=None,
            )
        except discord.HTTPException:
            pass

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_reviewer(interaction):
            return
        lock_key = _acquire_action_lock("manual_vouch_review", interaction.guild.id, self.vouch_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "manual_vouch_review", self.vouch_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            vouch, error = await approve_manual_vouch(interaction.guild.id, self.vouch_id, interaction.user.id)
            if error == "processed":
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"manual_vouch:{self.vouch_id}")
                await interaction.response.send_message("Vouch ini sudah diproses.", ephemeral=True)
                return
            if error == "unresolved_target":
                await interaction.response.send_message("Target belum resolved. Reject atau minta user submit ulang.", ephemeral=True)
                return
            if error:
                await interaction.response.send_message("Vouch manual tidak ditemukan.", ephemeral=True)
                return
            await self._update_review_message(interaction, vouch, "Approved")
            await interaction.response.send_message("Manual vouch approved.", ephemeral=True)
            await send_deal_audit_log(
                interaction.guild,
                "Manual Vouch Approved",
                actor=interaction.user,
                target=await _manual_vouch_target_display(interaction.client, interaction.guild, vouch),
                vouch_id=vouch.get("id"),
                note=truncate_review(vouch.get("review"), 120),
            )
        finally:
            _release_action_lock(lock_key)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_reviewer(interaction):
            return
        lock_key = _acquire_action_lock("manual_vouch_review", interaction.guild.id, self.vouch_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "manual_vouch_review", self.vouch_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            vouch, error = await reject_manual_vouch(interaction.guild.id, self.vouch_id, interaction.user.id)
            if error == "processed":
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"manual_vouch:{self.vouch_id}")
                await interaction.response.send_message("Vouch ini sudah diproses.", ephemeral=True)
                return
            if error:
                await interaction.response.send_message("Vouch manual tidak ditemukan.", ephemeral=True)
                return
            await self._update_review_message(interaction, vouch, "Rejected")
            await interaction.response.send_message("Manual vouch rejected.", ephemeral=True)
            await send_deal_audit_log(
                interaction.guild,
                "Manual Vouch Rejected",
                actor=interaction.user,
                target=await _manual_vouch_target_display(interaction.client, interaction.guild, vouch),
                vouch_id=vouch.get("id"),
            )
        finally:
            _release_action_lock(lock_key)

    @discord.ui.button(label="📝 Reject with Reason", style=discord.ButtonStyle.secondary)
    async def reject_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_reviewer(interaction):
            return
        source_message = getattr(interaction, "message", None)
        await interaction.response.send_modal(RejectManualVouchModal(
            self.vouch_id,
            getattr(getattr(source_message, "channel", None), "id", None),
            getattr(source_message, "id", None),
        ))


class RejectManualVouchModal(discord.ui.Modal, title="Reject Manual Vouch"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, vouch_id: int, channel_id=None, message_id=None):
        super().__init__()
        self.vouch_id = int(vouch_id)
        self.channel_id = channel_id
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk review vouch.", ephemeral=True)
            return
        lock_key = _acquire_action_lock("manual_vouch_review", interaction.guild.id, self.vouch_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "manual_vouch_review", self.vouch_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            vouch, error = await reject_manual_vouch(interaction.guild.id, self.vouch_id, interaction.user.id, str(self.reason.value).strip())
            if error == "processed":
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"manual_vouch:{self.vouch_id}")
                await interaction.response.send_message("Vouch ini sudah diproses.", ephemeral=True)
                return
            if error:
                await interaction.response.send_message("Vouch manual tidak ditemukan.", ephemeral=True)
                return
            await interaction.response.send_message("Manual vouch rejected.", ephemeral=True)
            if self.channel_id and self.message_id:
                try:
                    channel = interaction.guild.get_channel(int(self.channel_id))
                    message = await channel.fetch_message(int(self.message_id)) if channel else None
                    if message:
                        await message.edit(
                        embed=await _manual_vouch_review_embed(vouch, interaction.guild, interaction.client, status_text="Rejected"),
                        view=None,
                        )
                except discord.HTTPException:
                    pass
            await send_deal_audit_log(
                interaction.guild,
                "Manual Vouch Rejected",
                actor=interaction.user,
                target=await _manual_vouch_target_display(interaction.client, interaction.guild, vouch),
                vouch_id=vouch.get("id"),
                reason=str(self.reason.value).strip(),
            )
        finally:
            _release_action_lock(lock_key)


async def _collect_manual_vouch_proofs(client_obj, channel, key):
    session = MANUAL_VOUCH_PROOF_SESSIONS.get(key)
    if not session:
        return

    def check(message):
        return (
            message.guild
            and str(message.guild.id) == key[0]
            and str(message.channel.id) == key[1]
            and str(message.author.id) == key[2]
        )

    end_at = datetime.utcnow().timestamp() + 300
    try:
        while MANUAL_VOUCH_PROOF_SESSIONS.get(key) is session and not session.get("submitted") and not session.get("cancelled"):
            timeout = max(1, end_at - datetime.utcnow().timestamp())
            proof_message = await client_obj.wait_for("message", check=check, timeout=timeout)
            if MANUAL_VOUCH_PROOF_SESSIONS.get(key) is not session or session.get("submitted") or session.get("cancelled"):
                return
            if not proof_message.attachments:
                continue
            valid_records = []
            for attachment in proof_message.attachments:
                if not _attachment_is_valid_proof(attachment):
                    await channel.send("Proof harus berupa gambar atau PDF.")
                    valid_records = []
                    break
                valid_records.append({
                    "filename": getattr(attachment, "filename", None),
                    "attachmentUrl": getattr(attachment, "url", None),
                    "messageJumpUrl": proof_message.jump_url,
                    "contentType": getattr(attachment, "content_type", None),
                })
            if not valid_records:
                continue
            if len(session["proofs"]) + len(valid_records) > 15:
                await record_rate_limit_event(channel.guild.id, key[2], "proof_upload_invalid", target_id="manual_vouch", event_key=f"manual_vouch_proof_limit:{key[2]}:{int(datetime.utcnow().timestamp())}")
                await _send_abuse_guard_audit(channel.guild, "Proof Upload Blocked - Too Many Files", note=f"manual_vouch user={key[2]}")
                await channel.send("Maksimal 15 proof per vouch.")
                continue
            session["proofs"].extend(valid_records)
    except asyncio.TimeoutError:
        current = MANUAL_VOUCH_PROOF_SESSIONS.get(key)
        if current is session and not session.get("submitted") and not session.get("cancelled"):
            MANUAL_VOUCH_PROOF_SESSIONS.pop(key, None)
            await channel.send("Upload proof vouch dibatalkan karena timeout.")


class ManualVouchProofSessionView(discord.ui.View):
    def __init__(self, key):
        super().__init__(timeout=300)
        self.key = key

    @discord.ui.button(label="✅ Submit Vouch", style=discord.ButtonStyle.success)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = MANUAL_VOUCH_PROOF_SESSIONS.get(self.key)
        if not session or session.get("cancelled"):
            await interaction.response.send_message("Sesi upload proof vouch sudah tidak aktif.", ephemeral=True)
            return
        if str(interaction.user.id) != self.key[2]:
            await interaction.response.send_message("Ini bukan sesi vouch kamu.", ephemeral=True)
            return
        if not session["proofs"]:
            await interaction.response.send_message("Proof wajib dilampirkan untuk submit vouch manual.", ephemeral=True)
            return
        review_config = await get_manual_vouch_review_config(interaction.guild.id)
        if not review_config or not review_config.get("enabled") or not review_config.get("reviewChannelId"):
            await interaction.response.send_message("Channel review vouch belum diatur. Hubungi staff.", ephemeral=True)
            return
        review_channel = interaction.guild.get_channel(int(review_config["reviewChannelId"]))
        if not review_channel:
            await interaction.response.send_message("Channel review vouch belum diatur. Hubungi staff.", ephemeral=True)
            return
        bot_member = interaction.guild.me
        if bot_member and not review_channel.permissions_for(bot_member).send_messages:
            await interaction.response.send_message("Channel review vouch belum diatur. Hubungi staff.", ephemeral=True)
            return
        data = session["data"]
        guard_error = await manual_vouch_submit_guard(interaction.guild.id, interaction.user.id, data.get("target_id"))
        if guard_error == "cooldown":
            await interaction.response.send_message("Terlalu cepat mengirim vouch manual. Coba lagi sebentar lagi.", ephemeral=True)
            return
        if guard_error == "too_many_pending":
            await _send_abuse_guard_audit(interaction.guild, "Manual Vouch Blocked - Too Many Pending", actor=interaction.user)
            await interaction.response.send_message("Kamu masih punya terlalu banyak vouch manual yang menunggu review.", ephemeral=True)
            return
        if guard_error == "duplicate_pending":
            await interaction.response.send_message("Kamu sudah memiliki vouch manual pending untuk user ini.", ephemeral=True)
            return
        vouch, error = await create_pending_manual_vouch(
            interaction.guild.id,
            interaction.user.id,
            data.get("target_id"),
            data.get("target_raw"),
            data.get("target_resolved"),
            data.get("rating"),
            data.get("review"),
            data.get("context"),
            data.get("notes"),
            session["proofs"],
        )
        if error == "too_many_pending":
            await _send_abuse_guard_audit(interaction.guild, "Manual Vouch Blocked - Too Many Pending", actor=interaction.user)
            await interaction.response.send_message("Kamu masih punya terlalu banyak vouch manual yang menunggu review.", ephemeral=True)
            return
        if error == "duplicate_pending":
            await interaction.response.send_message("Kamu sudah memiliki vouch manual pending untuk user ini.", ephemeral=True)
            return
        if error == "missing_proof":
            await interaction.response.send_message("Proof wajib dilampirkan untuk submit vouch manual.", ephemeral=True)
            return
        if error == "too_many_proofs":
            await _send_abuse_guard_audit(interaction.guild, "Proof Upload Blocked - Too Many Files", actor=interaction.user, note="manual_vouch")
            await interaction.response.send_message("Maksimal 15 proof per vouch.", ephemeral=True)
            return
        if error == "invalid_proof":
            await interaction.response.send_message("Proof harus berupa gambar atau PDF.", ephemeral=True)
            return
        if error:
            await interaction.response.send_message("Gagal submit vouch manual.", ephemeral=True)
            return
        await record_rate_limit_event(
            interaction.guild.id,
            interaction.user.id,
            "manual_vouch_submit",
            target_id=data.get("target_id"),
            event_key=f"manual_vouch:{vouch['id']}",
        )
        session["submitted"] = True
        MANUAL_VOUCH_PROOF_SESSIONS.pop(self.key, None)
        review_embed = await _manual_vouch_review_embed(vouch, interaction.guild, interaction.client)
        try:
            review_message = await review_channel.send(embed=review_embed, view=ManualVouchReviewView(vouch["id"]))
        except discord.HTTPException:
            await reject_manual_vouch(interaction.guild.id, vouch["id"], getattr(interaction.client.user, "id", interaction.user.id), "review channel send failed")
            await interaction.response.send_message("Channel review vouch belum diatur. Hubungi staff.", ephemeral=True)
            return
        evidence = await _post_manual_vouch_evidence(review_message, vouch)
        if evidence:
            await review_message.edit(embed=await _manual_vouch_review_embed(vouch, interaction.guild, interaction.client, evidence=evidence))
        await interaction.response.send_message("Vouch kamu sudah dikirim dan menunggu approval staff.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Manual Vouch Submitted",
            actor=interaction.user,
            target=await _manual_vouch_target_display(interaction.client, interaction.guild, vouch),
            vouch_id=vouch.get("id"),
            note=truncate_review(vouch.get("review"), 120),
        )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = MANUAL_VOUCH_PROOF_SESSIONS.get(self.key)
        if str(interaction.user.id) != self.key[2]:
            await interaction.response.send_message("Ini bukan sesi vouch kamu.", ephemeral=True)
            return
        if session:
            session["cancelled"] = True
            MANUAL_VOUCH_PROOF_SESSIONS.pop(self.key, None)
        await interaction.response.send_message("Submit vouch manual dibatalkan.", ephemeral=True)

    async def on_timeout(self):
        session = MANUAL_VOUCH_PROOF_SESSIONS.get(self.key)
        if session and not session.get("submitted") and not session.get("cancelled"):
            MANUAL_VOUCH_PROOF_SESSIONS.pop(self.key, None)


class ManualVouchSubmitModal(discord.ui.Modal, title="Submit Manual Vouch"):
    target_user = discord.ui.TextInput(label="Target User", placeholder="Mention / User ID / username yang ingin kamu vouch", max_length=120)
    rating = discord.ui.TextInput(label="Rating", placeholder="1 sampai 5", max_length=1)
    review = discord.ui.TextInput(label="Review", placeholder="Tulis review singkat dan jelas", style=discord.TextStyle.paragraph, max_length=1000)
    context = discord.ui.TextInput(label="Deal / Context", placeholder="Contoh: Robux, akun Roblox, gamepass, middleman, dll", required=False, max_length=200)
    notes = discord.ui.TextInput(label="Catatan Tambahan", placeholder="Opsional", required=False, style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        target_text = str(self.target_user.value or "").strip()
        if not target_text:
            await interaction.response.send_message("Target User tidak boleh kosong.", ephemeral=True)
            return
        target_member, target_raw, target_resolved = await _resolve_manual_vouch_target(interaction.guild, target_text)
        if target_member and target_member.id == interaction.user.id:
            await interaction.response.send_message("Kamu tidak bisa vouch diri sendiri.", ephemeral=True)
            return
        try:
            rating = int(str(self.rating.value).strip())
        except (TypeError, ValueError):
            await interaction.response.send_message("Rating harus angka 1 sampai 5.", ephemeral=True)
            return
        if rating < 1 or rating > 5:
            await interaction.response.send_message("Rating harus angka 1 sampai 5.", ephemeral=True)
            return
        review = str(self.review.value or "").strip()
        if len(review) < 3:
            await interaction.response.send_message("Review terlalu pendek.", ephemeral=True)
            return
        guard_error = await manual_vouch_submit_guard(
            interaction.guild.id,
            interaction.user.id,
            str(target_member.id) if target_member else None,
        )
        if guard_error == "cooldown":
            await interaction.response.send_message("Terlalu cepat mengirim vouch manual. Coba lagi sebentar lagi.", ephemeral=True)
            return
        if guard_error == "too_many_pending":
            await _send_abuse_guard_audit(interaction.guild, "Manual Vouch Blocked - Too Many Pending", actor=interaction.user)
            await interaction.response.send_message("Kamu masih punya terlalu banyak vouch manual yang menunggu review.", ephemeral=True)
            return
        if guard_error == "duplicate_pending":
            await interaction.response.send_message("Kamu sudah memiliki vouch manual pending untuk user ini.", ephemeral=True)
            return
        key = _manual_vouch_session_key(interaction.guild.id, interaction.channel.id, interaction.user.id)
        if key in MANUAL_VOUCH_PROOF_SESSIONS:
            await record_rate_limit_event(interaction.guild.id, interaction.user.id, "proof_upload_session_start", target_id="manual_vouch", event_key=f"manual_vouch_session_active:{interaction.channel.id}:{interaction.user.id}")
            await interaction.response.send_message("Sesi upload proof vouch masih aktif.", ephemeral=True)
            return
        MANUAL_VOUCH_PROOF_SESSIONS[key] = {
            "data": {
                "target_id": str(target_member.id) if target_member else None,
                "target_raw": target_raw,
                "target_resolved": bool(target_member and target_resolved),
                "rating": rating,
                "review": review,
                "context": str(self.context.value or "").strip(),
                "notes": str(self.notes.value or "").strip(),
            },
            "proofs": [],
            "submitted": False,
            "cancelled": False,
        }
        await record_rate_limit_event(interaction.guild.id, interaction.user.id, "proof_upload_session_start", target_id="manual_vouch", event_key=f"manual_vouch_session_start:{interaction.channel.id}:{interaction.user.id}:{int(datetime.utcnow().timestamp())}")
        interaction.client.loop.create_task(_collect_manual_vouch_proofs(interaction.client, interaction.channel, key))
        await interaction.response.send_message(
            "Silakan upload proof vouch kamu di channel ini.\n"
            "Kamu bisa upload banyak gambar sekaligus atau beberapa kali.\n\n"
            "File yang diterima:\n"
            "png, jpg, jpeg, webp, pdf\n\n"
            "Maksimal 15 proof.\n\n"
            "Setelah selesai, klik Submit Vouch.",
            view=ManualVouchProofSessionView(key),
            ephemeral=True,
        )


class ManualVouchPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⭐ Submit Vouch", style=discord.ButtonStyle.primary, custom_id="manual_vouch_submit")
    async def submit_vouch(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await get_manual_vouch_panel_config(interaction.guild.id)
        if not config or not config.get("enabled"):
            await interaction.response.send_message("Panel vouch sedang nonaktif.", ephemeral=True)
            return
        await interaction.response.send_modal(ManualVouchSubmitModal())


def _scam_report_session_key(guild_id, channel_id, user_id):
    return (str(guild_id), str(channel_id), str(user_id))


def _scam_report_panel_embed():
    embed = discord.Embed(
        title="🚨 Report Scammer",
        description=(
            "Gunakan tombol di bawah untuk melaporkan user yang diduga melakukan scam.\n\n"
            "Wajib siapkan proof:\n"
            "- screenshot chat\n"
            "- bukti pembayaran\n"
            "- bukti deal\n"
            "- profile / username pelaku\n\n"
            "Laporan tidak langsung membuat user blacklist.\n"
            "Semua laporan akan direview oleh staff terlebih dahulu."
        ),
        color=0xED4245,
    )
    embed.set_footer(text="W2E Scammer Report")
    return embed


async def _scam_report_target_display(bot, guild, report):
    if report.get("reportedUserId"):
        return await format_user_display(bot, guild, report.get("reportedUserId"))
    return f"unresolved: {report.get('reportedRaw') or '-'}"


async def _scam_report_review_embed(report, guild=None, bot=None, *, status_text=None, evidence=None):
    status = report.get("status") or "pending"
    color = 0xFEE75C
    title = "🚨 Pending Scammer Report"
    if status in ("under_review",):
        title = "👁️ Scammer Report Under Review"
        color = 0xFEE75C
    elif status in ("confirmed_scam", "blacklisted"):
        title = "⛔ Confirmed Scam / Blacklisted"
        color = 0xED4245
    elif status == "rejected":
        title = "❌ Scammer Report Rejected"
        color = 0xED4245
    elif status in ("resolved", "closed"):
        title = "✅ Scammer Report Resolved"
        color = 0x57F287
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Report ID", value=str(report.get("id")), inline=True)
    embed.add_field(name="Reported User", value=await _scam_report_target_display(bot, guild, report), inline=True)
    embed.add_field(name="Reported By", value=await format_user_display(bot, guild, report.get("reporterId")), inline=True)
    embed.add_field(name="Reason", value=truncate_review(report.get("reason"), 350), inline=False)
    embed.add_field(name="Kronologi", value=truncate_review(report.get("chronology"), 600), inline=False)
    embed.add_field(name="Nominal / Item", value=truncate_review(report.get("nominalItem") or "-", 160), inline=False)
    if report.get("notes"):
        embed.add_field(name="Notes", value=truncate_review(report.get("notes"), 200), inline=False)
    embed.add_field(name="Proof Count", value=str(report.get("proofCount") or 0), inline=True)
    if evidence:
        embed.add_field(name="Evidence", value=truncate_review(evidence, 900), inline=False)
    status_label = status_text or {
        "pending": "Pending Staff Review",
        "under_review": "Under Review",
        "confirmed_scam": "Confirmed Scam / Blacklisted",
        "blacklisted": "Confirmed Scam / Blacklisted",
        "rejected": "Rejected",
        "resolved": "Resolved / Closed",
        "closed": "Resolved / Closed",
    }.get(status, status)
    embed.add_field(name="Status", value=status_label, inline=False)
    if report.get("rejectionReason"):
        embed.add_field(name="Reject Reason", value=truncate_review(report.get("rejectionReason"), 250), inline=False)
    if report.get("resolution"):
        embed.add_field(name="Resolution", value=truncate_review(report.get("resolution"), 250), inline=False)
    if report.get("staffNotes"):
        embed.add_field(name="Staff Notes", value=truncate_review(report.get("staffNotes"), 450), inline=False)
    embed.set_footer(text="Scammer report requires staff review.")
    return embed


async def _post_scam_report_evidence(review_message, report):
    try:
        proofs = json.loads(report.get("proofData") or "[]")
    except Exception:
        proofs = []
    lines = []
    for idx, proof in enumerate(proofs, start=1):
        jump_url = proof.get("messageJumpUrl") or proof.get("attachmentUrl")
        filename = proof.get("filename") or f"proof-{idx}"
        if jump_url:
            lines.append(f"{idx}. [{filename}]({jump_url})")
    if not lines:
        return None, None
    try:
        thread = await review_message.create_thread(
            name=f"scam-report-{report.get('id')}-proof",
            auto_archive_duration=1440,
        )
        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > 1800:
                chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}".strip()
        if current:
            chunks.append(current)
        for chunk in chunks:
            await thread.send(chunk)
        return getattr(thread, "mention", None) or f"Thread: {thread.name}", thread.id
    except discord.HTTPException:
        return "\n".join(lines[:8]), None


class ScammerReportActionModal(discord.ui.Modal):
    def __init__(self, report_id: int, action: str, channel_id=None, message_id=None):
        title_map = {
            "under_review": "Mark Under Review",
            "blacklisted": "Confirm Scam / Blacklist",
            "rejected": "Reject Scammer Report",
            "note": "Add Report Note",
            "resolved": "Resolve / Close Report",
        }
        super().__init__(title=title_map.get(action, "Review Scammer Report"))
        self.report_id = int(report_id)
        self.action = action
        self.channel_id = channel_id
        self.message_id = message_id
        if action == "under_review":
            self.reason = discord.ui.TextInput(label="Reason", placeholder="Alasan user ditandai Under Review", max_length=500)
            self.staff_note = discord.ui.TextInput(label="Staff Note", placeholder="Catatan internal staff, opsional", required=False, style=discord.TextStyle.paragraph, max_length=500)
            self.add_item(self.reason)
            self.add_item(self.staff_note)
        elif action == "blacklisted":
            self.reason = discord.ui.TextInput(label="Blacklist Reason", placeholder="Alasan blacklist", max_length=500)
            self.evidence_summary = discord.ui.TextInput(label="Evidence Summary", placeholder="Ringkasan bukti, jangan isi data sensitif", style=discord.TextStyle.paragraph, max_length=800)
            self.staff_note = discord.ui.TextInput(label="Staff Note", placeholder="Catatan internal, opsional", required=False, style=discord.TextStyle.paragraph, max_length=500)
            self.duration = discord.ui.TextInput(label="Duration", placeholder="Permanent / temporary note, opsional", required=False, max_length=120)
            self.add_item(self.reason)
            self.add_item(self.evidence_summary)
            self.add_item(self.staff_note)
            self.add_item(self.duration)
        elif action == "rejected":
            self.reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=500)
            self.add_item(self.reason)
        elif action == "note":
            self.note = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph, max_length=800)
            self.add_item(self.note)
        elif action == "resolved":
            self.resolution = discord.ui.TextInput(label="Resolution", placeholder="Ringkasan penyelesaian report", style=discord.TextStyle.paragraph, max_length=800)
            self.staff_note = discord.ui.TextInput(label="Staff Note", placeholder="Opsional", required=False, style=discord.TextStyle.paragraph, max_length=500)
            self.add_item(self.resolution)
            self.add_item(self.staff_note)

    async def _edit_source_message(self, interaction, report, status_text):
        if not self.channel_id or not self.message_id:
            return
        try:
            channel = interaction.guild.get_channel(int(self.channel_id))
            message = await channel.fetch_message(int(self.message_id)) if channel else None
            if not message:
                return
            evidence = None
            for embed in getattr(message, "embeds", []) or []:
                for field in getattr(embed, "fields", []) or []:
                    if field.name == "Evidence":
                        evidence = field.value
                        break
            view = None if report.get("status") in SCAM_REPORT_FINAL_STATUSES else ScammerReportReviewView(report["id"])
            await message.edit(embed=await _scam_report_review_embed(report, interaction.guild, interaction.client, status_text=status_text, evidence=evidence), view=view)
        except discord.HTTPException:
            pass

    async def on_submit(self, interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk review report scammer.", ephemeral=True)
            return
        lock_key = _acquire_action_lock("scam_report_review", interaction.guild.id, self.report_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "scam_report_review", self.report_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            action_label = None
            if self.action == "under_review":
                report, error = await update_scam_report_status(
                    interaction.guild.id, self.report_id, interaction.user.id, "under_review",
                    reason=str(self.reason.value).strip(), note=str(self.staff_note.value).strip(),
                )
                response = "User berhasil ditandai Under Review."
                audit_action = "User Marked Under Review"
                action_label = "Under Review"
            elif self.action == "blacklisted":
                report, error = await update_scam_report_status(
                    interaction.guild.id, self.report_id, interaction.user.id, "blacklisted",
                    reason=str(self.reason.value).strip(), note=str(self.staff_note.value).strip(),
                    evidence_summary=str(self.evidence_summary.value).strip(), duration=str(self.duration.value).strip(),
                )
                response = "Report dikonfirmasi dan user ditandai Blacklisted."
                audit_action = "User Blacklisted"
                action_label = "Confirmed Scam / Blacklisted"
            elif self.action == "rejected":
                report, error = await update_scam_report_status(
                    interaction.guild.id, self.report_id, interaction.user.id, "rejected",
                    reason=str(self.reason.value).strip(),
                )
                response = "Report scammer rejected."
                audit_action = "Scammer Report Rejected"
                action_label = "Rejected"
            elif self.action == "note":
                report, error = await add_scam_report_note(interaction.guild.id, self.report_id, interaction.user.id, str(self.note.value).strip())
                response = "Note report berhasil ditambahkan."
                audit_action = "Scammer Report Note Added"
                action_label = None
            else:
                report, error = await update_scam_report_status(
                    interaction.guild.id, self.report_id, interaction.user.id, "resolved",
                    resolution=str(self.resolution.value).strip(), note=str(self.staff_note.value).strip(),
                )
                response = "Report scammer berhasil ditutup."
                audit_action = "Scammer Report Resolved"
                action_label = "Resolved / Closed"
            if error == "processed":
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"scam_report:{self.report_id}")
                await interaction.response.send_message("Report ini sudah diproses.", ephemeral=True)
                return
            if error:
                await interaction.response.send_message("Report scammer tidak ditemukan.", ephemeral=True)
                return
            await interaction.response.send_message(response, ephemeral=True)
            await self._edit_source_message(interaction, report, action_label or report.get("status"))
            await send_deal_audit_log(
                interaction.guild,
                audit_action,
                actor=interaction.user,
                target=await _scam_report_target_display(interaction.client, interaction.guild, report),
                report_id=report.get("id"),
                reason=getattr(getattr(self, "reason", None), "value", None),
                note=truncate_review(getattr(getattr(self, "note", None), "value", None) or getattr(getattr(self, "resolution", None), "value", None), 120),
            )
        finally:
            _release_action_lock(lock_key)


class ScammerReportReviewView(discord.ui.View):
    def __init__(self, report_id: int):
        super().__init__(timeout=86400)
        self.report_id = int(report_id)

    async def _require_staff(self, interaction):
        if await _can_configure_audit_log(interaction):
            return True
        await interaction.response.send_message("Kamu tidak punya permission untuk review report scammer.", ephemeral=True)
        return False

    async def _open_modal(self, interaction, action):
        if not await self._require_staff(interaction):
            return
        report = await get_scam_report_by_id(interaction.guild.id, self.report_id)
        if not report:
            await interaction.response.send_message("Report scammer tidak ditemukan.", ephemeral=True)
            return
        if report.get("status") in SCAM_REPORT_FINAL_STATUSES and action != "note":
            await interaction.response.send_message("Report ini sudah diproses.", ephemeral=True)
            return
        message = getattr(interaction, "message", None)
        await interaction.response.send_modal(ScammerReportActionModal(
            self.report_id,
            action,
            getattr(getattr(message, "channel", None), "id", None),
            getattr(message, "id", None),
        ))

    @discord.ui.button(label="👁️ Mark Under Review", style=discord.ButtonStyle.secondary)
    async def under_review(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_modal(interaction, "under_review")

    @discord.ui.button(label="⛔ Confirm Scam / Blacklist", style=discord.ButtonStyle.danger)
    async def blacklist(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_modal(interaction, "blacklisted")

    @discord.ui.button(label="❌ Reject Report", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_modal(interaction, "rejected")

    @discord.ui.button(label="📝 Add Note", style=discord.ButtonStyle.primary)
    async def note(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_modal(interaction, "note")

    @discord.ui.button(label="✅ Resolve / Close", style=discord.ButtonStyle.success)
    async def resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_modal(interaction, "resolved")


async def _collect_scam_report_proofs(client_obj, channel, key):
    session = SCAM_REPORT_PROOF_SESSIONS.get(key)
    if not session:
        return

    def check(message):
        return (
            message.guild
            and str(message.guild.id) == key[0]
            and str(message.channel.id) == key[1]
            and str(message.author.id) == key[2]
        )

    end_at = datetime.utcnow().timestamp() + 300
    try:
        while SCAM_REPORT_PROOF_SESSIONS.get(key) is session and not session.get("submitted") and not session.get("cancelled"):
            timeout = max(1, end_at - datetime.utcnow().timestamp())
            proof_message = await client_obj.wait_for("message", check=check, timeout=timeout)
            if SCAM_REPORT_PROOF_SESSIONS.get(key) is not session or session.get("submitted") or session.get("cancelled"):
                return
            if not proof_message.attachments:
                continue
            valid_records = []
            for attachment in proof_message.attachments:
                if not _attachment_is_valid_proof(attachment):
                    await channel.send("Proof harus berupa gambar atau PDF.")
                    valid_records = []
                    break
                valid_records.append({
                    "filename": getattr(attachment, "filename", None),
                    "attachmentUrl": getattr(attachment, "url", None),
                    "messageJumpUrl": proof_message.jump_url,
                    "contentType": getattr(attachment, "content_type", None),
                })
            if not valid_records:
                continue
            if len(session["proofs"]) + len(valid_records) > 15:
                await record_rate_limit_event(channel.guild.id, key[2], "proof_upload_invalid", target_id="scam_report", event_key=f"scam_report_proof_limit:{key[2]}:{int(datetime.utcnow().timestamp())}")
                await _send_abuse_guard_audit(channel.guild, "Proof Upload Blocked - Too Many Files", note=f"scam_report user={key[2]}")
                await channel.send("Maksimal 15 proof per laporan.")
                continue
            session["proofs"].extend(valid_records)
    except asyncio.TimeoutError:
        current = SCAM_REPORT_PROOF_SESSIONS.get(key)
        if current is session and not session.get("submitted") and not session.get("cancelled"):
            SCAM_REPORT_PROOF_SESSIONS.pop(key, None)
            await channel.send("Upload proof report scammer dibatalkan karena timeout.")


class ScammerReportProofSessionView(discord.ui.View):
    def __init__(self, key):
        super().__init__(timeout=300)
        self.key = key

    @discord.ui.button(label="✅ Submit Report", style=discord.ButtonStyle.success)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = SCAM_REPORT_PROOF_SESSIONS.get(self.key)
        if not session or session.get("cancelled"):
            await interaction.response.send_message("Sesi upload proof report scammer sudah tidak aktif.", ephemeral=True)
            return
        if str(interaction.user.id) != self.key[2]:
            await interaction.response.send_message("Ini bukan sesi report kamu.", ephemeral=True)
            return
        if not session["proofs"]:
            await interaction.response.send_message("Proof wajib dilampirkan untuk report scammer.", ephemeral=True)
            return
        review_config = await get_scam_report_review_config(interaction.guild.id)
        if not review_config or not review_config.get("enabled") or not review_config.get("reviewChannelId"):
            await interaction.response.send_message("Channel review report scammer belum diatur. Hubungi staff.", ephemeral=True)
            return
        review_channel = interaction.guild.get_channel(int(review_config["reviewChannelId"]))
        if not review_channel:
            await interaction.response.send_message("Channel review report scammer belum diatur. Hubungi staff.", ephemeral=True)
            return
        bot_member = interaction.guild.me
        if bot_member and not review_channel.permissions_for(bot_member).send_messages:
            await interaction.response.send_message("Channel review report scammer belum diatur. Hubungi staff.", ephemeral=True)
            return
        data = session["data"]
        guard_error = await scam_report_submit_guard(interaction.guild.id, interaction.user.id, data.get("reported_user_id"))
        if guard_error == "cooldown":
            await interaction.response.send_message("Terlalu cepat mengirim report scammer. Coba lagi sebentar lagi.", ephemeral=True)
            return
        if guard_error == "duplicate_pending":
            await _send_abuse_guard_audit(interaction.guild, "Scam Report Blocked - Duplicate Pending", actor=interaction.user)
            await interaction.response.send_message("Kamu sudah memiliki report pending untuk user ini.", ephemeral=True)
            return
        report, error = await create_pending_scam_report(
            interaction.guild.id,
            interaction.user.id,
            data.get("reported_user_id"),
            data.get("reported_raw"),
            data.get("reported_resolved"),
            data.get("reason"),
            data.get("chronology"),
            data.get("nominal_item"),
            data.get("notes"),
            session["proofs"],
        )
        if error == "duplicate_pending":
            await _send_abuse_guard_audit(interaction.guild, "Scam Report Blocked - Duplicate Pending", actor=interaction.user)
            await interaction.response.send_message("Kamu sudah memiliki report pending untuk user ini.", ephemeral=True)
            return
        if error == "missing_proof":
            await interaction.response.send_message("Proof wajib dilampirkan untuk report scammer.", ephemeral=True)
            return
        if error == "too_many_proofs":
            await _send_abuse_guard_audit(interaction.guild, "Proof Upload Blocked - Too Many Files", actor=interaction.user, note="scam_report")
            await interaction.response.send_message("Maksimal 15 proof per laporan.", ephemeral=True)
            return
        if error == "invalid_proof":
            await interaction.response.send_message("Proof harus berupa gambar atau PDF.", ephemeral=True)
            return
        if error:
            await interaction.response.send_message("Gagal submit report scammer.", ephemeral=True)
            return
        await record_rate_limit_event(
            interaction.guild.id,
            interaction.user.id,
            "scam_report_submit",
            target_id=data.get("reported_user_id"),
            event_key=f"scam_report:{report['id']}",
        )
        session["submitted"] = True
        SCAM_REPORT_PROOF_SESSIONS.pop(self.key, None)
        try:
            review_message = await review_channel.send(embed=await _scam_report_review_embed(report, interaction.guild, interaction.client), view=ScammerReportReviewView(report["id"]))
        except discord.HTTPException:
            await update_scam_report_status(interaction.guild.id, report["id"], getattr(interaction.client.user, "id", interaction.user.id), "rejected", reason="review channel send failed")
            await interaction.response.send_message("Channel review report scammer belum diatur. Hubungi staff.", ephemeral=True)
            return
        evidence, thread_id = await _post_scam_report_evidence(review_message, report)
        report = await set_scam_report_review_message(interaction.guild.id, report["id"], review_channel.id, review_message.id, thread_id)
        if evidence:
            await review_message.edit(embed=await _scam_report_review_embed(report, interaction.guild, interaction.client, evidence=evidence))
        await interaction.response.send_message("Report scammer kamu sudah dikirim dan menunggu review staff.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Scammer Report Submitted",
            actor=interaction.user,
            target=await _scam_report_target_display(interaction.client, interaction.guild, report),
            report_id=report.get("id"),
            reason=truncate_review(report.get("reason"), 120),
        )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = SCAM_REPORT_PROOF_SESSIONS.get(self.key)
        if str(interaction.user.id) != self.key[2]:
            await interaction.response.send_message("Ini bukan sesi report kamu.", ephemeral=True)
            return
        if session:
            session["cancelled"] = True
            SCAM_REPORT_PROOF_SESSIONS.pop(self.key, None)
        await interaction.response.send_message("Report scammer dibatalkan.", ephemeral=True)

    async def on_timeout(self):
        session = SCAM_REPORT_PROOF_SESSIONS.get(self.key)
        if session and not session.get("submitted") and not session.get("cancelled"):
            SCAM_REPORT_PROOF_SESSIONS.pop(self.key, None)


class ReportScammerModal(discord.ui.Modal, title="Report Scammer"):
    reported_user = discord.ui.TextInput(label="Reported User", placeholder="Mention / User ID / username pelaku", max_length=120)
    reason = discord.ui.TextInput(label="Reason", placeholder="Contoh: Tidak mengirim item setelah pembayaran", max_length=300)
    chronology = discord.ui.TextInput(label="Kronologi Singkat", placeholder="Jelaskan singkat kejadian scam", style=discord.TextStyle.paragraph, max_length=1000)
    nominal_item = discord.ui.TextInput(label="Nominal / Item", placeholder="Contoh: 150K / akun Roblox / Robux / dll", required=False, max_length=200)
    notes = discord.ui.TextInput(label="Catatan Tambahan", placeholder="Opsional", required=False, style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        target_text = str(self.reported_user.value or "").strip()
        if not target_text:
            await interaction.response.send_message("Reported User tidak boleh kosong.", ephemeral=True)
            return
        target_member, target_raw, target_resolved = await _resolve_manual_vouch_target(interaction.guild, target_text)
        if target_member and target_member.id == interaction.user.id:
            await interaction.response.send_message("Kamu tidak bisa report diri sendiri.", ephemeral=True)
            return
        reason = str(self.reason.value or "").strip()
        chronology = str(self.chronology.value or "").strip()
        if len(reason) < 3:
            await interaction.response.send_message("Reason terlalu pendek.", ephemeral=True)
            return
        if len(chronology) < 5:
            await interaction.response.send_message("Kronologi terlalu pendek.", ephemeral=True)
            return
        guard_error = await scam_report_submit_guard(
            interaction.guild.id,
            interaction.user.id,
            str(target_member.id) if target_member else None,
        )
        if guard_error == "cooldown":
            await interaction.response.send_message("Terlalu cepat mengirim report scammer. Coba lagi sebentar lagi.", ephemeral=True)
            return
        if guard_error == "duplicate_pending":
            await _send_abuse_guard_audit(interaction.guild, "Scam Report Blocked - Duplicate Pending", actor=interaction.user)
            await interaction.response.send_message("Kamu sudah memiliki report pending untuk user ini.", ephemeral=True)
            return
        key = _scam_report_session_key(interaction.guild.id, interaction.channel.id, interaction.user.id)
        if key in SCAM_REPORT_PROOF_SESSIONS:
            await record_rate_limit_event(interaction.guild.id, interaction.user.id, "proof_upload_session_start", target_id="scam_report", event_key=f"scam_report_session_active:{interaction.channel.id}:{interaction.user.id}")
            await interaction.response.send_message("Sesi upload proof report scammer masih aktif.", ephemeral=True)
            return
        SCAM_REPORT_PROOF_SESSIONS[key] = {
            "data": {
                "reported_user_id": str(target_member.id) if target_member else None,
                "reported_raw": target_raw,
                "reported_resolved": bool(target_member and target_resolved),
                "reason": reason,
                "chronology": chronology,
                "nominal_item": str(self.nominal_item.value or "").strip(),
                "notes": str(self.notes.value or "").strip(),
            },
            "proofs": [],
            "submitted": False,
            "cancelled": False,
        }
        await record_rate_limit_event(interaction.guild.id, interaction.user.id, "proof_upload_session_start", target_id="scam_report", event_key=f"scam_report_session_start:{interaction.channel.id}:{interaction.user.id}:{int(datetime.utcnow().timestamp())}")
        interaction.client.loop.create_task(_collect_scam_report_proofs(interaction.client, interaction.channel, key))
        await interaction.response.send_message(
            "Silakan upload proof report scammer di channel ini.\n"
            "Kamu bisa upload banyak gambar sekaligus atau beberapa kali.\n\n"
            "File yang diterima:\n"
            "png, jpg, jpeg, webp, pdf\n\n"
            "Maksimal 15 proof.\n\n"
            "Setelah selesai, klik Submit Report.",
            view=ScammerReportProofSessionView(key),
            ephemeral=True,
        )


class ScamReportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚨 Report Scammer", style=discord.ButtonStyle.danger, custom_id="scam_report_submit")
    async def report_scammer(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await get_scam_report_panel_config(interaction.guild.id)
        if not config or not config.get("enabled"):
            await interaction.response.send_message("Panel report scammer sedang nonaktif.", ephemeral=True)
            return
        await interaction.response.send_modal(ReportScammerModal())


async def _vouch_progress_embed(deal):
    vouches = await list_deal_vouches(deal["guildId"], deal["dealId"])
    completed = {(v["reviewerRole"], v["targetRole"]) for v in vouches}
    lines = []
    for reviewer_role, target_role, _reviewer_id, _target_id in get_possible_deal_vouches(deal):
        mark = "✅" if (reviewer_role, target_role) in completed else "⬜"
        lines.append(f"{mark} {reviewer_role} → {target_role}")
    embed = discord.Embed(
        title="⭐ Verified Middleman Deal Vouch",
        description=(
            f"Deal `{deal['dealId']}` has been completed.\n"
            "Participants can now leave verified vouches.\n\n"
            "**Progress**\n" + "\n".join(lines)
        ),
        color=0xFFD700,
    )
    embed.set_footer(text=f"Progress {len(completed)}/6 • Only locked deal participants can vouch")
    return embed, len(completed) >= 6
    lines = []
    for reviewer_role, target_role, _reviewer_id, _target_id in get_possible_deal_vouches(deal):
        mark = "✅" if (reviewer_role, target_role) in completed else "⬜"
        lines.append(f"{mark} {reviewer_role} → {target_role}")
    embed = discord.Embed(
        title="⭐ Verified Middleman Deal Vouch",
        description="\n".join(lines),
        color=0xFFD700,
    )
    embed.add_field(name="Deal ID", value=deal["dealId"], inline=True)
    embed.add_field(name="Progress", value=f"{len(completed)} / 6", inline=True)
    embed.set_footer(text="Vouch hanya bisa diberikan oleh participant deal yang terkunci.")
    return embed, len(completed) >= 6


async def _send_vouch_channel(interaction: discord.Interaction, vouch):
    config = await get_deal_config(interaction.guild.id)
    if not config or not config.get("vouchChannelId"):
        return
    channel = interaction.guild.get_channel(int(config["vouchChannelId"]))
    if not channel:
        return
    try:
        await channel.send(embed=await _vouch_success_embed(vouch, interaction.guild, interaction.client))
    except discord.HTTPException:
        pass


async def _log_account_age_suspicion(interaction: discord.Interaction, vouch):
    reasons = []
    now = datetime.utcnow().replace(tzinfo=None)
    for label, uid in (("reviewer", vouch["reviewerId"]), ("target", vouch["targetId"])):
        member = interaction.guild.get_member(int(uid))
        created_at = getattr(member, "created_at", None) if member else None
        if created_at:
            created_naive = created_at.replace(tzinfo=None)
            if (now - created_naive).days < 7:
                reasons.append(f"{label} account baru <7 hari")
    if reasons:
        await add_deal_log(
            vouch["guildId"],
            vouch["dealId"],
            "vouch_suspicious",
            vouch["reviewerId"],
            None,
            f"vouch_id={vouch['id']}",
            ", ".join(reasons),
        )


async def _refresh_vouch_progress_message(interaction: discord.Interaction, deal, progress_message_id=None):
    progress_message_id = progress_message_id or deal.get("vouchProgressMessageId")
    if not progress_message_id:
        return
    embed, complete = await _vouch_progress_embed(deal)
    view = VouchView(deal["id"], disabled=complete)
    try:
        message = await interaction.channel.fetch_message(int(progress_message_id))
        await message.edit(embed=embed, view=view)
    except (discord.HTTPException, ValueError, TypeError, AttributeError):
        pass


async def _deal_info_embed(deal, show_notes=False, guild=None, bot=None):
    embed = discord.Embed(title=f"Deal Info: {deal.get('dealId') or '-'}", color=0x5865F2)
    fields = [
        ("Buyer", await format_user_display(bot, guild, deal.get("buyerId"))),
        ("Seller", await format_user_display(bot, guild, deal.get("sellerId"))),
        ("Middleman", await format_user_display(bot, guild, deal.get("middlemanId"))),
        ("Product / Deskripsi Item", deal.get("description") or "-"),
        ("Nominal Item", format_rupiah(deal["nominalItem"] or 0)),
        ("MM Fee", format_rupiah(deal["mmFee"] or 0)),
        ("Buyer Pays", format_rupiah(deal["buyerPays"] or 0)),
        ("Seller Receives", format_rupiah(deal["sellerReceives"] or 0)),
        ("Status", deal.get("status") or "-"),
        ("Created At", format_discord_timestamp(deal.get("createdAt"), "f")),
        ("Last Updated", format_discord_timestamp(deal.get("updatedAt"), "R")),
        ("Payment Proof", _proof_link(deal, "payment")),
        ("Transfer Proof", _proof_link(deal, "transfer")),
    ]
    for name, value in fields:
        embed.add_field(name=name, value=str(value), inline=False)

    vouches = await list_deal_vouches(deal["guildId"], deal["dealId"])
    done_pairs = {(v["reviewerRole"], v["targetRole"]) for v in vouches}
    progress_lines = []
    for reviewer_role, target_role, _rid, _tid in get_possible_deal_vouches(deal):
        mark = "✅" if (reviewer_role, target_role) in done_pairs else "⏳"
        progress_lines.append(f"{mark} {reviewer_role} → {target_role}")
    embed.add_field(name="Vouch Progress", value="\n".join(progress_lines) if progress_lines else "-", inline=False)

    timeline = []
    timeline.append("✅ Deal Created" if deal.get("createdAt") else "⬜ Deal Created")
    timeline.append("✅ Form Submitted" if deal.get("dealId") else "⬜ Form Submitted")
    timeline.append("✅ Dana Masuk" if deal.get("fundsReceivedAt") else "⬜ Dana Masuk")
    timeline.append("✅ Item Sent" if deal.get("itemSentAt") else "⬜ Item Sent")
    timeline.append("✅ Buyer Confirm" if deal.get("buyerConfirmedAt") else "⬜ Buyer Confirm")
    timeline.append("✅ Done & Transfer Sukses" if deal.get("completedAt") else "⬜ Done & Transfer Sukses")
    if deal.get("status") == DEAL_STATUS_DISPUTED:
        timeline.append("⚠️ Disputed")
    if deal.get("status") == "Cancelled":
        timeline.append("❌ Cancelled")
    timeline.append("⏳ Vouch Progress")
    embed.add_field(name="Timeline", value="\n".join(timeline), inline=False)

    if show_notes:
        notes = await list_deal_notes(deal["guildId"], deal["dealId"])
        note_lines = []
        for n in notes[-10:]:
            actor = await format_user_display(bot, guild, n.get("actorId"))
            note_lines.append(f"{format_discord_timestamp(n.get('createdAt'), 'R')} {actor}: {n['note']}")
        embed.add_field(name="Internal Notes", value="\n".join(note_lines) if note_lines else "-", inline=False)
    embed.set_footer(text="W2E Middleman")
    return embed


def _deal_config_embed(guild: discord.Guild, config):
    config = config or {}
    categories = []
    for cid in config.get("allowedTicketCategoryIds", []):
        category = guild.get_channel(int(cid))
        categories.append(category.name if category else cid)
    role = guild.get_role(int(config["middlemanRoleId"])) if config.get("middlemanRoleId") else None
    owner_role = guild.get_role(int(config["ownerRoleId"])) if config.get("ownerRoleId") else None
    log_channel = guild.get_channel(int(config["dealLogChannelId"])) if config.get("dealLogChannelId") else None
    vouch_channel = guild.get_channel(int(config["vouchChannelId"])) if config.get("vouchChannelId") else None
    staff_role_mentions = []
    seen_role_ids = set()
    for rid in [config.get("middlemanRoleId"), *(config.get("dealStaffRoleIds") or [])]:
        if not rid or str(rid) in seen_role_ids:
            continue
        seen_role_ids.add(str(rid))
        staff_role = guild.get_role(int(rid))
        staff_role_mentions.append(staff_role.mention if staff_role else str(rid))
    if not staff_role_mentions:
        staff_role_mentions = ["Middleman", "Miserator"]
    intervals = config.get("reminderIntervals", {})
    embed = discord.Embed(title="Konfigurasi Middleman Deal", color=0x5865F2)
    embed.add_field(name="Deal staff roles", value=", ".join(staff_role_mentions), inline=False)
    embed.add_field(name="Middleman role utama", value=role.mention if role else "Default nama role: Middleman / Miserator", inline=False)
    embed.add_field(name="Owner role", value=owner_role.mention if owner_role else "-", inline=False)
    embed.add_field(name="Deal log channel", value=log_channel.mention if log_channel else "-", inline=False)
    embed.add_field(name="Vouch channel", value=vouch_channel.mention if vouch_channel else "-", inline=False)
    embed.add_field(name="Legacy ticket categories", value=(", ".join(categories) if categories else "-") + "\nTidak wajib; `/deal start` bisa dipakai di channel mana pun.", inline=False)
    embed.add_field(name="Deal ID prefix", value=config.get("dealIdPrefix") or "MM", inline=True)
    embed.add_field(name="Current phase", value=str(DEAL_SYSTEM_PHASE), inline=True)
    embed.add_field(name="Ping cooldown", value=f"{config.get('pingCooldownSeconds', 3600)} detik", inline=True)
    embed.add_field(name="Reminder enabled", value="Ya" if config.get("reminderEnabled") else "Tidak", inline=True)
    embed.add_field(name="Auto timeout enabled", value="Ya" if config.get("autoTimeoutEnabled") else "Tidak", inline=True)
    embed.add_field(
        name="Proof requirements",
        value=(
            f"Payment proof: {'Wajib' if config.get('requirePaymentProof') else 'Tidak wajib'}\n"
            f"Transfer proof: {'Wajib' if config.get('requireTransferProof') else 'Tidak wajib'}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Reminder intervals",
        value=(
            f"Form belum submit: {intervals.get('form_not_submitted_seconds', 7200)}s\n"
            f"Menunggu Dana Masuk: {intervals.get('waiting_funds_seconds', 21600)}s\n"
            f"Dana Masuk belum confirm: {intervals.get('funds_no_confirm_seconds', 86400)}s\n"
            f"Disputed: {intervals.get('disputed_seconds', 86400)}s\n"
            f"Timeout: {intervals.get('timeout_seconds', 604800)}s"
        ),
        inline=False,
    )
    embed.add_field(name="User cancel request", value="Aktif" if config.get("allowUserCancelRequest") else "Nonaktif", inline=True)
    embed.add_field(name="Trusted role threshold", value=str(config.get("trustedRoleThreshold", 0)), inline=True)
    return embed


class DealListView(discord.ui.View):
    def __init__(self, deals, page=0):
        super().__init__(timeout=180)
        self.deals = deals
        self.page = page
        self.page_size = 5
        self._sync_buttons()

    def _sync_buttons(self):
        max_page = max(0, (len(self.deals) - 1) // self.page_size)
        for child in self.children:
            if getattr(child, "custom_id", None) == "deal_list_prev":
                child.disabled = self.page <= 0
            elif getattr(child, "custom_id", None) == "deal_list_next":
                child.disabled = self.page >= max_page

    async def embed(self, guild=None, bot=None):
        embed = discord.Embed(title="Active Middleman Deals", color=0x5865F2)
        start = self.page * self.page_size
        page_items = self.deals[start:start + self.page_size]
        if not page_items:
            embed.description = "Tidak ada deal aktif."
        for deal in page_items:
            buyer = await format_user_display(bot, guild, deal.get("buyerId"))
            seller = await format_user_display(bot, guild, deal.get("sellerId"))
            middleman = await format_user_display(bot, guild, deal.get("middlemanId"))
            embed.add_field(
                name=f"{deal.get('dealId') or 'Pending'} • {deal['status']}",
                value=(
                    f"Channel: <#{deal['ticketChannelId']}>\n"
                    f"Buyer: {buyer} | Seller: {seller}\n"
                    f"Middleman: {middleman}"
                ),
                inline=False,
            )
        max_page = max(0, (len(self.deals) - 1) // self.page_size)
        embed.set_footer(text=f"Page {self.page + 1}/{max_page + 1}")
        return embed

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary, custom_id="deal_list_prev")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=await self.embed(interaction.guild, interaction.client), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="deal_list_next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, (len(self.deals) - 1) // self.page_size)
        self.page = min(max_page, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=await self.embed(interaction.guild, interaction.client), view=self)


async def _send_ephemeral(interaction: discord.Interaction, message: str):
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def _require_deal_phase(interaction: discord.Interaction, minimum_phase: int):
    if deal_phase_at_least(minimum_phase):
        return True
    await _send_ephemeral(interaction, "Fitur ini belum aktif di phase saat ini.")
    return False


async def _require_matching_deal_channel(interaction: discord.Interaction, deal):
    if str(getattr(interaction.channel, "id", "")) == str(deal.get("ticketChannelId")):
        return True
    await _send_ephemeral(interaction, "Command ini hanya bisa digunakan di channel deal yang sesuai.")
    return False


async def _can_manage_deal(interaction: discord.Interaction, deal=None, config=None):
    if interaction.user.guild_permissions.administrator:
        return True
    if deal and str(interaction.user.id) == str(deal.get("middlemanId")):
        return True
    config = config or await get_deal_config(interaction.guild.id)
    return member_has_deal_role(interaction.user, config)


async def _can_admin_override(interaction: discord.Interaction):
    config = await get_deal_config(interaction.guild.id)
    return member_can_admin_override(interaction.user, config)


async def _can_configure_audit_log(interaction: discord.Interaction):
    config = await get_deal_config(interaction.guild.id)
    return bool(
        interaction.user.guild_permissions.administrator
        or member_has_deal_role(interaction.user, config)
        or member_can_admin_override(interaction.user, config)
    )


DISPUTE_OPEN_STAFF_ONLY_MESSAGE = (
    "Dispute hanya bisa dibuka oleh middleman/staff. Jika ada kendala, "
    "silakan jelaskan masalahnya di ticket agar middleman bisa meninjau."
)


async def _can_open_dispute(interaction: discord.Interaction, deal):
    if not deal or not interaction.guild:
        return False
    if str(interaction.user.id) == str(deal.get("middlemanId")):
        return True
    config = await get_deal_config(interaction.guild.id)
    return bool(
        interaction.user.guild_permissions.administrator
        or member_has_deal_role(interaction.user, config)
        or member_can_admin_override(interaction.user, config)
    )


def _deal_start_trust_status(row):
    status = str((row or {}).get("status") or "clear").strip().lower()
    return status if status in {"clear", "under_review", "blacklisted"} else "clear"


def _deal_start_status_label(status):
    return {
        "clear": "Clear",
        "under_review": "Under Review",
        "blacklisted": "Blacklisted",
    }.get(status, "Clear")


def _member_has_configured_deal_staff_role(member, config):
    if not member or not config:
        return False
    configured_staff_ids = {str(role_id) for role_id in (config.get("dealStaffRoleIds") or [])}
    if not configured_staff_ids:
        return False
    return any(str(role.id) in configured_staff_ids for role in getattr(member, "roles", []))


def _can_override_under_review_participant(member, config):
    return bool(
        member_can_admin_override(member, config)
        or member_has_deal_role(member, config)
    )


def _can_start_while_middleman_under_review(member, config):
    return bool(
        member_can_admin_override(member, config)
        or _member_has_configured_deal_staff_role(member, config)
    )


async def _audit_deal_start_trust_event(interaction, action, affected, *, deal=None, status=None):
    try:
        target = affected[0][1] if len(affected) == 1 else None
        note = ", ".join(f"{role}={_deal_start_status_label(item_status)}" for role, _, item_status in affected)
        await send_deal_audit_log(
            interaction.guild,
            action,
            actor=interaction.user,
            target=target,
            deal_id=(deal.get("dealId") or deal.get("id")) if deal else None,
            reason="deal start safety",
            note=truncate_review(note, 180),
            metadata={"status": status or (affected[0][2] if affected else None)},
        )
    except Exception:
        pass


def _under_review_deal_start_embed(interaction, buyer, seller, statuses):
    embed = discord.Embed(
        title="⚠️ User Under Review",
        description=(
            "Salah satu participant dalam deal ini sedang berstatus Under Review.\n"
            "Lanjutkan deal hanya jika staff/middleman sudah memahami risikonya."
        ),
        color=0xFEE75C,
    )
    embed.add_field(name="Buyer Status", value=_deal_start_status_label(statuses["buyer"]["status"]), inline=True)
    embed.add_field(name="Seller Status", value=_deal_start_status_label(statuses["seller"]["status"]), inline=True)
    embed.add_field(name="Middleman", value=_deal_start_status_label(statuses["middleman"]["status"]), inline=True)
    embed.add_field(name="Override By", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value="Cek channel review/audit staff.", inline=False)
    return embed


async def _check_deal_start_trust_safety(interaction, buyer, seller, config):
    statuses = {
        "buyer": {
            "member": buyer,
            "status": _deal_start_trust_status(await get_trust_moderation_status(interaction.guild.id, buyer.id)),
        },
        "seller": {
            "member": seller,
            "status": _deal_start_trust_status(await get_trust_moderation_status(interaction.guild.id, seller.id)),
        },
        "middleman": {
            "member": interaction.user,
            "status": _deal_start_trust_status(await get_trust_moderation_status(interaction.guild.id, interaction.user.id)),
        },
    }

    participant_blacklisted = [
        (role, data["member"], data["status"])
        for role, data in statuses.items()
        if role in {"buyer", "seller"} and data["status"] == "blacklisted"
    ]
    middleman_blacklisted = statuses["middleman"]["status"] == "blacklisted"
    if middleman_blacklisted:
        await _audit_deal_start_trust_event(
            interaction,
            "Deal Start Blocked - Blacklisted User",
            [("middleman", interaction.user, "blacklisted")],
            status="blacklisted",
        )
        return {"allowed": False, "message": "Middleman ini sedang masuk blacklist dan tidak bisa menjalankan deal.", "statuses": statuses}
    if participant_blacklisted:
        await _audit_deal_start_trust_event(
            interaction,
            "Deal Start Blocked - Blacklisted User",
            participant_blacklisted,
            status="blacklisted",
        )
        return {"allowed": False, "message": "User ini sedang masuk blacklist dan tidak bisa mengikuti deal.", "statuses": statuses}

    participant_under_review = [
        (role, data["member"], data["status"])
        for role, data in statuses.items()
        if role in {"buyer", "seller"} and data["status"] == "under_review"
    ]
    if participant_under_review and not _can_override_under_review_participant(interaction.user, config):
        await _audit_deal_start_trust_event(
            interaction,
            "Deal Start Blocked - Under Review",
            participant_under_review,
            status="under_review",
        )
        return {"allowed": False, "message": "User ini sedang Under Review. Deal hanya bisa dilanjutkan oleh staff/middleman.", "statuses": statuses}

    middleman_under_review = statuses["middleman"]["status"] == "under_review"
    if middleman_under_review and not _can_start_while_middleman_under_review(interaction.user, config):
        await _audit_deal_start_trust_event(
            interaction,
            "Deal Start Blocked - Under Review",
            [("middleman", interaction.user, "under_review")],
            status="under_review",
        )
        return {"allowed": False, "message": "Middleman ini sedang Under Review. Deal hanya bisa dilanjutkan oleh administrator/staff.", "statuses": statuses}

    under_review = list(participant_under_review)
    if middleman_under_review:
        under_review.append(("middleman", interaction.user, "under_review"))
    return {"allowed": True, "statuses": statuses, "under_review": under_review}


def _archive_bool_label(value):
    return "Yes" if value else "No"


def _proof_status_label(value):
    return "Submitted" if value else "Not Submitted"


async def _deal_archive_embed(archive, guild=None, bot=None):
    embed = discord.Embed(title="🧾 Deal Archive", color=0x5865F2)
    embed.add_field(name="Deal ID", value=archive.get("dealId") or "-", inline=True)
    embed.add_field(name="Final Status", value=archive.get("finalStatus") or "-", inline=True)
    embed.add_field(name="Buyer", value=await format_user_display(bot, guild, archive.get("buyerId")), inline=True)
    embed.add_field(name="Seller", value=await format_user_display(bot, guild, archive.get("sellerId")), inline=True)
    embed.add_field(name="Middleman", value=await format_user_display(bot, guild, archive.get("middlemanId")), inline=True)
    embed.add_field(name="Payment Proof", value=_proof_status_label(archive.get("paymentProofSubmitted")), inline=True)
    embed.add_field(name="Transfer Proof", value=_proof_status_label(archive.get("transferProofSubmitted")), inline=True)
    embed.add_field(name="Vouch Eligible", value=_archive_bool_label(archive.get("vouchEligible")), inline=True)
    embed.add_field(name="Dispute Opened", value=_archive_bool_label(archive.get("disputeOpened")), inline=True)
    embed.add_field(name="Dispute Resolved", value=_archive_bool_label(archive.get("disputeResolved")), inline=True)
    embed.add_field(name="Created At", value=format_discord_timestamp(archive.get("createdAt"), "f"), inline=True)
    embed.add_field(name="Finalized At", value=format_discord_timestamp(archive.get("finalizedAt"), "f"), inline=True)
    embed.add_field(name="Archived At", value=format_discord_timestamp(archive.get("archivedAt"), "f"), inline=True)
    if archive.get("finalActionById"):
        embed.add_field(name="Final Action By", value=await format_user_display(bot, guild, archive.get("finalActionById")), inline=True)
    if archive.get("safeReason"):
        embed.add_field(name="Safe Reason", value=truncate_review(archive.get("safeReason"), 300), inline=False)
    if archive.get("safeResolution"):
        embed.add_field(name="Safe Resolution", value=truncate_review(archive.get("safeResolution"), 300), inline=False)
    embed.set_footer(text="Safe archive summary • Sensitive data hidden")
    return embed


async def _deal_archive_list_embed(title, archives, guild=None, bot=None):
    embed = discord.Embed(title=title, color=0x5865F2)
    if not archives:
        embed.description = "Archive deal tidak ditemukan."
        embed.set_footer(text="Safe archive summary • Sensitive data hidden")
        return embed
    for archive in archives[:10]:
        buyer = await format_user_display(bot, guild, archive.get("buyerId"))
        seller = await format_user_display(bot, guild, archive.get("sellerId"))
        value = (
            f"Status: **{archive.get('finalStatus') or '-'}**\n"
            f"Buyer: {buyer}\n"
            f"Seller: {seller}\n"
            f"Archived: {format_discord_timestamp(archive.get('archivedAt'), 'R')}"
        )
        embed.add_field(name=f"`{archive.get('dealId') or '-'}`", value=value, inline=False)
    embed.set_footer(text="Safe archive summary • Sensitive data hidden")
    return embed


async def _send_archive_embed_response(interaction, embed):
    if getattr(interaction, "message", None):
        try:
            await interaction.user.send(embed=embed)
        except discord.HTTPException:
            await interaction.response.send_message("Gagal mengirim DM archive. Buka DM bot lalu coba lagi.", ephemeral=True)
            return
        await interaction.response.send_message("Archive deal dikirim lewat DM.", ephemeral=True)
        return
    await interaction.response.send_message(embed=embed, ephemeral=True)


def _is_participant(interaction: discord.Interaction, deal):
    return get_deal_participant_role(deal, interaction.user.id) is not None


async def _cancel_embed(deal, guild=None, bot=None):
    embed = discord.Embed(title="❌ Deal Cancelled", color=0xED4245)
    embed.add_field(name="Deal ID", value=deal.get("dealId") or "-", inline=False)
    embed.add_field(name="Cancelled By", value=await format_user_display(bot, guild, deal.get("cancelledById")), inline=True)
    embed.add_field(name="Reason", value=deal.get("cancelReason") or "-", inline=False)
    embed.add_field(name="Fee Policy", value="Fee hangus / cari seller baru", inline=False)
    embed.add_field(name="Status", value="Cancelled", inline=False)
    embed.set_footer(text="W2E Middleman")
    return embed


async def _dispute_embed(deal, guild=None, bot=None):
    embed = discord.Embed(
        title="⚠️ Deal Disputed",
        description=(
            "Deal sedang ditahan sampai middleman/staff menyelesaikan masalah.\n"
            "Jangan lanjut transfer/payment sebelum ada keputusan."
        ),
        color=0xFEE75C,
    )
    embed.add_field(name="Deal ID", value=deal.get("dealId") or "-", inline=False)
    embed.add_field(name="Opened By", value=await format_user_display(bot, guild, deal.get("disputedById")), inline=True)
    embed.add_field(name="Buyer", value=await format_user_display(bot, guild, deal.get("buyerId")), inline=True)
    embed.add_field(name="Seller", value=await format_user_display(bot, guild, deal.get("sellerId")), inline=True)
    embed.add_field(name="Middleman", value=await format_user_display(bot, guild, deal.get("middlemanId")), inline=True)
    embed.add_field(name="Reason", value=deal.get("disputeReason") or "-", inline=False)
    embed.add_field(name="Previous Status", value=deal.get("statusBeforeDispute") or deal.get("disputePreviousStatus") or "-", inline=True)
    embed.add_field(name="Status", value=DEAL_STATUS_DISPUTED, inline=False)
    embed.set_footer(text="W2E Middleman")
    return embed


async def _dispute_resolved_embed(deal, resolution, guild=None, bot=None):
    embed = discord.Embed(
        title="✅ Dispute Resolved",
        description=(
            "Dispute sudah diselesaikan oleh middleman/staff.\n"
            "Deal dapat dilanjutkan dari status sebelumnya."
        ),
        color=0x57F287,
    )
    embed.add_field(name="Deal ID", value=deal.get("dealId") or "-", inline=False)
    embed.add_field(name="Resolved By", value=await format_user_display(bot, guild, deal.get("disputeResolvedById")), inline=True)
    embed.add_field(name="Resolution", value=resolution or deal.get("disputeResolution") or "-", inline=False)
    embed.add_field(name="Restored Status", value=deal.get("status") or "-", inline=True)
    embed.add_field(name="Status", value=deal.get("status") or "-", inline=True)
    return embed


def _view_for_deal_status(deal):
    status = deal.get("status")
    if status == DEAL_STATUS_WAITING_FUNDS:
        return DealSummaryView(deal["id"])
    if status == DEAL_STATUS_FUNDS_RECEIVED:
        return FundsReceivedView(deal["id"])
    if status == DEAL_STATUS_ITEM_SENT:
        return ItemSentView(deal["id"])
    if status == DEAL_STATUS_BUYER_CONFIRMED:
        return BuyerConfirmedView(deal["id"])
    if status == DEAL_STATUS_DISPUTED:
        return DisputeActionView(deal["id"])
    return SafeDealActionView(deal)


async def _ping_staff_for_dispute(interaction: discord.Interaction, deal):
    config = await get_deal_config(interaction.guild.id)
    role_id = config.get("middlemanRoleId") if config else None
    if role_id:
        try:
            await interaction.channel.send(f"<@&{role_id}> deal `{deal.get('dealId')}` sedang dispute.")
        except discord.HTTPException:
            pass


async def _update_summary_message(guild: discord.Guild, deal):
    if not deal.get("summaryMessageId"):
        return
    channel = guild.get_channel(int(deal["ticketChannelId"]))
    if not channel:
        return
    try:
        msg = await channel.fetch_message(int(deal["summaryMessageId"]))
        await msg.edit(embed=await _summary_embed(deal, guild, client), view=DealSummaryView(deal["id"]))
    except (discord.HTTPException, ValueError, TypeError):
        pass


async def _send_deal_log(interaction: discord.Interaction, deal, title: str, description: str):
    config = await get_deal_config(interaction.guild.id)
    if not config or not config.get("dealLogChannelId"):
        return
    channel = interaction.guild.get_channel(int(config["dealLogChannelId"]))
    if not channel:
        return
    embed = discord.Embed(title=title, description=description, color=0x5865F2)
    embed.add_field(name="Deal ID", value=deal.get("dealId") or "-", inline=True)
    embed.add_field(name="Status", value=deal.get("status") or "-", inline=True)
    embed.add_field(name="Actor", value=interaction.user.mention, inline=True)
    embed.set_footer(text="W2E Middleman Log")
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def _deal_audit_target(deal, guild=None, bot=None):
    buyer = await format_user_display(bot, guild, deal.get("buyerId"))
    seller = await format_user_display(bot, guild, deal.get("sellerId"))
    return f"Buyer: {buyer}\nSeller: {seller}"


async def _wait_for_proof_upload(interaction, deal, *, proof_type):
    is_payment = proof_type == "payment"
    session_set = PAYMENT_PROOF_SESSIONS if is_payment else TRANSFER_PROOF_SESSIONS
    session_message = "Sesi upload bukti payment masih aktif." if is_payment else "Sesi upload bukti transfer masih aktif."
    instruction = (
        "Silakan kirim screenshot/bukti pembayaran dalam bentuk gambar atau PDF di channel ini."
        if is_payment
        else "Silakan kirim screenshot/bukti transfer ke seller dalam bentuk gambar atau PDF di channel ini."
    )
    timeout_message = (
        "Upload bukti payment dibatalkan karena timeout."
        if is_payment
        else "Upload bukti transfer dibatalkan karena timeout."
    )
    expected_user_id = str(deal["buyerId"] if is_payment else deal["middlemanId"])
    expected_status = DEAL_STATUS_WAITING_FUNDS if is_payment else DEAL_STATUS_BUYER_CONFIRMED
    row_id = int(deal["id"])
    if row_id in session_set:
        await interaction.response.send_message(session_message, ephemeral=True)
        return None

    session_set.add(row_id)
    await interaction.response.send_message(instruction)

    def check(message):
        return (
            message.guild
            and message.guild.id == interaction.guild.id
            and message.channel.id == interaction.channel.id
            and str(message.author.id) == expected_user_id
        )

    try:
        proof_message = await interaction.client.wait_for("message", check=check, timeout=300)
        if not proof_message.attachments:
            await interaction.channel.send("Bukti harus berupa attachment gambar atau PDF.")
            return None
        attachment = proof_message.attachments[0]
        if not _attachment_is_valid_proof(attachment):
            await interaction.channel.send("Proof harus berupa gambar atau PDF.")
            return None
        latest_deal = await get_deal_by_id(row_id)
        if not latest_deal or latest_deal.get("status") != expected_status:
            await interaction.channel.send("Deal ini sudah tidak berada di tahap tersebut.")
            return None
        if is_payment and latest_deal.get("paymentProofMessageId"):
            await interaction.channel.send("Action ini sudah diproses.")
            return None
        if not is_payment and latest_deal.get("transferProofMessageId"):
            await interaction.channel.send("Action ini sudah diproses.")
            return None
        now = _now()
        field_prefix = "paymentProof" if is_payment else "transferProof"
        fields = {
            f"{field_prefix}Url": attachment.url,
            f"{field_prefix}MessageId": str(proof_message.id),
            f"{field_prefix}ChannelId": str(proof_message.channel.id),
            f"{field_prefix}SubmittedById": str(proof_message.author.id),
            f"{field_prefix}SubmittedAt": now,
        }
        updated, error = await update_deal_fields(
            row_id,
            proof_message.author.id,
            fields,
            "deal_payment_proof_submitted" if is_payment else "deal_transfer_proof_submitted",
            proof_message.jump_url,
        )
        if error:
            await interaction.channel.send("Gagal menyimpan bukti. Coba lagi nanti.")
            return None
        return updated, proof_message, attachment
    except asyncio.TimeoutError:
        await interaction.channel.send(timeout_message)
        return None
    finally:
        session_set.discard(row_id)


async def _payment_proof_embed(deal, guild=None, bot=None, attachment=None):
    embed = discord.Embed(
        title="📎 Bukti Payment Dikirim",
        description=(
            "Buyer telah mengirim bukti pembayaran.\n\n"
            "Middleman silakan cek bukti dan pastikan dana benar-benar masuk sebelum menekan tombol “Dana Masuk”."
        ),
        color=0x5865F2,
    )
    embed.add_field(name="Deal ID", value=f"`{deal.get('dealId')}`", inline=True)
    embed.add_field(name="Buyer", value=await format_user_display(bot, guild, deal.get("buyerId")), inline=True)
    embed.add_field(name="Payment Proof", value=_proof_link(deal, "payment"), inline=False)
    embed.add_field(name="Status", value="Menunggu Konfirmasi Middleman", inline=False)
    if attachment and str(getattr(attachment, "content_type", "") or "").startswith("image/"):
        embed.set_image(url=attachment.url)
    return embed


def _funds_received_embed():
    return _transition_embed(
        "✅ Uang Telah Diterima Middleman",
        (
            "Silakan seller mengirim item/barang yang dijual kepada pembeli.\n\n"
            "Setelah data/item diterima, mohon segera diamankan terlebih dahulu.\n"
            "JANGAN bilang DONE sebelum benar-benar merasa aman.\n\n"
            "• DONE = transaksi selesai\n\n"
            "WAJIB ALLREC UNTUK PENJUALAN AKUN"
        ),
    )


async def _handle_dana_masuk(interaction: discord.Interaction, deal_row_id: int, source_view=None):
    if not deal_phase_at_least(2):
        await interaction.response.send_message(DEAL_V1_PLACEHOLDER_MESSAGE, ephemeral=True)
        return
    lock_key = _acquire_action_lock("deal_dana_masuk", interaction.guild.id, deal_row_id, interaction.user.id)
    if not lock_key:
        await _send_lock_collision_audit(interaction, "deal_dana_masuk", deal_row_id)
        await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
        return
    try:
        deal = await get_deal_by_id(deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if await _block_if_disputed(interaction, deal):
            return
        if not _is_middleman(interaction, deal):
            await interaction.response.send_message("Hanya middleman yang ditugaskan yang bisa menandai Dana Masuk.", ephemeral=True)
            return
        if deal["status"] != DEAL_STATUS_WAITING_FUNDS:
            await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_dana_masuk:{deal_row_id}")
            await interaction.response.send_message("Deal ini sudah tidak menunggu konfirmasi dana.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id)
        if config and config.get("requirePaymentProof") and not deal.get("paymentProofMessageId"):
            await interaction.response.send_message("Buyer belum mengirim bukti payment.", ephemeral=True)
            return
        updated, error = await update_deal_status(
            int(deal_row_id),
            (DEAL_STATUS_WAITING_FUNDS,),
            DEAL_STATUS_FUNDS_RECEIVED,
            interaction.user.id,
            "deal_funds_received",
            {"fundsReceivedById": str(interaction.user.id), "fundsReceivedAt": _now()},
            reason=_proof_jump_url(deal, "payment"),
        )
        if error:
            await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_dana_masuk:{deal_row_id}")
            await interaction.response.send_message("Deal ini sudah tidak menunggu konfirmasi dana.", ephemeral=True)
            return
        if source_view is not None:
            await _disable_source_message(interaction, source_view)
        await interaction.response.send_message(embed=_funds_received_embed(), view=FundsReceivedView(updated["id"]))
        await _send_deal_log(interaction, updated, "Deal: Dana Masuk", "Uang telah diterima oleh middleman.")
    except Exception:
        logging.exception("Dana Masuk interaction failed for deal %s", deal_row_id)
        error_message = "Terjadi error saat memproses Dana Masuk. Cek console bot untuk detail."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)
        except Exception:
            logging.exception("Failed to send Dana Masuk error response for deal %s", deal_row_id)
    finally:
        _release_action_lock(lock_key)


async def _completed_embed(deal, guild=None, bot=None, attachment=None):
    embed = _transition_embed(
        "✅ Proses Done & Transfer Sukses!",
        (
            "Dana sudah diteruskan oleh middleman.\n"
            "Silakan cek rekening atau e-wallet kalian masing-masing.\n\n"
            "Setelah transaksi dinyatakan DONE, kedua pihak sudah berada di luar tanggung jawab middleman.\n\n"
            "Kecuali untuk kasus refful, warranty, atau kesepakatan khusus yang sudah disebutkan sebelum deal selesai."
        ),
    )
    embed.add_field(name="Deal ID", value=f"`{deal.get('dealId')}`", inline=True)
    embed.add_field(name="Buyer", value=await format_user_display(bot, guild, deal.get("buyerId")), inline=True)
    embed.add_field(name="Seller", value=await format_user_display(bot, guild, deal.get("sellerId")), inline=True)
    embed.add_field(name="Middleman", value=await format_user_display(bot, guild, deal.get("middlemanId")), inline=True)
    embed.add_field(name="Transfer Proof", value=_proof_link(deal, "transfer"), inline=False)
    embed.add_field(name="Status", value="Completed", inline=True)
    if attachment and str(getattr(attachment, "content_type", "") or "").startswith("image/"):
        embed.set_image(url=attachment.url)
    return embed


def _is_middleman(interaction: discord.Interaction, deal):
    return str(interaction.user.id) == str(deal.get("middlemanId"))


def _is_seller(interaction: discord.Interaction, deal):
    return str(interaction.user.id) == str(deal.get("sellerId"))


def _is_buyer(interaction: discord.Interaction, deal):
    return str(interaction.user.id) == str(deal.get("buyerId"))


async def _block_if_disputed(interaction: discord.Interaction, deal):
    if deal and deal.get("status") == DEAL_STATUS_DISPUTED:
        await interaction.response.send_message(
            "Deal ini sedang dalam status dispute. Selesaikan dispute terlebih dahulu sebelum melanjutkan.",
            ephemeral=True,
        )
        return True
    return False


async def _open_dispute_modal(interaction: discord.Interaction, deal_row_id: int):
    if not await _require_deal_phase(interaction, 4):
        return
    deal = await get_deal_by_id(deal_row_id)
    if not deal:
        await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
        return
    if deal.get("status") == DEAL_STATUS_DISPUTED:
        await interaction.response.send_message("Action ini sudah diproses.", ephemeral=True)
        return
    if _is_terminal_deal_status(deal.get("status")):
        await interaction.response.send_message("Deal ini sudah tidak bisa dibuat dispute.", ephemeral=True)
        return
    if not await _can_open_dispute(interaction, deal):
        await interaction.response.send_message(DISPUTE_OPEN_STAFF_ONLY_MESSAGE, ephemeral=True)
        return
    await interaction.response.send_modal(DisputeDealModal(deal_row_id))


class EditDealModal(discord.ui.Modal, title="Edit Deal"):
    payment_penjual = discord.ui.TextInput(label="Payment Penjual", max_length=200)
    payment_pembeli = discord.ui.TextInput(label="Payment Pembeli", max_length=200)
    nominal_item = discord.ui.TextInput(label="Nominal Item", max_length=40)
    fee_type = discord.ui.TextInput(label="Fee: Inc / Exc", max_length=10)
    description = discord.ui.TextInput(label="Deskripsi Item", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, deal, force=False):
        super().__init__()
        self.deal_row_id = int(deal["id"])
        self.force = force
        self.payment_penjual.default = deal.get("paymentPenjual") or ""
        self.payment_pembeli.default = deal.get("paymentPembeli") or ""
        self.nominal_item.default = str(deal.get("nominalItem") or "")
        self.fee_type.default = deal.get("feeType") or ""
        self.description.default = deal.get("description") or ""

    async def on_submit(self, interaction: discord.Interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if self.force:
            if not await _can_admin_override(interaction):
                await interaction.response.send_message("Hanya admin atau owner role yang bisa force-edit deal.", ephemeral=True)
                return
        elif not (_is_participant(interaction, deal) or await _can_manage_deal(interaction, deal=deal)):
            await interaction.response.send_message(
                "Kamu tidak memiliki akses untuk mengedit deal ini. Hanya buyer, seller, dan middleman yang bisa mengedit.",
                ephemeral=True,
            )
            return
        updated, error = await update_deal_editable_fields(
            self.deal_row_id,
            interaction.user.id,
            payment_penjual=str(self.payment_penjual.value).strip(),
            payment_pembeli=str(self.payment_pembeli.value).strip(),
            nominal_item=str(self.nominal_item.value).strip(),
            fee_type=str(self.fee_type.value).strip(),
            description=str(self.description.value).strip(),
            force=self.force,
        )
        if error == "invalid_status":
            await interaction.response.send_message("Deal hanya bisa diedit sebelum Dana Masuk.", ephemeral=True)
            return
        if error in ("invalid_nominal", "invalid_fee"):
            await interaction.response.send_message("Nominal atau fee tidak valid. Fee harus Inc/Exc.", ephemeral=True)
            return
        if error:
            await interaction.response.send_message("Gagal mengedit deal.", ephemeral=True)
            return
        await _update_summary_message(interaction.guild, updated)
        if self.force:
            await interaction.response.send_message("✅ Override berhasil: deal diedit dan fee sudah dihitung ulang.", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Deal berhasil diedit dan fee sudah dihitung ulang.", ephemeral=True)


class CancelDealModal(discord.ui.Modal, title="Cancel Deal"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, deal_row_id: int, *, allow_disputed: bool = False):
        super().__init__()
        self.deal_row_id = deal_row_id
        self.allow_disputed = allow_disputed

    async def on_submit(self, interaction: discord.Interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await _safe_respond(interaction, "Data deal tidak ditemukan.", ephemeral=True)
            return
        if deal.get("status") == DEAL_STATUS_DISPUTED and not self.allow_disputed:
            await _safe_respond(
                interaction,
                "Deal ini sedang dalam status dispute. Selesaikan dispute terlebih dahulu sebelum melanjutkan.",
                ephemeral=True,
            )
            return

        reason = str(self.reason.value).strip()
        is_manager = await _can_manage_deal(interaction, deal=deal)
        is_part = _is_participant(interaction, deal)

        if is_manager or is_part:
            is_pre_payment = deal.get("status") in (DEAL_STATUS_PENDING_FORM, DEAL_STATUS_WAITING_FUNDS)
            if is_manager or is_pre_payment:
                lock_key = _acquire_action_lock("deal_cancel", interaction.guild.id, self.deal_row_id, interaction.user.id)
                if not lock_key:
                    await _send_lock_collision_audit(interaction, "deal_cancel", self.deal_row_id)
                    await _safe_respond(interaction, "Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
                    return
                try:
                    cancelled, error = await cancel_deal(self.deal_row_id, interaction.user.id, reason)
                    if error:
                        await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_cancel:{self.deal_row_id}")
                        await _safe_respond(interaction, "Deal ini tidak bisa dibatalkan.", ephemeral=True)
                        return
                    _clear_deal_upload_sessions(self.deal_row_id)
                    await _safe_respond(interaction, embed=await _cancel_embed(cancelled, interaction.guild, interaction.client))
                    await send_deal_audit_log(
                        interaction.guild,
                        "Deal Cancelled",
                        actor=interaction.user,
                        target=await _deal_audit_target(cancelled, interaction.guild, interaction.client),
                        deal_id=cancelled.get("dealId"),
                        reason=reason,
                    )
                finally:
                    _release_action_lock(lock_key)
                return
            else:
                config = await get_deal_config(interaction.guild.id)
                if not config.get("allowUserCancelRequest", True):
                    await _safe_respond(interaction, "Pengajuan pembatalan oleh user dinonaktifkan di server ini. Silakan hubungi staff/middleman.", ephemeral=True)
                    return

                if deal["status"] in (DEAL_STATUS_COMPLETED, "Cancelled", "Voided/Duplicate"):
                    await _safe_respond(interaction, "Deal ini tidak bisa dibatalkan.", ephemeral=True)
                    return

                lock_key = _acquire_action_lock("deal_cancel_request", interaction.guild.id, self.deal_row_id, interaction.user.id)
                if not lock_key:
                    await _send_lock_collision_audit(interaction, "deal_cancel_request", self.deal_row_id)
                    await _safe_respond(interaction, "Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
                    return
                try:
                    requested, error = await request_deal_cancel(self.deal_row_id, interaction.user.id, reason)
                    if error:
                        await _safe_respond(interaction, "Gagal mengajukan pembatalan deal.", ephemeral=True)
                        return
                    await _safe_respond(interaction, f"✅ Permintaan pembatalan deal `{deal['dealId']}` telah diajukan. Menunggu konfirmasi dari staff atau middleman.", ephemeral=False)
                finally:
                    _release_action_lock(lock_key)
                return
        await _safe_respond(interaction, "Kamu tidak punya akses untuk cancel deal ini.", ephemeral=True)



class DisputeDealModal(discord.ui.Modal, title="Dispute Deal"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, deal_row_id: int):
        super().__init__()
        self.deal_row_id = deal_row_id

    async def on_submit(self, interaction: discord.Interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if deal.get("status") == DEAL_STATUS_DISPUTED:
            await interaction.response.send_message("Action ini sudah diproses.", ephemeral=True)
            return
        if not await _can_open_dispute(interaction, deal):
            await interaction.response.send_message(DISPUTE_OPEN_STAFF_ONLY_MESSAGE, ephemeral=True)
            return
        lock_key = _acquire_action_lock("deal_dispute", interaction.guild.id, self.deal_row_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "deal_dispute", self.deal_row_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            disputed, error = await dispute_deal(
                self.deal_row_id,
                interaction.user.id,
                str(self.reason.value).strip(),
            )
            if error == "missing_reason":
                await interaction.response.send_message("Reason wajib diisi.", ephemeral=True)
                return
            if error:
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_dispute:{self.deal_row_id}")
                await interaction.response.send_message("Deal ini tidak bisa dibuat dispute.", ephemeral=True)
                return
            _clear_deal_upload_sessions(self.deal_row_id)
            await interaction.response.send_message(
                "Jika ada bukti tambahan, silakan kirim screenshot/gambar langsung di channel ini.",
                embed=await _dispute_embed(disputed, interaction.guild, interaction.client),
                view=DisputeActionView(disputed["id"]),
            )
            await _ping_staff_for_dispute(interaction, disputed)
            await send_deal_audit_log(
                interaction.guild,
                "Dispute Opened",
                actor=interaction.user,
                target=await _deal_audit_target(disputed, interaction.guild, interaction.client),
                deal_id=disputed.get("dealId"),
                reason=str(self.reason.value).strip(),
            )
        finally:
            _release_action_lock(lock_key)


class ResolveDisputeModal(discord.ui.Modal, title="Resolve Dispute"):
    resolution = discord.ui.TextInput(
        label="Resolution Note",
        placeholder="Contoh: masalah sudah selesai, deal boleh dilanjutkan.",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, deal_row_id: int):
        super().__init__()
        self.deal_row_id = deal_row_id

    async def on_submit(self, interaction: discord.Interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if not await _can_manage_deal(interaction, deal=deal):
            await interaction.response.send_message("Kamu tidak punya permission untuk menyelesaikan dispute ini.", ephemeral=True)
            return
        lock_key = _acquire_action_lock("deal_resolve_dispute", interaction.guild.id, self.deal_row_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "deal_resolve_dispute", self.deal_row_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            resolved, error = await resolve_deal_dispute(self.deal_row_id, interaction.user.id, str(self.resolution.value).strip())
            if error == "missing_previous_status":
                await interaction.response.send_message("Status sebelum dispute tidak aman untuk dipulihkan. Gunakan force-status.", ephemeral=True)
                return
            if error:
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_resolve_dispute:{self.deal_row_id}")
                await interaction.response.send_message("Deal ini tidak berada dalam status Disputed.", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=await _dispute_resolved_embed(resolved, str(self.resolution.value).strip(), interaction.guild, interaction.client),
                view=_view_for_deal_status(resolved),
            )
            await send_deal_audit_log(
                interaction.guild,
                "Dispute Resolved",
                actor=interaction.user,
                target=await _deal_audit_target(resolved, interaction.guild, interaction.client),
                deal_id=resolved.get("dealId"),
                note=str(self.resolution.value).strip(),
                metadata={"status": resolved.get("status")},
            )
        finally:
            _release_action_lock(lock_key)


class AddDealNoteModal(discord.ui.Modal, title="Add Deal Note"):
    note = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, deal_row_id: int):
        super().__init__()
        self.deal_row_id = deal_row_id

    async def on_submit(self, interaction: discord.Interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if not await _can_manage_deal(interaction, deal=deal):
            await interaction.response.send_message("Kamu tidak punya permission untuk menyelesaikan dispute ini.", ephemeral=True)
            return
        note = str(self.note.value).strip()
        lock_key = _acquire_action_lock("deal_note", interaction.guild.id, self.deal_row_id, interaction.user.id, ttl=10)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "deal_note", self.deal_row_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            _note_id, error = await add_deal_note(interaction.guild.id, deal["dealId"], interaction.user.id, note)
            if error:
                await interaction.response.send_message("Note tidak boleh kosong.", ephemeral=True)
                return
            embed = discord.Embed(title="📝 Deal Note Added", color=0x5865F2)
            embed.add_field(name="Deal ID", value=deal.get("dealId") or "-", inline=True)
            embed.add_field(name="Added By", value=interaction.user.mention, inline=True)
            embed.add_field(name="Note", value=note, inline=False)
            await interaction.response.send_message(embed=embed)
        finally:
            _release_action_lock(lock_key)


class DisputeActionView(discord.ui.View):
    def __init__(self, deal_row_id: int):
        super().__init__(timeout=86400)
        self.deal_row_id = deal_row_id

    async def _require_staff(self, interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return None
        if deal.get("status") != DEAL_STATUS_DISPUTED:
            await interaction.response.send_message("Deal ini tidak berada dalam status Disputed.", ephemeral=True)
            return None
        if not await _can_manage_deal(interaction, deal=deal):
            await interaction.response.send_message("Kamu tidak punya permission untuk menyelesaikan dispute ini.", ephemeral=True)
            return None
        return deal

    @discord.ui.button(label="✅ Resolve / Undispute", style=discord.ButtonStyle.success)
    async def resolve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_staff(interaction):
            return
        await interaction.response.send_modal(ResolveDisputeModal(self.deal_row_id))

    @discord.ui.button(label="📝 Add Note", style=discord.ButtonStyle.secondary)
    async def add_note(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_staff(interaction):
            return
        await interaction.response.send_modal(AddDealNoteModal(self.deal_row_id))

    @discord.ui.button(label="❌ Cancel Deal", style=discord.ButtonStyle.danger)
    async def cancel_deal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_staff(interaction):
            return
        await interaction.response.send_modal(CancelDealModal(self.deal_row_id, allow_disputed=True))


class PaymentProofActionView(discord.ui.View):
    def __init__(self, deal_row_id: int):
        super().__init__(timeout=86400)
        self.deal_row_id = int(deal_row_id)

    @discord.ui.button(label="✅ Dana Masuk", style=discord.ButtonStyle.success)
    async def dana_masuk(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_dana_masuk(interaction, self.deal_row_id, PaymentProofActionView(self.deal_row_id))

    @discord.ui.button(label="⚠️ Dispute", style=discord.ButtonStyle.secondary)
    async def dispute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_dispute_modal(interaction, self.deal_row_id)


class DealSummaryView(discord.ui.View):
    def __init__(self, deal_row_id: int):
        super().__init__(timeout=86400)
        self.deal_row_id = deal_row_id

    @discord.ui.button(label="✅ Dana Masuk", style=discord.ButtonStyle.success)
    async def dana_masuk(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_dana_masuk(interaction, self.deal_row_id, DealSummaryView(self.deal_row_id))

    @discord.ui.button(label="✏️ Edit Deal", style=discord.ButtonStyle.primary)
    async def edit_deal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not deal_phase_at_least(2):
            await interaction.response.send_message(DEAL_V1_PLACEHOLDER_MESSAGE, ephemeral=True)
            return
        if not await _require_deal_phase(interaction, 4):
            return
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if await _block_if_disputed(interaction, deal):
            return
        if not (_is_participant(interaction, deal) or await _can_manage_deal(interaction, deal=deal)):
            await interaction.response.send_message(
                "Kamu tidak memiliki akses untuk mengedit deal ini. Hanya buyer, seller, dan middleman yang bisa mengedit.",
                ephemeral=True,
            )
            return
        if deal["status"] != DEAL_STATUS_WAITING_FUNDS:
            await interaction.response.send_message("Deal hanya bisa diedit sebelum Dana Masuk.", ephemeral=True)
            return
        await interaction.response.send_modal(EditDealModal(deal))

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not deal_phase_at_least(2):
            await interaction.response.send_message(DEAL_V1_PLACEHOLDER_MESSAGE, ephemeral=True)
            return
        if not await _require_deal_phase(interaction, 4):
            return
        await interaction.response.send_modal(CancelDealModal(self.deal_row_id))

    @discord.ui.button(label="⚠️ Dispute", style=discord.ButtonStyle.secondary)
    async def dispute(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not deal_phase_at_least(2):
            await interaction.response.send_message(DEAL_V1_PLACEHOLDER_MESSAGE, ephemeral=True)
            return
        await _open_dispute_modal(interaction, self.deal_row_id)


class FundsReceivedView(discord.ui.View):
    def __init__(self, deal_row_id: int):
        super().__init__(timeout=86400)
        self.deal_row_id = deal_row_id

    @discord.ui.button(label="📦 Item Sent", style=discord.ButtonStyle.primary)
    async def item_sent(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_deal_phase(interaction, 2):
            return
        lock_key = _acquire_action_lock("deal_item_sent", interaction.guild.id, self.deal_row_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "deal_item_sent", self.deal_row_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            deal = await get_deal_by_id(self.deal_row_id)
            if not deal:
                await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
                return
            if await _block_if_disputed(interaction, deal):
                return
            if not _is_seller(interaction, deal):
                await interaction.response.send_message("Hanya seller yang bisa menandai item/data telah dikirim.", ephemeral=True)
                return
            deal, error = await update_deal_status(
                self.deal_row_id,
                (DEAL_STATUS_FUNDS_RECEIVED,),
                DEAL_STATUS_ITEM_SENT,
                interaction.user.id,
                "deal_item_sent",
                {"itemSentById": str(interaction.user.id), "itemSentAt": _now()},
            )
            if error:
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_item_sent:{self.deal_row_id}")
                await interaction.response.send_message("Deal ini tidak berada di status Dana Masuk.", ephemeral=True)
                return
            await _disable_source_message(interaction, FundsReceivedView(self.deal_row_id))
            embed = _transition_embed(
                "📦 Item/Data Telah Dikirim",
                (
                    "Seller telah mengirim item/data kepada buyer.\n\n"
                    "Buyer silakan cek item/data sesuai detail deal.\n"
                    "Jika sudah sesuai, tekan tombol “Buyer Confirm”."
                ),
            )
            await interaction.response.send_message(embed=embed, view=ItemSentView(deal["id"]))
            await _send_deal_log(interaction, deal, "Deal: Item Sent", "Seller menandai item/data sudah dikirim.")
        finally:
            _release_action_lock(lock_key)

    @discord.ui.button(label="✅ Buyer Confirm", style=discord.ButtonStyle.success)
    async def buyer_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_deal_phase(interaction, 2):
            return
        await _buyer_confirm(interaction, self.deal_row_id)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_deal_phase(interaction, 4):
            return
        await interaction.response.send_modal(CancelDealModal(self.deal_row_id))

    @discord.ui.button(label="⚠️ Dispute", style=discord.ButtonStyle.secondary)
    async def dispute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_dispute_modal(interaction, self.deal_row_id)


class ItemSentView(discord.ui.View):
    def __init__(self, deal_row_id: int):
        super().__init__(timeout=86400)
        self.deal_row_id = deal_row_id

    @discord.ui.button(label="✅ Buyer Confirm", style=discord.ButtonStyle.success)
    async def buyer_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_deal_phase(interaction, 2):
            return
        await _buyer_confirm(interaction, self.deal_row_id)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_deal_phase(interaction, 4):
            return
        await interaction.response.send_modal(CancelDealModal(self.deal_row_id))

    @discord.ui.button(label="⚠️ Dispute", style=discord.ButtonStyle.secondary)
    async def dispute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_dispute_modal(interaction, self.deal_row_id)


class SellerPayoutModal(discord.ui.Modal, title="Data Pencairan Seller"):
    platform = discord.ui.TextInput(
        label="Platform",
        placeholder="Dana / OVO / Gopay / BCA / dll",
        max_length=100,
    )
    account = discord.ui.TextInput(
        label="No Rek / No HP / Email",
        placeholder="Nomor rekening, nomor e-wallet, atau email",
        max_length=200,
    )
    account_name = discord.ui.TextInput(
        label="Atas Nama",
        placeholder="Nama pemilik rekening/e-wallet",
        max_length=200,
    )

    def __init__(self, deal_row_id: int):
        super().__init__()
        self.deal_row_id = int(deal_row_id)

    async def on_submit(self, interaction: discord.Interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if await _block_if_disputed(interaction, deal):
            return
        if deal.get("status") != DEAL_STATUS_BUYER_CONFIRMED:
            await interaction.response.send_message("Deal ini belum berada di status Buyer Confirmed.", ephemeral=True)
            return
        if not (_is_seller(interaction, deal) or await _can_manage_deal(interaction, deal=deal)):
            await interaction.response.send_message("Hanya seller yang bisa mengirim data pencairan.", ephemeral=True)
            return

        platform = _clean_payout_value(self.platform.value)
        account = _clean_payout_value(self.account.value)
        account_name = _clean_payout_value(self.account_name.value)
        if not platform or not account or not account_name:
            await interaction.response.send_message("Data pencairan belum lengkap.", ephemeral=True)
            return

        was_update = _has_seller_payout_info(deal)
        lock_key = _acquire_action_lock("deal_seller_payout", interaction.guild.id, self.deal_row_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "deal_seller_payout", self.deal_row_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            latest = await get_deal_by_id(self.deal_row_id)
            if not latest or latest.get("status") != DEAL_STATUS_BUYER_CONFIRMED:
                await interaction.response.send_message("Deal ini sudah tidak berada di tahap tersebut.", ephemeral=True)
                return
            updated, error = await update_deal_fields(
                self.deal_row_id,
                interaction.user.id,
                {
                    "sellerPayoutPlatform": platform,
                    "sellerPayoutAccount": account,
                    "sellerPayoutName": account_name,
                    "sellerPayoutSubmittedById": str(interaction.user.id),
                    "sellerPayoutSubmittedAt": _now(),
                },
                "deal_seller_payout_submitted",
                "Seller payout data submitted.",
            )
            if error:
                await interaction.response.send_message("Gagal menyimpan data pencairan. Coba lagi nanti.", ephemeral=True)
                return

            content = "Data pencairan seller berhasil diperbarui." if was_update else None
            await interaction.response.send_message(
                content=content,
                embed=await _seller_payout_received_embed(updated, interaction.guild, interaction.client),
            )
        finally:
            _release_action_lock(lock_key)


class BuyerConfirmedView(discord.ui.View):
    def __init__(self, deal_row_id: int):
        super().__init__(timeout=86400)
        self.deal_row_id = deal_row_id

    @discord.ui.button(label="🏦 Kirim Data Pencairan", style=discord.ButtonStyle.primary)
    async def kirim_data_pencairan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_deal_phase(interaction, 2):
            return
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if await _block_if_disputed(interaction, deal):
            return
        if deal.get("status") != DEAL_STATUS_BUYER_CONFIRMED:
            await interaction.response.send_message("Deal ini belum berada di status Buyer Confirmed.", ephemeral=True)
            return
        if not (_is_seller(interaction, deal) or await _can_manage_deal(interaction, deal=deal)):
            await interaction.response.send_message("Hanya seller yang bisa mengirim data pencairan.", ephemeral=True)
            return
        await interaction.response.send_modal(SellerPayoutModal(self.deal_row_id))

    @discord.ui.button(label="✅ Done & Transfer Sukses", style=discord.ButtonStyle.success)
    async def done_transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_deal_phase(interaction, 2):
            return
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if await _block_if_disputed(interaction, deal):
            return
        if not _is_middleman(interaction, deal):
            await interaction.response.send_message("Hanya middleman yang ditugaskan yang bisa menyelesaikan deal.", ephemeral=True)
            return
        if deal["status"] != DEAL_STATUS_BUYER_CONFIRMED:
            await interaction.response.send_message("Deal ini belum berada di status Buyer Confirmed.", ephemeral=True)
            return
        if REQUIRE_SELLER_PAYOUT_INFO and not _has_seller_payout_info(deal):
            await interaction.response.send_message("Seller belum mengirim data pencairan.", ephemeral=True)
            return
        lock_key = _acquire_action_lock("deal_done_transfer", interaction.guild.id, self.deal_row_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "deal_done_transfer", self.deal_row_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        try:
            result = await _wait_for_proof_upload(interaction, deal, proof_type="transfer")
            if not result:
                return
            proofed_deal, _message, attachment = result
            completed, error = await update_deal_status(
                self.deal_row_id,
                (DEAL_STATUS_BUYER_CONFIRMED,),
                DEAL_STATUS_COMPLETED,
                interaction.user.id,
                "deal_completed",
                {
                    "completedById": str(interaction.user.id),
                    "completedAt": _now(),
                    "isVouchEligible": 1,
                },
                reason=_proof_jump_url(proofed_deal, "transfer"),
            )
            if error:
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_done_transfer:{self.deal_row_id}")
                await interaction.channel.send("Deal ini sudah tidak bisa diselesaikan.")
                return
            _clear_deal_upload_sessions(self.deal_row_id)
            await _disable_source_message(interaction, BuyerConfirmedView(self.deal_row_id))
            await interaction.channel.send(embed=await _completed_embed(completed, interaction.guild, interaction.client, attachment))
            await interaction.channel.send(embed=await _final_summary_embed(completed, interaction.guild, interaction.client))
            if deal_phase_at_least(3):
                progress_embed, complete = await _vouch_progress_embed(completed)
                progress_msg = await interaction.channel.send(embed=progress_embed, view=VouchView(completed["id"], disabled=complete))
                await set_deal_vouch_progress_message(completed["id"], progress_msg.id)
            await _send_deal_log(interaction, completed, "Deal: Completed", "Deal selesai dan transfer dana sukses.")
            await send_deal_audit_log(
                interaction.guild,
                "Deal Completed",
                actor=interaction.user,
                target=await _deal_audit_target(completed, interaction.guild, interaction.client),
                deal_id=completed.get("dealId"),
                note="Deal completed successfully.",
                metadata={"status": completed.get("status")},
            )
        finally:
            _release_action_lock(lock_key)

    @discord.ui.button(label="⚠️ Dispute", style=discord.ButtonStyle.secondary)
    async def dispute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_dispute_modal(interaction, self.deal_row_id)


class SafeDealActionView(discord.ui.View):
    def __init__(self, deal):
        super().__init__(timeout=86400)
        self.deal_row_id = int(deal["id"])

    @discord.ui.button(label="✏️ Edit Deal", style=discord.ButtonStyle.primary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if not await _can_manage_deal(interaction, deal=deal):
            await interaction.response.send_message("Hanya middleman atau admin yang bisa edit deal.", ephemeral=True)
            return
        await interaction.response.send_modal(EditDealModal(deal, force=True))

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if not await _can_manage_deal(interaction, deal=deal):
            await interaction.response.send_message("Kamu tidak punya permission untuk menyelesaikan dispute ini.", ephemeral=True)
            return
        await interaction.response.send_modal(CancelDealModal(self.deal_row_id))

    @discord.ui.button(label="⚠️ Dispute", style=discord.ButtonStyle.secondary)
    async def dispute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_dispute_modal(interaction, self.deal_row_id)


class VouchModal(discord.ui.Modal, title="Verified Deal Vouch"):
    rating = discord.ui.TextInput(label="Rating 1-5", max_length=1)
    review = discord.ui.TextInput(label="Review / feedback", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, deal_row_id: int, target_role: str, progress_message_id=None):
        super().__init__()
        self.deal_row_id = deal_row_id
        self.target_role = target_role
        self.progress_message_id = progress_message_id

    async def on_submit(self, interaction: discord.Interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if await _block_if_disputed(interaction, deal):
            return
        target_id = _target_id_for_role(deal, self.target_role)
        vouch, error = await create_verified_deal_vouch(
            deal,
            interaction.user.id,
            target_id,
            str(self.rating.value).strip(),
            str(self.review.value).strip(),
            None,
        )
        if error == "self":
            await interaction.response.send_message("Kamu tidak bisa memberi vouch ke diri sendiri.", ephemeral=True)
            return
        if error == "duplicate":
            await interaction.response.send_message("Kamu sudah memberi vouch untuk user ini di deal ini.", ephemeral=True)
            return
        if error == "invalid_rating":
            await interaction.response.send_message("Rating harus angka 1 sampai 5.", ephemeral=True)
            return
        if error == "empty_review":
            await interaction.response.send_message("Review tidak boleh kosong.", ephemeral=True)
            return
        if error == "short_review":
            await interaction.response.send_message("Review terlalu pendek.", ephemeral=True)
            return
        if error == "not_completed":
            await interaction.response.send_message("Vouch hanya bisa diberikan setelah deal Completed.", ephemeral=True)
            return
        if error in ("not_participant", "not_allowed"):
            await interaction.response.send_message("Kamu tidak punya izin memberi vouch untuk target ini.", ephemeral=True)
            return
        if error:
            await interaction.response.send_message("Gagal menyimpan vouch.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        await interaction.followup.send(embed=await _vouch_success_embed(vouch, interaction.guild, interaction.client))
        await _send_vouch_channel(interaction, vouch)
        await _log_account_age_suspicion(interaction, vouch)
        await _refresh_vouch_progress_message(interaction, deal, self.progress_message_id)


class VouchView(discord.ui.View):
    def __init__(self, deal_row_id: int, disabled=False):
        super().__init__(timeout=86400)
        self.deal_row_id = deal_row_id
        if disabled:
            for child in self.children:
                child.disabled = True

    async def _open_vouch(self, interaction: discord.Interaction, target_role: str):
        if not await _require_deal_phase(interaction, 3):
            return
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if await _block_if_disputed(interaction, deal):
            return
        if deal["status"] != DEAL_STATUS_COMPLETED or not deal.get("isVouchEligible"):
            await interaction.response.send_message("Vouch hanya bisa diberikan setelah deal Completed.", ephemeral=True)
            return
        target_id = _target_id_for_role(deal, target_role)
        if str(interaction.user.id) == str(target_id):
            await interaction.response.send_message("Kamu tidak bisa memberi vouch ke diri sendiri.", ephemeral=True)
            return
        reviewer_role = get_deal_participant_role(deal, interaction.user.id)
        if not reviewer_role or not can_deal_role_vouch_for(reviewer_role, target_role):
            await interaction.response.send_message("Kamu tidak punya izin memberi vouch untuk target ini.", ephemeral=True)
            return
        existing = await list_deal_vouches(deal["guildId"], deal["dealId"])
        if any(str(v["reviewerId"]) == str(interaction.user.id) and str(v["targetId"]) == str(target_id) for v in existing):
            await interaction.response.send_message("Kamu sudah memberi vouch untuk user ini di deal ini.", ephemeral=True)
            return
        progress_message_id = getattr(getattr(interaction, "message", None), "id", None) or deal.get("vouchProgressMessageId")
        await interaction.response.send_modal(VouchModal(self.deal_row_id, target_role, progress_message_id))

    @discord.ui.button(label="⭐ Vouch Buyer", style=discord.ButtonStyle.primary)
    async def vouch_buyer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_vouch(interaction, "Buyer")

    @discord.ui.button(label="⭐ Vouch Seller", style=discord.ButtonStyle.primary)
    async def vouch_seller(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_vouch(interaction, "Seller")

    @discord.ui.button(label="⭐ Vouch Middleman", style=discord.ButtonStyle.primary)
    async def vouch_middleman(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_vouch(interaction, "Middleman")


async def _buyer_confirm(interaction: discord.Interaction, deal_row_id: int):
    lock_key = _acquire_action_lock("deal_buyer_confirm", interaction.guild.id, deal_row_id, interaction.user.id)
    if not lock_key:
        await _send_lock_collision_audit(interaction, "deal_buyer_confirm", deal_row_id)
        await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
        return
    try:
        deal = await get_deal_by_id(deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if await _block_if_disputed(interaction, deal):
            return
        if not _is_buyer(interaction, deal):
            await interaction.response.send_message("Hanya buyer yang terkunci di deal ini yang bisa menekan Buyer Confirm.", ephemeral=True)
            return
        source_view = FundsReceivedView(deal_row_id) if deal["status"] == DEAL_STATUS_FUNDS_RECEIVED else ItemSentView(deal_row_id)
        deal, error = await update_deal_status(
            deal_row_id,
            (DEAL_STATUS_FUNDS_RECEIVED, DEAL_STATUS_ITEM_SENT),
            DEAL_STATUS_BUYER_CONFIRMED,
            interaction.user.id,
            "deal_buyer_confirmed",
            {"buyerConfirmedById": str(interaction.user.id), "buyerConfirmedAt": _now()},
        )
        if error:
            await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_buyer_confirm:{deal_row_id}")
            await interaction.response.send_message("Deal ini tidak berada di status Dana Masuk atau Item Sent.", ephemeral=True)
            return
        await _disable_source_message(interaction, source_view)
        await interaction.response.send_message(embed=await _buyer_confirm_embed(deal, interaction.guild, interaction.client))
        seller_display = await format_user_display(interaction.client, interaction.guild, deal.get("sellerId"))
        await interaction.channel.send(
            f"{seller_display} silakan isi data pencairan dana untuk proses transfer dari middleman.",
            embed=_seller_payout_instruction_embed(),
            view=BuyerConfirmedView(deal["id"]),
        )
        await _send_deal_log(interaction, deal, "Deal: Buyer Confirm", "Buyer mengonfirmasi item/data sudah diterima sesuai deal.")
    finally:
        _release_action_lock(lock_key)


class DealFormModal(discord.ui.Modal, title="Form Middleman Deal"):
    payment_penjual = discord.ui.TextInput(label="Payment Penjual", max_length=200)
    payment_pembeli = discord.ui.TextInput(label="Payment Pembeli", max_length=200)
    nominal_item = discord.ui.TextInput(label="Nominal Item", placeholder="Contoh: Rp150.000", max_length=40)
    fee_type = discord.ui.TextInput(label="Fee: Inc / Exc", placeholder="Inc atau Exc", max_length=10)
    description = discord.ui.TextInput(label="Deskripsi Item", style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, deal_row_id: int, middleman_id: int):
        super().__init__()
        self.deal_row_id = deal_row_id
        self.middleman_id = middleman_id

    async def on_submit(self, interaction: discord.Interaction):
        deal_row = await get_deal_by_id(self.deal_row_id)
        if not deal_row:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if not get_deal_participant_role(deal_row, interaction.user.id):
            await interaction.response.send_message("Hanya buyer, seller, atau middleman yang terlibat di deal ini yang bisa mengisi form.", ephemeral=True)
            return
        if deal_row["status"] != DEAL_STATUS_PENDING_FORM:
            await interaction.response.send_message("Form deal ini sudah diisi.", ephemeral=True)
            return

        nominal = parse_rupiah_amount(str(self.nominal_item.value))
        if nominal is None:
            await interaction.response.send_message(
                "Nominal item tidak valid. Gunakan format seperti 150000, 150.000, 150,000, atau Rp150.000.",
                ephemeral=True,
            )
            return

        fee_type = str(self.fee_type.value).strip().capitalize()
        if fee_type not in ("Inc", "Exc"):
            await interaction.response.send_message("Fee hanya boleh diisi Inc atau Exc.", ephemeral=True)
            return

        mm_fee = calculate_middleman_fee(nominal)
        if fee_type == "Exc":
            buyer_pays = nominal + mm_fee
            seller_receives = nominal
        else:
            buyer_pays = nominal
            seller_receives = nominal - mm_fee

        if seller_receives < 0:
            await interaction.response.send_message("Nominal item terlalu kecil untuk fee Inc.", ephemeral=True)
            return

        lock_key = _acquire_action_lock("deal_form_submit", interaction.guild.id, self.deal_row_id, interaction.user.id)
        if not lock_key:
            await _send_lock_collision_audit(interaction, "deal_form_submit", self.deal_row_id)
            await interaction.response.send_message("Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            deal = await finalize_deal_from_form(
                self.deal_row_id,
                submitted_by_id=interaction.user.id,
                payment_penjual=str(self.payment_penjual.value).strip(),
                payment_pembeli=str(self.payment_pembeli.value).strip(),
                nominal_item=nominal,
                fee_type=fee_type,
                mm_fee=mm_fee,
                buyer_pays=buyer_pays,
                seller_receives=seller_receives,
                description=str(self.description.value).strip(),
            )
            if not deal:
                await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_form_submit:{self.deal_row_id}")
                await interaction.followup.send("Form deal ini sudah diisi.", ephemeral=True)
                return

            msg = await interaction.followup.send(embed=await _summary_embed(deal, interaction.guild, interaction.client), view=DealSummaryView(deal["id"]), wait=True)
            await set_deal_summary_message(deal["id"], msg.id)
        finally:
            _release_action_lock(lock_key)


class DealStartView(discord.ui.View):
    def __init__(self, deal):
        super().__init__(timeout=86400)
        self.deal_row_id = int(deal["id"])
        self.middleman_id = int(deal["middlemanId"])

    async def _open_form(self, interaction: discord.Interaction):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if not get_deal_participant_role(deal, interaction.user.id):
            await interaction.response.send_message("Hanya buyer, seller, atau middleman yang terlibat di deal ini yang bisa mengisi form.", ephemeral=True)
            return
        if deal["status"] != DEAL_STATUS_PENDING_FORM:
            await interaction.response.send_message("Form deal ini sudah diisi.", ephemeral=True)
            return
        try:
            await interaction.response.send_modal(DealFormModal(self.deal_row_id, self.middleman_id))
        except discord.HTTPException:
            if not interaction.response.is_done():
                await interaction.response.send_message("Form gagal dibuka. Silakan klik tombol Form lagi.", ephemeral=True)
            else:
                await interaction.followup.send("Form gagal dibuka. Silakan klik tombol Form lagi.", ephemeral=True)

    @discord.ui.button(label="⚠️ Ketentuan", style=discord.ButtonStyle.secondary)
    async def ketentuan(self, interaction: discord.Interaction, button: discord.ui.Button):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=_terms_embed(), view=DealTermsView(deal))

    @discord.ui.button(label="📋 Form", style=discord.ButtonStyle.primary)
    async def form(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_form(interaction)

    @discord.ui.button(label="❌ Cancel Request", style=discord.ButtonStyle.danger)
    async def cancel_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        deal = await get_deal_by_id(self.deal_row_id)
        if not deal:
            await interaction.response.send_message("Data deal tidak ditemukan.", ephemeral=True)
            return
        if not await _can_manage_deal(interaction, deal=deal):
            await interaction.response.send_message("Hanya middleman atau staff yang bisa membatalkan request ini.", ephemeral=True)
            return
        ok = await cancel_pending_deal(self.deal_row_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message("Request ini sudah tidak bisa dibatalkan.", ephemeral=True)
            return
        deal["status"] = "Cancelled"
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=await _warning_embed(deal, interaction.guild, interaction.client), view=self)


class DealTermsView(discord.ui.View):
    def __init__(self, deal):
        super().__init__(timeout=86400)
        self.deal = deal
        self.middleman_id = int(deal["middlemanId"])

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        fresh = await get_deal_by_id(self.deal["id"]) or self.deal
        await interaction.response.edit_message(embed=await _warning_embed(fresh, interaction.guild, interaction.client), view=DealStartView(fresh))

    @discord.ui.button(label="📋 Form", style=discord.ButtonStyle.primary)
    async def form(self, interaction: discord.Interaction, button: discord.ui.Button):
        fresh = await get_deal_by_id(self.deal["id"]) or self.deal
        if not get_deal_participant_role(fresh, interaction.user.id):
            await interaction.response.send_message("Hanya buyer, seller, atau middleman yang terlibat di deal ini yang bisa mengisi form.", ephemeral=True)
            return
        if fresh["status"] != DEAL_STATUS_PENDING_FORM:
            await interaction.response.send_message("Form deal ini sudah diisi.", ephemeral=True)
            return
        try:
            await interaction.response.send_modal(DealFormModal(int(self.deal["id"]), self.middleman_id))
        except discord.HTTPException:
            if not interaction.response.is_done():
                await interaction.response.send_message("Form gagal dibuka. Silakan klik tombol Form lagi.", ephemeral=True)
            else:
                await interaction.followup.send("Form gagal dibuka. Silakan klik tombol Form lagi.", ephemeral=True)


class PrefixEditDealView(discord.ui.View):
    def __init__(self, deal_id: str, force: bool = False):
        super().__init__(timeout=180)
        self.deal_id = str(deal_id).strip().upper()
        self.force = bool(force)

    @discord.ui.button(label="Buka Form Edit", style=discord.ButtonStyle.primary)
    async def open_edit_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _require_deal_phase(interaction, 4):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, self.deal_id)
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if self.force:
            if not await _can_admin_override(interaction):
                await interaction.response.send_message("Hanya admin atau owner role yang bisa memakai override.", ephemeral=True)
                return
            await interaction.response.send_modal(EditDealModal(deal, force=True))
            return
        if not await _require_matching_deal_channel(interaction, deal):
            return
        if not (_is_participant(interaction, deal) or await _can_manage_deal(interaction, deal=deal)):
            await interaction.response.send_message(
                "Kamu tidak memiliki akses untuk mengedit deal ini. Hanya buyer, seller, dan middleman yang bisa mengedit.",
                ephemeral=True,
            )
            return
        if deal["status"] != DEAL_STATUS_WAITING_FUNDS:
            await interaction.response.send_message("Deal hanya bisa diedit sebelum Dana Masuk.", ephemeral=True)
            return
        await interaction.response.send_modal(EditDealModal(deal))


def setup(tree, client):
    deal_group = app_commands.Group(name="deal", description="Sistem middleman deal")
    config_group = app_commands.Group(name="config", description="Konfigurasi middleman deal")
    audit_group = app_commands.Group(name="audit-log", description="Audit log staff untuk deal")
    archive_group = app_commands.Group(name="archive", description="Archive aman deal final")
    panel_group = app_commands.Group(name="panel", description="Public trust panels")
    mm_status_group = app_commands.Group(name="mm-status", description="Status operasi middleman")
    vouch_review_group = app_commands.Group(name="vouch-review-channel", description="Channel review manual vouch")
    vouch_panel_group = app_commands.Group(name="vouch-panel", description="Panel submit manual vouch")
    scam_review_group = app_commands.Group(name="scam-report-review-channel", description="Channel review report scammer")
    scam_panel_group = app_commands.Group(name="scam-report-panel", description="Panel report scammer")
    trust_status_group = app_commands.Group(name="trust-status", description="Moderasi trust status user")
    try:
        client.add_view(ManualVouchPanelView())
        client.add_view(ScamReportPanelView())
    except Exception:
        pass

    async def _prefix_send(message, text):
        await message.reply(text, delete_after=10)

    async def _prefix_member(guild, token):
        token = str(token or "").strip()
        match = re.fullmatch(r"<@!?([0-9]+)>", token)
        raw_id = match.group(1) if match else token
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        member = guild.get_member(user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(user_id)
        except (discord.HTTPException, discord.NotFound):
            return None

    def _prefix_role(guild, token):
        token = str(token or "").strip()
        match = re.fullmatch(r"<@&([0-9]+)>", token)
        raw_id = match.group(1) if match else token
        try:
            return guild.get_role(int(raw_id))
        except (TypeError, ValueError):
            return None

    async def _prefix_channel(guild, token):
        token = str(token or "").strip()
        match = re.fullmatch(r"<#([0-9]+)>", token)
        raw_id = match.group(1) if match else token
        try:
            channel_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        channel = guild.get_channel(channel_id)
        if channel:
            return channel
        try:
            return await guild.fetch_channel(channel_id)
        except (discord.HTTPException, discord.NotFound):
            return None

    def _prefix_int(token):
        try:
            return int(str(token).strip())
        except (TypeError, ValueError):
            return None

    def _join_tail(tokens):
        return " ".join(str(token) for token in tokens).strip()

    def _tail_with_optional_proof(tokens):
        items = [str(token) for token in tokens]
        proof = None
        if items and items[-1].lower().startswith(("http://", "https://")):
            proof = items.pop()
        return _join_tail(items), proof

    async def _run_prefix_command(command, interaction, *args):
        callback = getattr(command, "callback", command)
        await callback(interaction, *args)

    async def _prefix_edit_prompt(interaction, deal_id, force=False):
        if not await _require_deal_phase(interaction, 4):
            return
        await interaction.response.send_message(
            "Klik tombol di bawah untuk membuka form edit deal.",
            view=PrefixEditDealView(deal_id, force=force),
        )

    async def deal_prefix_dispatcher(message, args):
        if not message.guild:
            await _prefix_send(message, "Command ini hanya bisa digunakan di server.")
            return
        if not args:
            await _prefix_send(message, "Command ini belum tersedia.")
            return

        interaction = FakeInteraction(message)
        subcommand = args[0].lower()

        if subcommand == "start":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal start @buyer @seller")
                return
            buyer = await _prefix_member(message.guild, args[1])
            seller = await _prefix_member(message.guild, args[2])
            if not buyer or not seller:
                await _prefix_send(message, "Buyer atau seller tidak valid.")
                return
            await _run_prefix_command(deal_start, interaction, buyer, seller)
            return

        if subcommand == "add-user":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal add-user <deal_id> @user")
                return
            user = await _prefix_member(message.guild, args[2])
            if not user:
                await _prefix_send(message, "User tidak valid.")
                return
            await _run_prefix_command(deal_add_user, interaction, args[1], user)
            return

        if subcommand == "audit-log":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal audit-log set #channel | disable | status")
                return
            audit_cmd = args[1].lower()
            if audit_cmd == "set":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal audit-log set #channel")
                    return
                channel = await _prefix_channel(message.guild, args[2])
                if not isinstance(channel, discord.TextChannel):
                    await _prefix_send(message, "Channel tidak valid.")
                    return
                await _run_prefix_command(audit_log_set, interaction, channel)
                return
            if audit_cmd == "disable":
                await _run_prefix_command(audit_log_disable, interaction)
                return
            if audit_cmd == "status":
                await _run_prefix_command(audit_log_status, interaction)
                return
            await _prefix_send(message, "Command audit-log tidak dikenal.")
            return

        if subcommand == "archive":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal archive info <deal_id> | search @user | recent | backfill")
                return
            archive_cmd = args[1].lower()
            if archive_cmd == "info":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal archive info <deal_id>")
                    return
                await _run_prefix_command(deal_archive_info, interaction, args[2])
                return
            if archive_cmd == "search":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal archive search @user")
                    return
                user = await _prefix_member(message.guild, args[2])
                if not user:
                    await _prefix_send(message, "User tidak valid.")
                    return
                await _run_prefix_command(deal_archive_search, interaction, user)
                return
            if archive_cmd == "recent":
                await _run_prefix_command(deal_archive_recent, interaction)
                return
            if archive_cmd == "backfill":
                await _run_prefix_command(deal_archive_backfill, interaction)
                return
            await _prefix_send(message, "Command archive tidak dikenal.")
            return

        if subcommand == "panel":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal panel leaderboard|stats|recent-vouches|completed-deals|middleman-status|active-deals|dispute-board|trust-warning set|refresh|disable|status")
                return
            panel_name = args[1].lower()
            panel_cmd = args[2].lower()
            panel_map = {
                "leaderboard": {
                    "set": panel_leaderboard_set,
                    "refresh": panel_leaderboard_refresh,
                    "disable": panel_leaderboard_disable,
                    "status": panel_leaderboard_status,
                },
                "stats": {
                    "set": panel_stats_set,
                    "refresh": panel_stats_refresh,
                    "disable": panel_stats_disable,
                    "status": panel_stats_status,
                },
                "recent-vouches": {
                    "set": panel_recent_vouches_set,
                    "disable": panel_recent_vouches_disable,
                    "status": panel_recent_vouches_status,
                },
                "completed-deals": {
                    "set": panel_completed_deals_set,
                    "disable": panel_completed_deals_disable,
                    "status": panel_completed_deals_status,
                },
                "middleman-status": {
                    "set": panel_middleman_status_set,
                    "refresh": panel_middleman_status_refresh,
                    "disable": panel_middleman_status_disable,
                    "status": panel_middleman_status_status,
                },
                "active-deals": {
                    "set": panel_active_deals_set,
                    "refresh": panel_active_deals_refresh,
                    "disable": panel_active_deals_disable,
                    "status": panel_active_deals_status,
                },
                "dispute-board": {
                    "set": panel_dispute_board_set,
                    "refresh": panel_dispute_board_refresh,
                    "disable": panel_dispute_board_disable,
                    "status": panel_dispute_board_status,
                },
                "trust-warning": {
                    "set": panel_trust_warning_set,
                    "refresh": panel_trust_warning_refresh,
                    "disable": panel_trust_warning_disable,
                    "status": panel_trust_warning_status,
                },
            }
            if panel_name not in panel_map or panel_cmd not in panel_map[panel_name]:
                await _prefix_send(message, "Command panel tidak dikenal.")
                return
            command = panel_map[panel_name][panel_cmd]
            if panel_cmd == "set":
                if len(args) < 4:
                    await _prefix_send(message, f"Format salah. Gunakan: w!deal panel {panel_name} set #channel")
                    return
                channel = await _prefix_channel(message.guild, args[3])
                if not isinstance(channel, discord.TextChannel):
                    await _prefix_send(message, "Channel tidak valid.")
                    return
                await _run_prefix_command(command, interaction, channel)
                return
            await _run_prefix_command(command, interaction)
            return

        if subcommand == "mm-status":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal mm-status set <available|busy|offline|unavailable> [note] | clear")
                return
            status_cmd = args[1].lower()
            if status_cmd == "set":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal mm-status set <available|busy|offline|unavailable> [note]")
                    return
                note = _join_tail(args[3:]) or None
                await _run_prefix_command(mm_status_set, interaction, args[2], note)
                return
            if status_cmd == "clear":
                await _run_prefix_command(mm_status_clear, interaction)
                return
            await _prefix_send(message, "Command mm-status tidak dikenal.")
            return

        if subcommand == "vouch-review-channel":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal vouch-review-channel set #channel | disable | status")
                return
            review_cmd = args[1].lower()
            if review_cmd == "set":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal vouch-review-channel set #channel")
                    return
                channel = await _prefix_channel(message.guild, args[2])
                if not isinstance(channel, discord.TextChannel):
                    await _prefix_send(message, "Channel tidak valid.")
                    return
                await _run_prefix_command(vouch_review_channel_set, interaction, channel)
                return
            if review_cmd == "disable":
                await _run_prefix_command(vouch_review_channel_disable, interaction)
                return
            if review_cmd == "status":
                await _run_prefix_command(vouch_review_channel_status, interaction)
                return
            await _prefix_send(message, "Command vouch-review-channel tidak dikenal.")
            return

        if subcommand == "vouch-panel":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal vouch-panel setup #channel | disable")
                return
            panel_cmd = args[1].lower()
            if panel_cmd == "setup":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal vouch-panel setup #channel")
                    return
                channel = await _prefix_channel(message.guild, args[2])
                if not isinstance(channel, discord.TextChannel):
                    await _prefix_send(message, "Channel tidak valid.")
                    return
                await _run_prefix_command(vouch_panel_setup, interaction, channel)
                return
            if panel_cmd == "disable":
                await _run_prefix_command(vouch_panel_disable, interaction)
                return
            await _prefix_send(message, "Command vouch-panel tidak dikenal.")
            return

        if subcommand == "scam-report-review-channel":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal scam-report-review-channel set #channel | disable | status")
                return
            review_cmd = args[1].lower()
            if review_cmd == "set":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal scam-report-review-channel set #channel")
                    return
                channel = await _prefix_channel(message.guild, args[2])
                if not isinstance(channel, discord.TextChannel):
                    await _prefix_send(message, "Channel tidak valid.")
                    return
                await _run_prefix_command(scam_report_review_channel_set, interaction, channel)
                return
            if review_cmd == "disable":
                await _run_prefix_command(scam_report_review_channel_disable, interaction)
                return
            if review_cmd == "status":
                await _run_prefix_command(scam_report_review_channel_status, interaction)
                return
            await _prefix_send(message, "Command scam-report-review-channel tidak dikenal.")
            return

        if subcommand == "scam-report-panel":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal scam-report-panel setup #channel | disable | status")
                return
            panel_cmd = args[1].lower()
            if panel_cmd == "setup":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal scam-report-panel setup #channel")
                    return
                channel = await _prefix_channel(message.guild, args[2])
                if not isinstance(channel, discord.TextChannel):
                    await _prefix_send(message, "Channel tidak valid.")
                    return
                await _run_prefix_command(scam_report_panel_setup, interaction, channel)
                return
            if panel_cmd == "disable":
                await _run_prefix_command(scam_report_panel_disable, interaction)
                return
            if panel_cmd == "status":
                await _run_prefix_command(scam_report_panel_status, interaction)
                return
            await _prefix_send(message, "Command scam-report-panel tidak dikenal.")
            return

        if subcommand == "trust-status":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal trust-status view|set|clear @user ...")
                return
            trust_cmd = args[1].lower()
            user = await _prefix_member(message.guild, args[2])
            if not user:
                await _prefix_send(message, "User tidak valid.")
                return
            if trust_cmd == "view":
                await _run_prefix_command(trust_status_view, interaction, user)
                return
            if trust_cmd == "set":
                if len(args) < 5:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal trust-status set @user <clear|under_review|blacklisted> <reason>")
                    return
                await _run_prefix_command(trust_status_set, interaction, user, args[3], _join_tail(args[4:]))
                return
            if trust_cmd == "clear":
                if len(args) < 4:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal trust-status clear @user <reason>")
                    return
                await _run_prefix_command(trust_status_clear, interaction, user, _join_tail(args[3:]))
                return
            await _prefix_send(message, "Command trust-status tidak dikenal.")
            return

        if subcommand == "config":
            if len(args) < 2:
                await _prefix_send(message, "Command ini belum tersedia.")
                return
            config_cmd = args[1].lower()
            if config_cmd == "role":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal config role @role")
                    return
                role = _prefix_role(message.guild, args[2])
                if not role:
                    await _prefix_send(message, "Role tidak valid.")
                    return
                await _run_prefix_command(config_role, interaction, role)
                return
            if config_cmd == "add-role":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal config add-role @role")
                    return
                role = _prefix_role(message.guild, args[2])
                if not role:
                    await _prefix_send(message, "Role tidak valid.")
                    return
                await _run_prefix_command(config_add_role, interaction, role)
                return
            if config_cmd == "remove-role":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal config remove-role @role")
                    return
                role = _prefix_role(message.guild, args[2])
                if not role:
                    await _prefix_send(message, "Role tidak valid.")
                    return
                await _run_prefix_command(config_remove_role, interaction, role)
                return
            if config_cmd == "roles":
                await _run_prefix_command(config_roles, interaction)
                return
            if config_cmd == "log-channel":
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal config log-channel #channel")
                    return
                channel = await _prefix_channel(message.guild, args[2])
                if not isinstance(channel, discord.TextChannel):
                    await _prefix_send(message, "Channel tidak valid.")
                    return
                await _run_prefix_command(config_log_channel, interaction, channel)
                return
            if config_cmd in ("prefix", "id-prefix"):
                if len(args) < 3:
                    await _prefix_send(message, "Format salah. Gunakan: w!deal config prefix <prefix>")
                    return
                await _run_prefix_command(config_prefix, interaction, args[2])
                return
            if config_cmd == "show":
                await _run_prefix_command(config_show, interaction)
                return
            await _prefix_send(message, "Command ini belum tersedia.")
            return

        if subcommand == "info":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal info <deal_id>")
                return
            await _run_prefix_command(deal_info, interaction, args[1])
            return

        if subcommand == "cancel":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal cancel <deal_id> <reason>")
                return
            await _run_prefix_command(deal_cancel, interaction, args[1], _join_tail(args[2:]))
            return

        if subcommand == "dispute":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal dispute <deal_id> <reason> [proof]")
                return
            reason, proof = _tail_with_optional_proof(args[2:])
            await _run_prefix_command(deal_dispute, interaction, args[1], reason, proof)
            return

        if subcommand == "edit":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal edit <deal_id>")
                return
            await _prefix_edit_prompt(interaction, args[1], force=False)
            return

        if subcommand == "list":
            await _run_prefix_command(deal_list, interaction)
            return

        if subcommand == "note":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal note <deal_id> <note>")
                return
            await _run_prefix_command(deal_note, interaction, args[1], _join_tail(args[2:]))
            return

        if subcommand == "resolve-dispute":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal resolve-dispute <deal_id> <resolution>")
                return
            await _run_prefix_command(deal_resolve_dispute, interaction, args[1], _join_tail(args[2:]))
            return

        if subcommand == "force-status":
            if len(args) < 4:
                await _prefix_send(message, "Format salah. Gunakan: w!deal force-status <deal_id> <status> <reason>")
                return
            await _run_prefix_command(deal_force_status, interaction, args[1], args[2], _join_tail(args[3:]))
            return

        if subcommand == "force-edit":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal force-edit <deal_id>")
                return
            await _prefix_edit_prompt(interaction, args[1], force=True)
            return

        if subcommand == "delete-duplicate":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal delete-duplicate <deal_id> <reason>")
                return
            await _run_prefix_command(deal_delete_duplicate, interaction, args[1], _join_tail(args[2:]))
            return

        if subcommand == "vouch":
            if len(args) < 5:
                await _prefix_send(message, "Format salah. Gunakan: w!deal vouch <deal_id> @target <rating> <review>")
                return
            target = await _prefix_member(message.guild, args[2])
            rating = _prefix_int(args[3])
            if not target or rating is None:
                await _prefix_send(message, "Target atau rating tidak valid.")
                return
            review = _join_tail(args[4:])
            await _run_prefix_command(slash_vouch, interaction, args[1], target, rating, review)
            return

        if subcommand == "rep":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal rep @user")
                return
            user = await _prefix_member(message.guild, args[1])
            if not user:
                await _prefix_send(message, "User tidak valid.")
                return
            if not await _require_deal_phase(interaction, 6):
                return
            rep = await recalculate_user_reputation(message.guild.id, user.id)
            latest_vouches = await list_user_vouches(message.guild.id, user.id)
            await interaction.response.send_message(embed=await _reputation_profile_embed(user, rep, latest_vouches, interaction.client))
            return

        if subcommand == "vouches":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal vouches @user")
                return
            user = await _prefix_member(message.guild, args[1])
            if not user:
                await _prefix_send(message, "User tidak valid.")
                return
            await _run_prefix_command(slash_vouches, interaction, user)
            return

        if subcommand == "rank":
            if len(args) < 2:
                await _prefix_send(message, "Format salah. Gunakan: w!deal rank @user")
                return
            user = await _prefix_member(message.guild, args[1])
            if not user:
                await _prefix_send(message, "User tidak valid.")
                return
            await _run_prefix_command(slash_rank, interaction, user)
            return

        if subcommand == "leaderboard":
            await _run_prefix_command(slash_reputation_leaderboard, interaction)
            return

        if subcommand == "removevouch":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal removevouch <vouch_id> <reason>")
                return
            vouch_id = _prefix_int(args[1])
            if vouch_id is None:
                await _prefix_send(message, "Vouch ID tidak valid.")
                return
            await _run_prefix_command(slash_removevouch, interaction, vouch_id, _join_tail(args[2:]))
            return

        if subcommand == "reportvouch":
            if len(args) < 3:
                await _prefix_send(message, "Format salah. Gunakan: w!deal reportvouch <vouch_id> <reason> [proof]")
                return
            vouch_id = _prefix_int(args[1])
            if vouch_id is None:
                await _prefix_send(message, "Vouch ID tidak valid.")
                return
            reason, proof = _tail_with_optional_proof(args[2:])
            await _run_prefix_command(slash_reportvouch, interaction, vouch_id, reason, proof)
            return

        await _prefix_send(message, "Command ini belum tersedia.")

    @deal_group.command(name="start", description="Mulai middleman deal di channel saat ini")
    async def deal_start(interaction: discord.Interaction, buyer: discord.Member, seller: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return

        config = await get_deal_config(interaction.guild.id)
        if not member_has_deal_role(interaction.user, config):
            await interaction.response.send_message("Hanya role Middleman, Miserator, atau deal staff yang dikonfigurasi yang bisa menjalankan command ini.", ephemeral=True)
            return
        if buyer.id == seller.id:
            await interaction.response.send_message("Buyer dan seller tidak boleh sama.", ephemeral=True)
            return
        if interaction.user.id in (buyer.id, seller.id):
            await interaction.response.send_message("Middleman tidak boleh sama dengan buyer atau seller.", ephemeral=True)
            return

        bot_member = interaction.guild.me or interaction.guild.get_member(client.user.id)
        bot_perms = interaction.channel.permissions_for(bot_member)
        if not (bot_perms.view_channel and bot_perms.send_messages and bot_perms.read_message_history and bot_perms.manage_channels):
            await interaction.response.send_message(
                "Bot tidak punya permission untuk menambahkan user ke channel ini. Berikan permission Manage Channels ke bot.",
                ephemeral=True,
            )
            return

        active = await find_active_deal_for_channel(interaction.guild.id, interaction.channel.id)
        if active:
            await interaction.response.send_message(
                f"Channel ini sudah punya deal aktif dengan status `{active['status']}`.",
                ephemeral=True,
            )
            return

        trust_safety = await _check_deal_start_trust_safety(interaction, buyer, seller, config)
        if not trust_safety.get("allowed"):
            await interaction.response.send_message(trust_safety["message"], ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            for member in (buyer, seller, interaction.user):
                await patch_deal_channel_permissions(
                    interaction.channel,
                    member,
                    reason=f"Middleman deal access by {interaction.user} ({interaction.user.id})",
                )
        except discord.Forbidden:
            await interaction.followup.send(
                "Bot tidak punya permission untuk menambahkan user ke channel ini. Berikan permission Manage Channels ke bot.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send("Gagal menambahkan user ke channel ini. Coba lagi nanti.", ephemeral=True)
            return

        deal = await create_pending_deal(
            interaction.guild.id,
            interaction.channel.id,
            interaction.user.id,
            buyer.id,
            seller.id,
            interaction.user.id,
        )
        if not deal:
            await interaction.followup.send("Channel ini sudah punya deal aktif.", ephemeral=True)
            return

        msg = await interaction.followup.send(embed=await _warning_embed(deal, interaction.guild, interaction.client), view=DealStartView(deal), wait=True)
        await set_deal_warning_message(deal["id"], msg.id)
        under_review = trust_safety.get("under_review") or []
        if under_review:
            try:
                await interaction.channel.send(embed=_under_review_deal_start_embed(interaction, buyer, seller, trust_safety["statuses"]))
            except discord.HTTPException:
                pass
            await _audit_deal_start_trust_event(
                interaction,
                "Under Review Deal Start Override",
                under_review,
                deal=deal,
                status="under_review",
            )

    @deal_group.command(name="add-user", description="Tambahkan user ke channel deal")
    async def deal_add_user(interaction: discord.Interaction, deal_id: str, user: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.followup.send("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if str(interaction.channel.id) != str(deal["ticketChannelId"]):
            await interaction.followup.send("Command ini hanya bisa digunakan di channel deal yang sesuai.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id)
        if not await _can_manage_deal(interaction, deal=deal, config=config):
            await interaction.followup.send("Hanya middleman atau staff yang bisa menambahkan user ke deal.", ephemeral=True)
            return
        bot_member = interaction.guild.me or interaction.guild.get_member(client.user.id)
        if not interaction.channel.permissions_for(bot_member).manage_channels:
            await interaction.followup.send(
                "Bot tidak punya permission untuk menambahkan user ke channel ini. Berikan permission Manage Channels ke bot.",
                ephemeral=True,
            )
            return
        try:
            await patch_deal_channel_permissions(
                interaction.channel,
                user,
                reason=f"Middleman deal add-user by {interaction.user} ({interaction.user.id})",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Bot tidak punya permission untuk menambahkan user ke channel ini. Berikan permission Manage Channels ke bot.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send("Gagal menambahkan user ke channel ini. Coba lagi nanti.", ephemeral=True)
            return
        await write_audit("deal_add_user", deal["id"], f"dealId={deal['dealId']}, added={user.id}, by={interaction.user.id}", source="deal")
        await interaction.followup.send(f"✅ {user.mention} berhasil ditambahkan ke channel deal `{deal['dealId']}`.", ephemeral=True)

    @deal_group.command(name="edit", description="Edit detail deal sebelum Dana Masuk")
    async def deal_edit(interaction: discord.Interaction, deal_id: str):
        if not await _require_deal_phase(interaction, 4):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _require_matching_deal_channel(interaction, deal):
            return
        if not (_is_participant(interaction, deal) or await _can_manage_deal(interaction, deal=deal)):
            await interaction.response.send_message(
                "Kamu tidak memiliki akses untuk mengedit deal ini. Hanya buyer, seller, dan middleman yang bisa mengedit.",
                ephemeral=True,
            )
            return
        if deal["status"] != DEAL_STATUS_WAITING_FUNDS:
            await interaction.response.send_message("Deal hanya bisa diedit sebelum Dana Masuk.", ephemeral=True)
            return
        await interaction.response.send_modal(EditDealModal(deal))

    @deal_group.command(name="cancel", description="Cancel deal dengan alasan")
    async def deal_cancel(interaction: discord.Interaction, deal_id: str, reason: str):
        if not await _require_deal_phase(interaction, 2):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _require_matching_deal_channel(interaction, deal):
            return
        if await _block_if_disputed(interaction, deal):
            return
        is_manager = await _can_manage_deal(interaction, deal=deal)
        is_part = _is_participant(interaction, deal)

        if is_manager or is_part:
            is_pre_payment = deal.get("status") in (DEAL_STATUS_PENDING_FORM, DEAL_STATUS_WAITING_FUNDS)
            if is_manager or is_pre_payment:
                lock_key = _acquire_action_lock("deal_cancel", interaction.guild.id, deal["id"], interaction.user.id)
                if not lock_key:
                    await _send_lock_collision_audit(interaction, "deal_cancel", deal["id"])
                    await _safe_respond(interaction, "Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
                    return
                try:
                    cancelled, error = await cancel_deal(deal["id"], interaction.user.id, reason)
                    if error:
                        await _send_abuse_guard_audit(interaction.guild, "Critical Action Duplicate Blocked", actor=interaction.user, note=f"deal_cancel:{deal['id']}")
                        await _safe_respond(interaction, "Deal ini tidak bisa dibatalkan.", ephemeral=True)
                        return
                    _clear_deal_upload_sessions(deal["id"])
                    await _safe_respond(interaction, embed=await _cancel_embed(cancelled, interaction.guild, interaction.client), ephemeral=False)
                    await send_deal_audit_log(
                        interaction.guild,
                        "Deal Cancelled",
                        actor=interaction.user,
                        target=await _deal_audit_target(cancelled, interaction.guild, interaction.client),
                        deal_id=cancelled.get("dealId"),
                        reason=reason,
                    )
                finally:
                    _release_action_lock(lock_key)
                return
            else:
                config = await get_deal_config(interaction.guild.id)
                if not config.get("allowUserCancelRequest", True):
                    await _safe_respond(interaction, "Pengajuan pembatalan oleh user dinonaktifkan di server ini. Silakan hubungi staff/middleman.", ephemeral=True)
                    return

                if deal["status"] in (DEAL_STATUS_COMPLETED, "Cancelled", "Voided/Duplicate"):
                    await _safe_respond(interaction, "Deal ini tidak bisa dibatalkan.", ephemeral=True)
                    return

                lock_key = _acquire_action_lock("deal_cancel_request", interaction.guild.id, deal["id"], interaction.user.id)
                if not lock_key:
                    await _send_lock_collision_audit(interaction, "deal_cancel_request", deal["id"])
                    await _safe_respond(interaction, "Action ini sedang diproses. Coba lagi sebentar.", ephemeral=True)
                    return
                try:
                    requested, error = await request_deal_cancel(deal["id"], interaction.user.id, reason)
                    if error:
                        await _safe_respond(interaction, "Gagal mengajukan pembatalan deal.", ephemeral=True)
                        return
                    await _safe_respond(interaction, f"✅ Permintaan pembatalan deal `{deal['dealId']}` telah diajukan. Menunggu konfirmasi dari staff atau middleman.", ephemeral=False)
                finally:
                    _release_action_lock(lock_key)
                return
        await _safe_respond(interaction, "Kamu tidak punya akses untuk cancel deal ini.", ephemeral=True)


    @deal_group.command(name="dispute", description="Buka dispute untuk deal")
    async def deal_dispute(interaction: discord.Interaction, deal_id: str, reason: str, proof: str = None):
        if not await _require_deal_phase(interaction, 2):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _require_matching_deal_channel(interaction, deal):
            return
        if deal.get("status") == DEAL_STATUS_DISPUTED:
            await interaction.response.send_message("Action ini sudah diproses.", ephemeral=True)
            return
        if not await _can_open_dispute(interaction, deal):
            await interaction.response.send_message(DISPUTE_OPEN_STAFF_ONLY_MESSAGE, ephemeral=True)
            return
        disputed, error = await dispute_deal(deal["id"], interaction.user.id, reason, None)
        if error:
            await interaction.response.send_message("Deal ini tidak bisa dibuat dispute.", ephemeral=True)
            return
        _clear_deal_upload_sessions(deal["id"])
        await interaction.response.send_message(
            "Jika ada bukti tambahan, silakan kirim screenshot/gambar langsung di channel ini.",
            embed=await _dispute_embed(disputed, interaction.guild, interaction.client),
            view=DisputeActionView(disputed["id"]),
        )
        await _ping_staff_for_dispute(interaction, disputed)
        await send_deal_audit_log(
            interaction.guild,
            "Dispute Opened",
            actor=interaction.user,
            target=await _deal_audit_target(disputed, interaction.guild, interaction.client),
            deal_id=disputed.get("dealId"),
            reason=reason,
        )

    @deal_group.command(name="resolve-dispute", description="Resolve dispute deal")
    async def deal_resolve_dispute(interaction: discord.Interaction, deal_id: str, resolution: str):
        if not await _require_deal_phase(interaction, 4):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _require_matching_deal_channel(interaction, deal):
            return
        if not await _can_manage_deal(interaction, deal=deal):
            await interaction.response.send_message("Kamu tidak punya permission untuk menyelesaikan dispute ini.", ephemeral=True)
            return
        resolved, error = await resolve_deal_dispute(deal["id"], interaction.user.id, resolution)
        if error == "missing_previous_status":
            await interaction.response.send_message("Status sebelum dispute tidak aman untuk dipulihkan. Gunakan force-status.", ephemeral=True)
            return
        if error:
            await interaction.response.send_message("Deal ini tidak berada dalam status Disputed.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=await _dispute_resolved_embed(resolved, resolution, interaction.guild, interaction.client),
            view=_view_for_deal_status(resolved),
        )
        await send_deal_audit_log(
            interaction.guild,
            "Dispute Resolved",
            actor=interaction.user,
            target=await _deal_audit_target(resolved, interaction.guild, interaction.client),
            deal_id=resolved.get("dealId"),
            note=resolution,
            metadata={"status": resolved.get("status")},
        )

    @deal_group.command(name="info", description="Lihat info dan timeline deal")
    async def deal_info(interaction: discord.Interaction, deal_id: str):
        if not await _require_deal_phase(interaction, 2):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _require_matching_deal_channel(interaction, deal):
            return
        if not (_is_participant(interaction, deal) or await _can_manage_deal(interaction, deal=deal)):
            await interaction.response.send_message("Kamu tidak punya akses melihat deal ini.", ephemeral=True)
            return
        show_notes = await _can_manage_deal(interaction, deal=deal)
        await interaction.response.send_message(embed=await _deal_info_embed(deal, show_notes=show_notes, guild=interaction.guild, bot=interaction.client), ephemeral=True)

    @deal_group.command(name="list", description="Lihat semua deal aktif")
    async def deal_list(interaction: discord.Interaction):
        if not await _require_deal_phase(interaction, 4):
            return
        config = await get_deal_config(interaction.guild.id)
        if not member_has_deal_role(interaction.user, config) and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Hanya staff yang bisa melihat daftar deal aktif.", ephemeral=True)
            return
        deals = await list_active_deals(interaction.guild.id)
        view = DealListView(deals)
        await interaction.response.send_message(embed=await view.embed(interaction.guild, interaction.client), view=view, ephemeral=True)

    @deal_group.command(name="note", description="Tambah internal note untuk deal")
    async def deal_note(interaction: discord.Interaction, deal_id: str, note: str):
        if not await _require_deal_phase(interaction, 4):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _require_matching_deal_channel(interaction, deal):
            return
        if not await _can_manage_deal(interaction, deal=deal):
            await interaction.response.send_message("Hanya staff/middleman yang bisa menambah internal note.", ephemeral=True)
            return
        _note_id, error = await add_deal_note(interaction.guild.id, deal["dealId"], interaction.user.id, note)
        if error:
            await interaction.response.send_message("Note tidak boleh kosong.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Internal note ditambahkan untuk deal `{deal['dealId']}`.", ephemeral=True)

    @deal_group.command(name="force-status", description="Admin override status deal")
    async def deal_force_status(interaction: discord.Interaction, deal_id: str, status: str, reason: str):
        if not await _require_deal_phase(interaction, 4):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _can_admin_override(interaction):
            await interaction.response.send_message("Hanya admin atau owner role yang bisa memakai override.", ephemeral=True)
            return
        updated, error = await force_deal_status(deal["id"], interaction.user.id, status, reason)
        if error:
            await interaction.response.send_message("Force status gagal. Status dan reason wajib diisi.", ephemeral=True)
            return
        if _is_terminal_deal_status(updated.get("status")):
            _clear_deal_upload_sessions(deal["id"])
        await interaction.response.send_message(
            f"✅ Override berhasil: deal `{updated['dealId']}` dipaksa ke status `{updated['status']}`.",
            ephemeral=True,
        )

    @deal_group.command(name="force-edit", description="Admin override edit deal")
    async def deal_force_edit(interaction: discord.Interaction, deal_id: str):
        if not await _require_deal_phase(interaction, 4):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _can_admin_override(interaction):
            await interaction.response.send_message("Hanya admin atau owner role yang bisa memakai override.", ephemeral=True)
            return
        await interaction.response.send_modal(EditDealModal(deal, force=True))

    @deal_group.command(name="delete-duplicate", description="Tandai deal duplicate sebagai void")
    async def deal_delete_duplicate(interaction: discord.Interaction, deal_id: str, reason: str):
        if not await _require_deal_phase(interaction, 4):
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        if not await _can_admin_override(interaction):
            await interaction.response.send_message("Hanya admin atau owner role yang bisa memakai override.", ephemeral=True)
            return
        updated, error = await mark_deal_void_duplicate(deal["id"], interaction.user.id, reason)
        if error:
            await interaction.response.send_message("Reason wajib diisi.", ephemeral=True)
            return
        _clear_deal_upload_sessions(deal["id"])
        await interaction.response.send_message(
            f"✅ Override berhasil: deal `{updated['dealId']}` ditandai sebagai `Voided/Duplicate`.",
            ephemeral=True,
        )

    async def _send_or_update_manual_vouch_panel(guild, channel):
        config = await get_manual_vouch_panel_config(guild.id)
        embed = _manual_vouch_panel_embed()
        view = ManualVouchPanelView()
        if config and config.get("messageId") and str(config.get("channelId")) == str(channel.id):
            try:
                old_message = await channel.fetch_message(int(config["messageId"]))
                await old_message.edit(embed=embed, view=view)
                await set_manual_vouch_panel_config(guild.id, channel.id, old_message.id, enabled=True)
                return old_message
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                pass
        message = await channel.send(embed=embed, view=view)
        await set_manual_vouch_panel_config(guild.id, channel.id, message.id, enabled=True)
        return message

    async def _send_or_update_scam_report_panel(guild, channel):
        config = await get_scam_report_panel_config(guild.id)
        embed = _scam_report_panel_embed()
        view = ScamReportPanelView()
        if config and config.get("messageId") and str(config.get("channelId")) == str(channel.id):
            try:
                old_message = await channel.fetch_message(int(config["messageId"]))
                await old_message.edit(embed=embed, view=view)
                await set_scam_report_panel_config(guild.id, channel.id, old_message.id, enabled=True)
                return old_message
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                pass
        message = await channel.send(embed=embed, view=view)
        await set_scam_report_panel_config(guild.id, channel.id, message.id, enabled=True)
        return message

    @scam_review_group.command(name="set", description="Atur channel review report scammer")
    async def scam_report_review_channel_set(interaction: discord.Interaction, channel: discord.TextChannel):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur review report scammer.", ephemeral=True)
            return
        await set_scam_report_review_config(interaction.guild.id, channel.id, enabled=True)
        await interaction.response.send_message("Channel review report scammer berhasil diatur.", ephemeral=True)
        await send_deal_audit_log(interaction.guild, "Scam Report Review Channel Configured", actor=interaction.user, target=channel)

    @scam_review_group.command(name="disable", description="Nonaktifkan channel review report scammer")
    async def scam_report_review_channel_disable(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur review report scammer.", ephemeral=True)
            return
        await disable_scam_report_review_config(interaction.guild.id)
        await interaction.response.send_message("Channel review report scammer berhasil dinonaktifkan.", ephemeral=True)

    @scam_review_group.command(name="status", description="Lihat status channel review report scammer")
    async def scam_report_review_channel_status(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur review report scammer.", ephemeral=True)
            return
        config = await get_scam_report_review_config(interaction.guild.id)
        enabled = bool(config and config.get("enabled"))
        channel_value = "-"
        if config and config.get("reviewChannelId"):
            try:
                channel = interaction.guild.get_channel(int(config["reviewChannelId"]))
                channel_value = channel.mention if channel else f"Channel tidak ditemukan ({config['reviewChannelId']})"
            except (TypeError, ValueError):
                channel_value = "Channel tidak valid"
        await interaction.response.send_message(
            f"Review report scammer: **{'aktif' if enabled else 'nonaktif'}**\nChannel: {channel_value}",
            ephemeral=True,
        )

    @scam_panel_group.command(name="setup", description="Kirim panel publik report scammer")
    async def scam_report_panel_setup(interaction: discord.Interaction, channel: discord.TextChannel):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur panel report scammer.", ephemeral=True)
            return
        await _send_or_update_scam_report_panel(interaction.guild, channel)
        await interaction.response.send_message("Panel report scammer berhasil diatur.", ephemeral=True)
        await send_deal_audit_log(interaction.guild, "Scam Report Panel Configured", actor=interaction.user, target=channel)

    @scam_panel_group.command(name="disable", description="Nonaktifkan panel publik report scammer")
    async def scam_report_panel_disable(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur panel report scammer.", ephemeral=True)
            return
        await disable_scam_report_panel_config(interaction.guild.id)
        await interaction.response.send_message("Panel report scammer berhasil dinonaktifkan.", ephemeral=True)

    @scam_panel_group.command(name="status", description="Lihat status panel report scammer")
    async def scam_report_panel_status(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur panel report scammer.", ephemeral=True)
            return
        config = await get_scam_report_panel_config(interaction.guild.id)
        enabled = bool(config and config.get("enabled"))
        channel_value = "-"
        if config and config.get("channelId"):
            try:
                channel = interaction.guild.get_channel(int(config["channelId"]))
                channel_value = channel.mention if channel else f"Channel tidak ditemukan ({config['channelId']})"
            except (TypeError, ValueError):
                channel_value = "Channel tidak valid"
        await interaction.response.send_message(
            f"Panel report scammer: **{'aktif' if enabled else 'nonaktif'}**\nChannel: {channel_value}\nMessage ID: {config.get('messageId') if config else '-'}",
            ephemeral=True,
        )

    async def _trust_status_embed(guild, bot, user, status_row):
        embed = discord.Embed(title="🛡️ Trust Status", color=0x5865F2)
        embed.add_field(name="User", value=await format_user_display(bot, guild, user.id), inline=False)
        embed.add_field(name="Status", value=status_row.get("status") or "clear", inline=True)
        embed.add_field(name="Reason", value=truncate_review(status_row.get("reason") or "-", 250), inline=False)
        source = f"{status_row.get('sourceType') or '-'} #{status_row.get('sourceId') or '-'}"
        embed.add_field(name="Source", value=source, inline=True)
        embed.add_field(name="Updated By", value=await format_user_display(bot, guild, status_row.get("updatedById")), inline=True)
        embed.add_field(name="Updated At", value=format_discord_timestamp(status_row.get("updatedAt"), "f"), inline=True)
        return embed

    @trust_status_group.command(name="view", description="Lihat trust moderation status user")
    async def trust_status_view(interaction: discord.Interaction, user: discord.Member):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur trust status.", ephemeral=True)
            return
        status_row = await get_trust_moderation_status(interaction.guild.id, user.id)
        await interaction.response.send_message(embed=await _trust_status_embed(interaction.guild, interaction.client, user, status_row), ephemeral=True)

    @trust_status_group.command(name="set", description="Set trust moderation status user")
    async def trust_status_set(interaction: discord.Interaction, user: discord.Member, status: str, reason: str):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur trust status.", ephemeral=True)
            return
        updated, error = await set_trust_moderation_status(interaction.guild.id, user.id, status, reason, interaction.user.id, "manual", None)
        if error == "invalid_status":
            await interaction.response.send_message("Status harus clear, under_review, atau blacklisted.", ephemeral=True)
            return
        if error:
            await interaction.response.send_message("Reason wajib diisi.", ephemeral=True)
            return
        await recalculate_user_reputation(interaction.guild.id, user.id)
        await interaction.response.send_message(embed=await _trust_status_embed(interaction.guild, interaction.client, user, updated), ephemeral=True)
        await send_deal_audit_log(interaction.guild, "Trust Status Updated", actor=interaction.user, target=user, reason=reason, metadata={"status": status})

    @trust_status_group.command(name="clear", description="Clear trust moderation status user")
    async def trust_status_clear(interaction: discord.Interaction, user: discord.Member, reason: str):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur trust status.", ephemeral=True)
            return
        updated, error = await set_trust_moderation_status(interaction.guild.id, user.id, "clear", reason, interaction.user.id, "manual", None)
        if error:
            await interaction.response.send_message("Reason wajib diisi.", ephemeral=True)
            return
        await recalculate_user_reputation(interaction.guild.id, user.id)
        await interaction.response.send_message(embed=await _trust_status_embed(interaction.guild, interaction.client, user, updated), ephemeral=True)
        await send_deal_audit_log(interaction.guild, "Trust Status Updated", actor=interaction.user, target=user, reason=reason, metadata={"status": "clear"})

    @archive_group.command(name="info", description="Lihat archive aman untuk deal final")
    async def deal_archive_info(interaction: discord.Interaction, deal_id: str):
        archive = await get_deal_archive(interaction.guild.id, deal_id)
        if not archive:
            await interaction.response.send_message("Archive deal tidak ditemukan.", ephemeral=True)
            return
        is_participant = (
            str(interaction.user.id) in (
                str(archive.get("buyerId")),
                str(archive.get("sellerId")),
                str(archive.get("middlemanId"))
            )
        )
        if not (is_participant or await _can_configure_audit_log(interaction)):
            await interaction.response.send_message("Kamu tidak punya permission untuk melihat archive deal.", ephemeral=True)
            return
        await _send_archive_embed_response(interaction, await _deal_archive_embed(archive, interaction.guild, interaction.client))

    @archive_group.command(name="search", description="Cari archive aman berdasarkan user")
    async def deal_archive_search(interaction: discord.Interaction, user: discord.Member):
        if not (user.id == interaction.user.id or await _can_configure_audit_log(interaction)):
            await interaction.response.send_message("Kamu tidak punya permission untuk melihat archive deal user lain.", ephemeral=True)
            return
        archives = await search_deal_archives_for_user(interaction.guild.id, user.id, limit=10)
        embed = await _deal_archive_list_embed(f"🧾 Deal Archive Search — {user.display_name}", archives, interaction.guild, interaction.client)
        await _send_archive_embed_response(interaction, embed)

    @archive_group.command(name="recent", description="Lihat archive deal terbaru")
    async def deal_archive_recent(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk melihat archive deal.", ephemeral=True)
            return
        archives = await list_recent_deal_archives(interaction.guild.id, limit=10)
        embed = await _deal_archive_list_embed("🧾 Recent Deal Archives", archives, interaction.guild, interaction.client)
        await _send_archive_embed_response(interaction, embed)

    @archive_group.command(name="backfill", description="Backfill archive aman untuk deal final lama")
    async def deal_archive_backfill(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk melihat archive deal.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        created, skipped = await backfill_deal_archives(interaction.guild.id, interaction.user.id)
        await interaction.followup.send(f"Archive backfill selesai. Created: {created}, Skipped: {skipped}.", ephemeral=True)

    async def _panel_require_staff(interaction):
        if await _can_configure_audit_log(interaction):
            return True
        await interaction.response.send_message("Kamu tidak punya permission untuk mengatur panel trust.", ephemeral=True)
        return False

    async def _panel_set(interaction, panel_type, channel):
        if not await _panel_require_staff(interaction):
            return
        _result, status = await setup_deal_panel(interaction.guild, panel_type, channel)
        await interaction.response.send_message(
            f"Panel trust `{DEAL_PANEL_LABELS.get(panel_type, panel_type)}` berhasil diatur ke {channel.mention}.",
            ephemeral=True,
        )
        await send_deal_audit_log(
            interaction.guild,
            "Trust Panel Configured",
            actor=interaction.user,
            target=channel,
            note=DEAL_PANEL_LABELS.get(panel_type, panel_type),
            metadata={"status": status},
        )

    async def _panel_refresh(interaction, panel_type):
        if not await _panel_require_staff(interaction):
            return
        message, status = await refresh_deal_panel(interaction.guild, panel_type, force=True)
        if not message and status in ("disabled", "missing_channel"):
            await interaction.response.send_message("Panel belum aktif atau channel tidak ditemukan.", ephemeral=True)
            return
        await interaction.response.send_message(f"Panel trust berhasil direfresh. Status: `{status}`.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Trust Panel Manual Refresh",
            actor=interaction.user,
            note=DEAL_PANEL_LABELS.get(panel_type, panel_type),
            metadata={"status": status},
        )

    async def _panel_disable(interaction, panel_type):
        if not await _panel_require_staff(interaction):
            return
        await disable_deal_panel_config(interaction.guild.id, panel_type)
        await interaction.response.send_message(f"Panel trust `{DEAL_PANEL_LABELS.get(panel_type, panel_type)}` dinonaktifkan.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Trust Panel Disabled",
            actor=interaction.user,
            note=DEAL_PANEL_LABELS.get(panel_type, panel_type),
            metadata={"status": "disabled"},
        )

    async def _panel_status(interaction, panel_type):
        if not await _panel_require_staff(interaction):
            return
        config = await get_deal_panel_config(interaction.guild.id, panel_type)
        enabled = bool(config and config.get("enabled"))
        channel_value = "-"
        if config and config.get("channelId"):
            try:
                channel = interaction.guild.get_channel(int(config["channelId"]))
                channel_value = channel.mention if channel else f"Channel tidak ditemukan ({config['channelId']})"
            except (TypeError, ValueError):
                channel_value = "Channel tidak valid"
        message_id = config.get("messageId") if config else "-"
        await interaction.response.send_message(
            f"{DEAL_PANEL_LABELS.get(panel_type, panel_type)}: **{'aktif' if enabled else 'nonaktif'}**\n"
            f"Channel: {channel_value}\nMessage ID: {message_id or '-'}",
            ephemeral=True,
        )

    async def _staff_panel_require_staff(interaction):
        if await _can_configure_audit_log(interaction):
            return True
        await interaction.response.send_message("Kamu tidak punya permission untuk mengatur panel staff.", ephemeral=True)
        return False

    async def _staff_panel_set(interaction, panel_type, channel):
        if not await _staff_panel_require_staff(interaction):
            return
        _result, status = await setup_deal_panel(interaction.guild, panel_type, channel)
        await interaction.response.send_message(
            f"Panel staff `{DEAL_PANEL_LABELS.get(panel_type, panel_type)}` berhasil diatur ke {channel.mention}.",
            ephemeral=True,
        )
        await send_deal_audit_log(
            interaction.guild,
            "Staff Operation Panel Configured",
            actor=interaction.user,
            target=channel,
            note=DEAL_PANEL_LABELS.get(panel_type, panel_type),
            metadata={"status": status},
        )

    async def _staff_panel_refresh(interaction, panel_type):
        if not await _staff_panel_require_staff(interaction):
            return
        message, status = await refresh_deal_panel(interaction.guild, panel_type, force=True)
        if not message and status in ("disabled", "missing_channel"):
            await interaction.response.send_message("Panel belum aktif atau channel tidak ditemukan.", ephemeral=True)
            return
        await interaction.response.send_message(f"Panel staff berhasil direfresh. Status: `{status}`.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Staff Operation Panel Manual Refresh",
            actor=interaction.user,
            note=DEAL_PANEL_LABELS.get(panel_type, panel_type),
            metadata={"status": status},
        )

    async def _staff_panel_disable(interaction, panel_type):
        if not await _staff_panel_require_staff(interaction):
            return
        await disable_deal_panel_config(interaction.guild.id, panel_type)
        await interaction.response.send_message(f"Panel staff `{DEAL_PANEL_LABELS.get(panel_type, panel_type)}` dinonaktifkan.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Staff Operation Panel Disabled",
            actor=interaction.user,
            note=DEAL_PANEL_LABELS.get(panel_type, panel_type),
            metadata={"status": "disabled"},
        )

    async def _staff_panel_status(interaction, panel_type):
        if not await _staff_panel_require_staff(interaction):
            return
        config = await get_deal_panel_config(interaction.guild.id, panel_type)
        enabled = bool(config and config.get("enabled"))
        channel_value = "-"
        if config and config.get("channelId"):
            try:
                channel = interaction.guild.get_channel(int(config["channelId"]))
                channel_value = channel.mention if channel else f"Channel tidak ditemukan ({config['channelId']})"
            except (TypeError, ValueError):
                channel_value = "Channel tidak valid"
        message_id = config.get("messageId") if config else "-"
        await interaction.response.send_message(
            f"{DEAL_PANEL_LABELS.get(panel_type, panel_type)}: **{'aktif' if enabled else 'nonaktif'}**\n"
            f"Channel: {channel_value}\nMessage ID: {message_id or '-'}",
            ephemeral=True,
        )

    @panel_group.command(name="leaderboard-set", description="Atur channel Trusted Vouch Leaderboard")
    async def panel_leaderboard_set(interaction: discord.Interaction, channel: discord.TextChannel):
        await _panel_set(interaction, "vouch_leaderboard", channel)

    async def panel_leaderboard_refresh(interaction: discord.Interaction):
        await _panel_refresh(interaction, "vouch_leaderboard")

    async def panel_leaderboard_disable(interaction: discord.Interaction):
        await _panel_disable(interaction, "vouch_leaderboard")

    @panel_group.command(name="leaderboard-status", description="Lihat status Trusted Vouch Leaderboard")
    async def panel_leaderboard_status(interaction: discord.Interaction):
        await _panel_status(interaction, "vouch_leaderboard")

    @panel_group.command(name="stats-set", description="Atur channel Server Trust Stats")
    async def panel_stats_set(interaction: discord.Interaction, channel: discord.TextChannel):
        await _panel_set(interaction, "trust_stats", channel)

    async def panel_stats_refresh(interaction: discord.Interaction):
        await _panel_refresh(interaction, "trust_stats")

    async def panel_stats_disable(interaction: discord.Interaction):
        await _panel_disable(interaction, "trust_stats")

    @panel_group.command(name="stats-status", description="Lihat status Server Trust Stats")
    async def panel_stats_status(interaction: discord.Interaction):
        await _panel_status(interaction, "trust_stats")

    @panel_group.command(name="recent-vouches-set", description="Atur channel Recent Vouches feed")
    async def panel_recent_vouches_set(interaction: discord.Interaction, channel: discord.TextChannel):
        await _panel_set(interaction, "recent_vouches", channel)

    async def panel_recent_vouches_disable(interaction: discord.Interaction):
        await _panel_disable(interaction, "recent_vouches")

    @panel_group.command(name="recent-vouches-status", description="Lihat status Recent Vouches feed")
    async def panel_recent_vouches_status(interaction: discord.Interaction):
        await _panel_status(interaction, "recent_vouches")

    @panel_group.command(name="completed-deals-set", description="Atur channel Completed Deals feed")
    async def panel_completed_deals_set(interaction: discord.Interaction, channel: discord.TextChannel):
        await _panel_set(interaction, "completed_deals", channel)

    async def panel_completed_deals_disable(interaction: discord.Interaction):
        await _panel_disable(interaction, "completed_deals")

    @panel_group.command(name="completed-deals-status", description="Lihat status Completed Deals feed")
    async def panel_completed_deals_status(interaction: discord.Interaction):
        await _panel_status(interaction, "completed_deals")

    @panel_group.command(name="middleman-status-set", description="Atur channel Middleman Status Panel")
    async def panel_middleman_status_set(interaction: discord.Interaction, channel: discord.TextChannel):
        await _staff_panel_set(interaction, "middleman_status", channel)

    async def panel_middleman_status_refresh(interaction: discord.Interaction):
        await _staff_panel_refresh(interaction, "middleman_status")

    async def panel_middleman_status_disable(interaction: discord.Interaction):
        await _staff_panel_disable(interaction, "middleman_status")

    @panel_group.command(name="middleman-status-status", description="Lihat status Middleman Status Panel")
    async def panel_middleman_status_status(interaction: discord.Interaction):
        await _staff_panel_status(interaction, "middleman_status")

    @panel_group.command(name="active-deals-set", description="Atur channel Active Deal Queue")
    async def panel_active_deals_set(interaction: discord.Interaction, channel: discord.TextChannel):
        await _staff_panel_set(interaction, "active_deals", channel)

    async def panel_active_deals_refresh(interaction: discord.Interaction):
        await _staff_panel_refresh(interaction, "active_deals")

    async def panel_active_deals_disable(interaction: discord.Interaction):
        await _staff_panel_disable(interaction, "active_deals")

    @panel_group.command(name="active-deals-status", description="Lihat status Active Deal Queue")
    async def panel_active_deals_status(interaction: discord.Interaction):
        await _staff_panel_status(interaction, "active_deals")

    @panel_group.command(name="dispute-board-set", description="Atur channel Dispute Board")
    async def panel_dispute_board_set(interaction: discord.Interaction, channel: discord.TextChannel):
        await _staff_panel_set(interaction, "dispute_board", channel)

    async def panel_dispute_board_refresh(interaction: discord.Interaction):
        await _staff_panel_refresh(interaction, "dispute_board")

    async def panel_dispute_board_disable(interaction: discord.Interaction):
        await _staff_panel_disable(interaction, "dispute_board")

    @panel_group.command(name="dispute-board-status", description="Lihat status Dispute Board")
    async def panel_dispute_board_status(interaction: discord.Interaction):
        await _staff_panel_status(interaction, "dispute_board")

    @panel_group.command(name="trust-warning-set", description="Atur channel Trust Warning / Report Panel")
    async def panel_trust_warning_set(interaction: discord.Interaction, channel: discord.TextChannel):
        await _staff_panel_set(interaction, "trust_warning", channel)

    async def panel_trust_warning_refresh(interaction: discord.Interaction):
        await _staff_panel_refresh(interaction, "trust_warning")

    async def panel_trust_warning_disable(interaction: discord.Interaction):
        await _staff_panel_disable(interaction, "trust_warning")

    @panel_group.command(name="trust-warning-status", description="Lihat status Trust Warning / Report Panel")
    async def panel_trust_warning_status(interaction: discord.Interaction):
        await _staff_panel_status(interaction, "trust_warning")

    PANEL_REFRESH_CHOICES = [
        app_commands.Choice(name="leaderboard", value="vouch_leaderboard"),
        app_commands.Choice(name="stats", value="trust_stats"),
        app_commands.Choice(name="middleman-status", value="middleman_status"),
        app_commands.Choice(name="active-deals", value="active_deals"),
        app_commands.Choice(name="dispute-board", value="dispute_board"),
        app_commands.Choice(name="trust-warning", value="trust_warning"),
    ]
    PANEL_DISABLE_CHOICES = [
        app_commands.Choice(name="leaderboard", value="vouch_leaderboard"),
        app_commands.Choice(name="stats", value="trust_stats"),
        app_commands.Choice(name="recent-vouches", value="recent_vouches"),
        app_commands.Choice(name="completed-deals", value="completed_deals"),
        app_commands.Choice(name="middleman-status", value="middleman_status"),
        app_commands.Choice(name="active-deals", value="active_deals"),
        app_commands.Choice(name="dispute-board", value="dispute_board"),
        app_commands.Choice(name="trust-warning", value="trust_warning"),
    ]

    async def _panel_refresh_by_type(interaction: discord.Interaction, panel_type: str):
        if panel_type in STAFF_OPERATION_PANEL_TYPES:
            await _staff_panel_refresh(interaction, panel_type)
            return
        await _panel_refresh(interaction, panel_type)

    async def _panel_disable_by_type(interaction: discord.Interaction, panel_type: str):
        if panel_type in STAFF_OPERATION_PANEL_TYPES:
            await _staff_panel_disable(interaction, panel_type)
            return
        await _panel_disable(interaction, panel_type)

    @panel_group.command(name="refresh", description="Refresh panel trust/staff")
    @app_commands.choices(panel=PANEL_REFRESH_CHOICES)
    async def panel_refresh(interaction: discord.Interaction, panel: app_commands.Choice[str]):
        await _panel_refresh_by_type(interaction, panel.value)

    @panel_group.command(name="disable", description="Nonaktifkan panel trust/staff")
    @app_commands.choices(panel=PANEL_DISABLE_CHOICES)
    async def panel_disable(interaction: discord.Interaction, panel: app_commands.Choice[str]):
        await _panel_disable_by_type(interaction, panel.value)

    @mm_status_group.command(name="set", description="Set status operasi middleman kamu")
    async def mm_status_set(interaction: discord.Interaction, status: str, note: str = None):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur status middleman.", ephemeral=True)
            return
        status_value = str(status or "").strip().lower()
        updated, error = await set_middleman_status(interaction.guild.id, interaction.user.id, status_value, note, interaction.user.id)
        if error == "invalid_status":
            await interaction.response.send_message("Status harus available, busy, offline, atau unavailable.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Status middleman kamu sekarang `{updated['status']}`.",
            ephemeral=True,
        )
        await send_deal_audit_log(
            interaction.guild,
            "Middleman Status Updated",
            actor=interaction.user,
            note=f"status={updated['status']}",
        )

    @mm_status_group.command(name="clear", description="Clear status operasi middleman kamu")
    async def mm_status_clear(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur status middleman.", ephemeral=True)
            return
        updated, _error = await clear_middleman_status(interaction.guild.id, interaction.user.id, interaction.user.id)
        await interaction.response.send_message("Status middleman kamu direset ke `offline`.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Middleman Status Cleared",
            actor=interaction.user,
            note=f"status={updated['status'] if updated else 'offline'}",
        )

    @vouch_review_group.command(name="set", description="Atur channel review manual vouch")
    async def vouch_review_channel_set(interaction: discord.Interaction, channel: discord.TextChannel):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur review vouch.", ephemeral=True)
            return
        await set_manual_vouch_review_config(interaction.guild.id, channel.id, enabled=True)
        await interaction.response.send_message("Channel review vouch berhasil diatur.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Manual Vouch Review Channel Configured",
            actor=interaction.user,
            target=channel,
        )

    @vouch_review_group.command(name="disable", description="Nonaktifkan channel review manual vouch")
    async def vouch_review_channel_disable(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur review vouch.", ephemeral=True)
            return
        await disable_manual_vouch_review_config(interaction.guild.id)
        await interaction.response.send_message("Channel review vouch berhasil dinonaktifkan.", ephemeral=True)

    @vouch_review_group.command(name="status", description="Lihat status channel review manual vouch")
    async def vouch_review_channel_status(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur review vouch.", ephemeral=True)
            return
        config = await get_manual_vouch_review_config(interaction.guild.id)
        enabled = bool(config and config.get("enabled"))
        channel_value = "-"
        if config and config.get("reviewChannelId"):
            try:
                channel = interaction.guild.get_channel(int(config["reviewChannelId"]))
                channel_value = channel.mention if channel else f"Channel tidak ditemukan ({config['reviewChannelId']})"
            except (TypeError, ValueError):
                channel_value = "Channel tidak valid"
        await interaction.response.send_message(
            f"Review vouch: **{'aktif' if enabled else 'nonaktif'}**\nChannel: {channel_value}",
            ephemeral=True,
        )

    @vouch_panel_group.command(name="setup", description="Kirim panel publik submit manual vouch")
    async def vouch_panel_setup(interaction: discord.Interaction, channel: discord.TextChannel):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur panel vouch.", ephemeral=True)
            return
        await _send_or_update_manual_vouch_panel(interaction.guild, channel)
        await interaction.response.send_message("Panel vouch berhasil diatur.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Manual Vouch Panel Configured",
            actor=interaction.user,
            target=channel,
        )

    @vouch_panel_group.command(name="disable", description="Nonaktifkan panel publik submit manual vouch")
    async def vouch_panel_disable(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur panel vouch.", ephemeral=True)
            return
        await disable_manual_vouch_panel_config(interaction.guild.id)
        await interaction.response.send_message("Panel vouch berhasil dinonaktifkan.", ephemeral=True)

    @audit_group.command(name="set", description="Atur channel staff audit log deal")
    async def audit_log_set(interaction: discord.Interaction, channel: discord.TextChannel):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur audit log.", ephemeral=True)
            return
        await set_deal_audit_log_config(interaction.guild.id, channel.id, enabled=True)
        await interaction.response.send_message("Audit log deal berhasil diatur.", ephemeral=True)
        await send_deal_audit_log(
            interaction.guild,
            "Audit Log Configured",
            actor=interaction.user,
            target=channel,
            note="Audit log deal diaktifkan.",
        )

    @audit_group.command(name="disable", description="Nonaktifkan staff audit log deal")
    async def audit_log_disable(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur audit log.", ephemeral=True)
            return
        await send_deal_audit_log(
            interaction.guild,
            "Audit Log Disabled",
            actor=interaction.user,
            note="Audit log deal dinonaktifkan.",
        )
        await disable_deal_audit_log(interaction.guild.id)
        await interaction.response.send_message("Audit log deal berhasil dinonaktifkan.", ephemeral=True)

    @audit_group.command(name="status", description="Lihat status staff audit log deal")
    async def audit_log_status(interaction: discord.Interaction):
        if not await _can_configure_audit_log(interaction):
            await interaction.response.send_message("Kamu tidak punya permission untuk mengatur audit log.", ephemeral=True)
            return
        config = await get_deal_audit_log_config(interaction.guild.id)
        enabled = bool(config and config.get("enabled"))
        channel_value = "-"
        if config and config.get("channelId"):
            try:
                channel = interaction.guild.get_channel(int(config["channelId"]))
                channel_value = channel.mention if channel else f"Channel tidak ditemukan ({config['channelId']})"
            except (TypeError, ValueError):
                channel_value = "Channel tidak valid"
        status = "aktif" if enabled else "nonaktif"
        await interaction.response.send_message(
            f"Audit log deal: **{status}**\nChannel: {channel_value}",
            ephemeral=True,
        )

    @config_group.command(name="role", description="Atur role middleman/staff")
    async def config_role(interaction: discord.Interaction, role: discord.Role):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        config = await save_deal_config(interaction.guild.id, middleman_role_id=role.id)
        await interaction.response.send_message(f"✅ Role middleman diatur ke {role.mention}. Prefix Deal ID: `{config['dealIdPrefix']}`", ephemeral=True)

    @config_group.command(name="add-role", description="Tambahkan role staff deal")
    async def config_add_role(interaction: discord.Interaction, role: discord.Role):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id) or {"dealStaffRoleIds": []}
        ids = list(dict.fromkeys([*config.get("dealStaffRoleIds", []), str(role.id)]))
        await save_deal_config(interaction.guild.id, deal_staff_role_ids=ids)
        await interaction.response.send_message(f"✅ Role {role.mention} ditambahkan sebagai staff deal.", ephemeral=True)

    @config_group.command(name="remove-role", description="Hapus role staff deal")
    async def config_remove_role(interaction: discord.Interaction, role: discord.Role):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id) or {"dealStaffRoleIds": []}
        ids = [rid for rid in config.get("dealStaffRoleIds", []) if rid != str(role.id)]
        await save_deal_config(interaction.guild.id, deal_staff_role_ids=ids)
        await interaction.response.send_message(f"✅ Role {role.mention} dihapus dari staff deal.", ephemeral=True)

    @config_group.command(name="roles", description="Lihat role staff deal")
    async def config_roles(interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa melihat konfigurasi deal.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id) or {}
        role_ids = []
        if config.get("middlemanRoleId"):
            role_ids.append(str(config["middlemanRoleId"]))
        role_ids.extend(str(rid) for rid in config.get("dealStaffRoleIds", []))
        mentions = []
        for rid in dict.fromkeys(role_ids):
            role = interaction.guild.get_role(int(rid))
            mentions.append(role.mention if role else rid)
        value = ", ".join(mentions) if mentions else "Default nama role: Middleman, Miserator"
        await interaction.response.send_message(f"Role staff deal: {value}", ephemeral=True)

    @config_group.command(name="owner-role", description="Atur role owner untuk admin override deal")
    async def config_owner_role(interaction: discord.Interaction, role: discord.Role):
        if not await _require_deal_phase(interaction, 4):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        await save_deal_config(interaction.guild.id, owner_role_id=role.id)
        await interaction.response.send_message(f"✅ Owner role untuk override deal diatur ke {role.mention}.", ephemeral=True)

    @config_group.command(name="add-category", description="Legacy opsional kategori deal")
    async def config_add_category(interaction: discord.Interaction, category: discord.CategoryChannel):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id) or {"allowedTicketCategoryIds": []}
        ids = list(dict.fromkeys(config.get("allowedTicketCategoryIds", []) + [str(category.id)]))
        await save_deal_config(interaction.guild.id, allowed_ticket_category_ids=ids)
        await interaction.response.send_message(
            f"✅ Kategori `{category.name}` disimpan sebagai legacy config opsional. Kategori ticket tidak wajib lagi; `/deal start` bisa digunakan di channel mana pun.",
            ephemeral=True,
        )

    @config_group.command(name="remove-category", description="Hapus legacy kategori deal")
    async def config_remove_category(interaction: discord.Interaction, category: discord.CategoryChannel):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id) or {"allowedTicketCategoryIds": []}
        ids = [cid for cid in config.get("allowedTicketCategoryIds", []) if cid != str(category.id)]
        await save_deal_config(interaction.guild.id, allowed_ticket_category_ids=ids)
        await interaction.response.send_message(
            f"✅ Kategori `{category.name}` dihapus dari legacy config opsional. Kategori ticket tidak wajib lagi; `/deal start` bisa digunakan di channel mana pun.",
            ephemeral=True,
        )

    @config_group.command(name="log-channel", description="Atur channel log deal")
    async def config_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        await save_deal_config(interaction.guild.id, deal_log_channel_id=channel.id)
        await interaction.response.send_message(f"✅ Channel log deal diatur ke {channel.mention}.", ephemeral=True)

    @config_group.command(name="vouch-channel", description="Atur channel testimonial/vouch deal")
    async def config_vouch_channel(interaction: discord.Interaction, channel: discord.TextChannel):
        if not await _require_deal_phase(interaction, 3):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        await save_deal_config(interaction.guild.id, vouch_channel_id=channel.id)
        await interaction.response.send_message(f"✅ Channel testimonial/vouch deal diatur ke {channel.mention}.", ephemeral=True)

    @config_group.command(name="ping-cooldown", description="Atur cooldown ping reminder dalam detik")
    async def config_ping_cooldown(interaction: discord.Interaction, seconds: int):
        if not await _require_deal_phase(interaction, 5):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        if seconds < 60:
            await interaction.response.send_message("Ping cooldown minimal 60 detik.", ephemeral=True)
            return
        await save_deal_config(interaction.guild.id, ping_cooldown_seconds=seconds)
        await interaction.response.send_message(f"✅ Ping cooldown reminder diatur ke {seconds} detik.", ephemeral=True)

    @config_group.command(name="reminders", description="Atur reminder otomatis deal")
    async def config_reminders(
        interaction: discord.Interaction,
        enabled: bool,
        form_seconds: int = 7200,
        waiting_funds_seconds: int = 21600,
        funds_confirm_seconds: int = 86400,
        disputed_seconds: int = 86400,
        timeout_seconds: int = 604800,
    ):
        if not await _require_deal_phase(interaction, 5):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        intervals = {
            "form_not_submitted_seconds": form_seconds,
            "waiting_funds_seconds": waiting_funds_seconds,
            "funds_no_confirm_seconds": funds_confirm_seconds,
            "disputed_seconds": disputed_seconds,
            "timeout_seconds": timeout_seconds,
        }
        await save_deal_config(interaction.guild.id, reminder_enabled=enabled, reminder_intervals=intervals)
        await interaction.response.send_message(f"✅ Reminder deal {'diaktifkan' if enabled else 'dinonaktifkan'}.", ephemeral=True)

    @config_group.command(name="proof", description="Atur requirement proof payment/transfer")
    async def config_proof(interaction: discord.Interaction, require_payment_proof: bool, require_transfer_proof: bool):
        if not await _require_deal_phase(interaction, 5):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        await save_deal_config(
            interaction.guild.id,
            require_payment_proof=require_payment_proof,
            require_transfer_proof=require_transfer_proof,
        )
        await interaction.response.send_message("✅ Requirement proof deal diperbarui.", ephemeral=True)

    @config_group.command(name="user-cancel", description="Atur apakah buyer/seller boleh request cancel")
    async def config_user_cancel(interaction: discord.Interaction, enabled: bool):
        if not await _require_deal_phase(interaction, 5):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        await save_deal_config(interaction.guild.id, allow_user_cancel_request=enabled)
        await interaction.response.send_message(f"✅ User cancel request {'diaktifkan' if enabled else 'dinonaktifkan'}.", ephemeral=True)

    @config_group.command(name="auto-timeout", description="Atur auto-timeout deal inactive")
    async def config_auto_timeout(interaction: discord.Interaction, enabled: bool):
        if not await _require_deal_phase(interaction, 5):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        await save_deal_config(interaction.guild.id, auto_timeout_enabled=enabled)
        await interaction.response.send_message(f"✅ Auto-timeout deal {'diaktifkan' if enabled else 'dinonaktifkan'}.", ephemeral=True)

    @config_group.command(name="trusted-threshold", description="Atur trusted role threshold deal")
    async def config_trusted_threshold(interaction: discord.Interaction, threshold: int):
        if not await _require_deal_phase(interaction, 5):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        if threshold < 0:
            await interaction.response.send_message("Trusted role threshold tidak boleh negatif.", ephemeral=True)
            return
        await save_deal_config(interaction.guild.id, trusted_role_threshold=threshold)
        await interaction.response.send_message(f"✅ Trusted role threshold diatur ke {threshold}.", ephemeral=True)

    @config_group.command(name="prefix", description="Atur prefix Deal ID")
    async def config_prefix(interaction: discord.Interaction, prefix: str):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa mengubah konfigurasi deal.", ephemeral=True)
            return
        config = await save_deal_config(interaction.guild.id, deal_id_prefix=prefix)
        await interaction.response.send_message(f"✅ Prefix Deal ID diatur ke `{config['dealIdPrefix']}`.", ephemeral=True)

    @config_group.command(name="show", description="Lihat konfigurasi deal")
    async def config_show(interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa melihat konfigurasi deal.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id) or {}
        await interaction.response.send_message(embed=_deal_config_embed(interaction.guild, config), ephemeral=True)

    @config_group.command(name="view", description="Lihat konfigurasi deal")
    async def config_view(interaction: discord.Interaction):
        if not await _require_deal_phase(interaction, 5):
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("Hanya admin yang bisa melihat konfigurasi deal.", ephemeral=True)
            return
        config = await get_deal_config(interaction.guild.id) or {}
        await interaction.response.send_message(embed=_deal_config_embed(interaction.guild, config), ephemeral=True)

    deal_group.add_command(audit_group)
    deal_group.add_command(archive_group)
    deal_group.add_command(panel_group)
    deal_group.add_command(mm_status_group)
    deal_group.add_command(vouch_review_group)
    deal_group.add_command(vouch_panel_group)
    deal_group.add_command(scam_review_group)
    deal_group.add_command(scam_panel_group)
    deal_group.add_command(trust_status_group)
    deal_group.add_command(config_group)
    tree.add_command(deal_group)

    @tree.command(name="vouch", description="Beri vouch verified dari deal middleman yang sudah selesai")
    async def slash_vouch(
        interaction: discord.Interaction,
        deal_id: str,
        target: discord.Member,
        rating: int,
        review: str,
    ):
        if not await _require_deal_phase(interaction, 3):
            return
        if not interaction.guild:
            await interaction.response.send_message("Command ini hanya bisa digunakan di server.", ephemeral=True)
            return
        deal = await get_deal_by_deal_id(interaction.guild.id, deal_id.strip().upper())
        if not deal:
            await interaction.response.send_message("Deal ID tidak ditemukan.", ephemeral=True)
            return
        vouch, error = await create_verified_deal_vouch(
            deal,
            interaction.user.id,
            target.id,
            rating,
            review,
            None,
        )
        if error == "self":
            await interaction.response.send_message("Kamu tidak bisa memberi vouch ke diri sendiri.", ephemeral=True)
            return
        if error == "duplicate":
            await interaction.response.send_message("Kamu sudah memberi vouch untuk user ini di deal ini.", ephemeral=True)
            return
        if error == "invalid_rating":
            await interaction.response.send_message("Rating harus angka 1 sampai 5.", ephemeral=True)
            return
        if error == "empty_review":
            await interaction.response.send_message("Review tidak boleh kosong.", ephemeral=True)
            return
        if error == "short_review":
            await interaction.response.send_message("Review terlalu pendek.", ephemeral=True)
            return
        if error == "not_completed":
            await interaction.response.send_message("Vouch hanya bisa diberikan setelah deal Completed.", ephemeral=True)
            return
        if error in ("not_participant", "not_allowed"):
            await interaction.response.send_message("Kamu tidak punya izin memberi vouch untuk target ini.", ephemeral=True)
            return
        if error:
            await interaction.response.send_message("Gagal menyimpan vouch.", ephemeral=True)
            return
        await interaction.response.send_message(embed=await _vouch_success_embed(vouch, interaction.guild, interaction.client))
        await _send_vouch_channel(interaction, vouch)
        await _log_account_age_suspicion(interaction, vouch)
        await _refresh_vouch_progress_message(interaction, deal)

    @tree.command(name="vouches", description="Lihat semua vouch user")
    async def slash_vouches(interaction: discord.Interaction, user: discord.Member):
        if not await _require_deal_phase(interaction, 6):
            return
        vouches = await list_user_vouches(interaction.guild.id, user.id)
        view = VouchesListView(user, vouches)
        await interaction.response.send_message(embed=await view.embed(interaction.client), view=view)

    @tree.command(name="rank", description="Lihat rank reputasi user")
    async def slash_rank(interaction: discord.Interaction, user: discord.Member):
        if not await _require_deal_phase(interaction, 6):
            return
        rep = await recalculate_user_reputation(interaction.guild.id, user.id)
        await interaction.response.send_message(embed=_rank_embed(user, rep))

    @tree.command(name="vouchleaderboard", description="Lihat top trusted users")
    async def slash_reputation_leaderboard(interaction: discord.Interaction):
        if not await _require_deal_phase(interaction, 6):
            return
        reps = await get_reputation_leaderboard(interaction.guild.id, 10)
        await interaction.response.send_message(embed=await _vouch_leaderboard_embed(interaction.guild, interaction.client, reps))

    @tree.command(name="removevouch", description="Hapus vouch dari reputasi (soft remove)")
    async def slash_removevouch(interaction: discord.Interaction, vouch_id: int, reason: str):
        if not await _require_deal_phase(interaction, 6):
            return
        config = await get_deal_config(interaction.guild.id)
        if not member_has_deal_role(interaction.user, config) and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Hanya staff yang bisa remove vouch.", ephemeral=True)
            return
        vouch, error = await remove_vouch(interaction.guild.id, vouch_id, interaction.user.id, reason)
        if error == "missing_reason":
            await interaction.response.send_message("Reason wajib diisi.", ephemeral=True)
            return
        if error == "not_found":
            await interaction.response.send_message("Vouch ID tidak ditemukan.", ephemeral=True)
            return
        if error == "already_removed":
            await interaction.response.send_message("Vouch ini sudah removed.", ephemeral=True)
            return
        target_display = await format_user_display(interaction.client, interaction.guild, vouch.get("targetId"))
        await interaction.response.send_message(f"✅ Vouch `#{vouch_id}` sudah ditandai removed. Reputasi {target_display} diperbarui.", ephemeral=True)

    @tree.command(name="reportvouch", description="Report vouch yang mencurigakan")
    async def slash_reportvouch(interaction: discord.Interaction, vouch_id: int, reason: str, proof: str = None):
        if not await _require_deal_phase(interaction, 6):
            return
        report, error = await report_vouch(interaction.guild.id, vouch_id, interaction.user.id, reason, proof)
        if error == "missing_reason":
            await interaction.response.send_message("Reason wajib diisi.", ephemeral=True)
            return
        if error == "not_found":
            await interaction.response.send_message("Vouch ID tidak ditemukan.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Report vouch `#{vouch_id}` sudah dikirim untuk review staff.", ephemeral=True)
        config = await get_deal_config(interaction.guild.id)
        channel = interaction.guild.get_channel(int(config["dealLogChannelId"])) if config and config.get("dealLogChannelId") else None
        if channel:
            embed = discord.Embed(title="⚠️ Vouch Report", color=0xFEE75C)
            embed.add_field(name="Report ID", value=str(report["id"]), inline=True)
            embed.add_field(name="Vouch ID", value=str(vouch_id), inline=True)
            embed.add_field(name="Reporter", value=interaction.user.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Proof", value=proof or "-", inline=False)
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    register_prefix_command_handler("deal", deal_prefix_dispatcher)

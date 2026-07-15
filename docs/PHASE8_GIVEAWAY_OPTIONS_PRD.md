# Phase 8 Giveaway dan Eternal Options

## Status

Phase 8 diimplementasikan untuk staging dengan migration eksplisit `800 / phase8-giveaway-options`.
`ECONOMY_PHASE8_ENABLED` tetap `false` secara default. Production belum dimigrasikan, belum
diaktifkan, belum di-seed, dan belum disetujui untuk cutover.

## Scope

- Giveaway V1 dengan tiket 10.000 ECY, escrow, Activity Score, secure draw, acknowledgement,
  structured redraw evidence, refund pembatalan, dan recovery.
- Activity Score 30 hari dengan category cap dan active-day UTC.
- `VOICE_ACTIVITY_30M` per guild/user dalam blok 30 menit yang tidak tumpang tindih.
- Eternal Options berdasarkan exact committed Phase 6 price-history identity.
- Shared Casino exposure untuk liability Casino dan Options.
- Fencing Giveaway legacy, Crash, dan Binomo hanya ketika Phase 8 aktif.

## Non-goals

- Tidak ada automatic prize fulfillment, winner tax, cancellation Options, Phase 9, write API,
  production migration, atau perubahan odds Casino, Crypto pricing, dan Mining economics.
- Giveaway legacy, Crash, dan Binomo tetap berjalan seperti semula ketika flag Phase 8 false.

## Giveaway

Syarat entry dan draw: account age 30 hari, membership 14 hari, masih berada di guild, non-bot,
tidak `blacklisted`, dan capped Activity Score minimal 80. Score memakai half-open UTC 30-day
window. Cap kategori: Daily 40, Daily Quest 80, Voice 40, Boss participation 30, Dungeon 30,
dan active-day 60.

Satu user membeli satu tiket. Satu channel memiliki satu Giveaway unresolved dan guild maksimal
tiga. Entry memindahkan 10.000 ECY dari user ke `ECY_GIVEAWAY`. Pembatalan mengembalikan tiket
secara penuh. Completion menahan 80%, memindahkan 10% ke `ECY_RESERVE`, dan 10% ke `ECY_BURN`.
Tidak adanya entrant eligible tidak menciptakan refund; alokasi completion tetap berlaku.

Draw memakai `secrets.randbelow` atas pool user ID canonical. Pool, evidence, hash, index, winner,
deadline 24 jam, dan receipt dipersist sebelum announcement. Claim hanya acknowledgement melalui
persistent actor-validated control. Redraw memerlukan reason code dan immutable evidence. Rule
violation wajib menggunakan pesan Discord guild-local yang berhasil di-fetch dan di-hash; Admin
tidak pernah memasukkan winner pengganti.

## Voice Activity

State menyimpan qualified start, awarded-through, last observed, block sequence, status, dan
version. Satu blok selesai setiap 30 menit qualified. Insert event dan advancement boundary terjadi
dalam satu `BEGIN IMMEDIATE`. Continuous 60 menit menghasilkan tepat dua event. Qualification
break menutup remainder. Restart menutup state di `lastObservedAt` tanpa offline backfill.

## Eternal Options

- Stake 1.000-500.000 ECY, kelipatan 1.000.
- Durasi 5, 10, atau 30 menit.
- Maksimum tiga posisi dan combined active stake 500.000 ECY per guild/user.
- Win gross `floor(stake * 19000 / 10000)`, tie refund stake, loss tanpa transaksi ECY kedua.
- Entry memakai latest committed price pada atau sebelum acceptance.
- Expiry memakai first committed history pada atau setelah expiry, diurutkan timestamp lalu ID.
- Exact history IDs bersifat immutable; missing expiry history tetap pending.

Liability Options adalah gross 1,90x. Shared availability:

```text
availableBankroll = ECY_CASINO - active/review Casino liability - active/review Options liability
exposureCap = floor(max(0, availableBankroll) * 2 / 100)
```

Opening memindahkan stake user ke `ECY_CASINO`. Win/tie dibayar dari account itu. Loss hanya
menulis domain settlement receipt yang merujuk opening transaction; tidak ada synthetic ledger.

## Migration dan Recovery

Migration 800 hanya melalui CLI staging, backup-first, idempotent, checksummed, dan menolak path
production. Capability memerlukan exact Phase 5 dan Phase 6 schema/checksum. Startup tidak pernah
menerapkan migration. Legacy active Giveaway dan Binomo disnapshot read-only/review tanpa mutasi.

Recovery memakai original request, transaction, pool, evidence, price, reservation, winner, dan
receipt. Recovery tidak reroll, auto-redraw, backfill voice time, mengganti harga, atau mint diam-diam.
Pause memblokir create/entry/open tetapi tidak memblokir obligation settlement, refund, claim,
structured redraw, dan receipt replay.

## Verification

- Migration checksum: `33c88d9b49b31b0b029c641f7fecaadeacd57db2f5f2e8c6dacfb8cd958d40a9`.
- Simulation artifact: `ce50819010645c8cabcc5a2398837b77f0911f8dd863a8c85f6408d3a4a38ec4`.
- Giveaway: 1.000 users, 10.000 draws, chi-square p-value `0.6212634449446391`.
- Options: 20 seeds, 100.000 positions/seed, aggregate RTP `0.9504240337325349`,
  95% CI `[0.9491074010171691, 0.9517406664479008]`.
- Verifikasi otomatis: 190 test Economy Phase 1-8, 19 test fokus Phase 8,
  64 test Marketplace, dan 15 test Living PRD lulus.
- Migration apply/replay/reconciliation lulus dengan `integrity_check=ok` dan
  nol error `foreign_key_check` pada database sementara.
- Both acceptance gates pass. Connected Discord staging and dashboard production build remain pending.

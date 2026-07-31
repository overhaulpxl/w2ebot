# Phase 9B Economy Dashboard dan Notification Routing

## Status

- Implementasi lokal: `IMPLEMENTED_LOCAL_VERIFICATION`
- Migrasi: `910 / phase9b-dashboard-notification-routing`
- Feature flag baru: tidak ada
- Connected Discord/OAuth staging: pending
- Production: tidak dimigrasi, tidak diaktifkan, tidak disetujui

## Tujuan

Phase 9B menyediakan dashboard Economy yang membaca state otoritatif, kontrol operasional terbatas,
dan routing notifikasi durable. Semua halaman dan API browser tetap berada di belakang session
`DASHBOARD_VIEW` Phase 9A. Semua backend route adalah `POST` internal bertanda tangan dan kembali
memvalidasi permission, session, guild, nonce, payload, serta capability migrasi 900 dan 910.

## Dashboard Read Model

Read model mencakup overview, supply, flow 7/30 hari, liability, Marketplace, Casino/Options,
Giveaway, Crypto/Mining, recovery/outbox, route, dan audit operator. Setiap response membawa
`schemaVersion`, `guildId`, `asOf`, `sourceAsOf`, `freshness`, `warnings`, dan `data`. Integer
transport dikirim sebagai string desimal. Agregasi supply dilakukan dengan integer Python agar
tidak overflow di SQLite. Operasi yang tidak dikenal dilaporkan sebagai warning, bukan disembunyikan.

## Notification Routing

Kategori otoritatif adalah `GENERAL`, `MARKET_CRYPTO`, `MARKETPLACE`, `GIVEAWAY`, `CASINO`,
`ETERNAL_OPTIONS`, `MINING`, `BOSS`, `LEVEL_UP`, `BIRTHDAY`, `BOOSTER`, `RECOVERY`, `SECURITY`,
dan `OPERATOR_AUDIT`. Setelah capability 910 aktif, route database bersifat eksklusif dan tidak
ada fallback channel acak.

Route disimpan dengan versi, channel, role opsional, dan event filter. Perubahan route hanya
berlaku bagi reservation baru. Delivery yang sudah direservasi mempertahankan route version,
channel, role, event type, payload hash, dan marker semula.

## Durable Delivery

Produsen domain tidak mengirim pesan Discord melalui jalur baru. Existing outbox digunakan sebagai
source of truth; produsen legacy tanpa outbox membuat `DashboardNotificationDelivery` deterministik
sebelum delivery. Unique identity `(guildId, deliveryKind, sourceType, sourceKey)` mencegah duplikasi.

Lifecycle adalah `RESERVED -> LEASED`, lalu `SENT`, `FAILED`, atau `REVIEW_REQUIRED`. `FAILED`
hanya berarti Discord secara konklusif tidak menerima pesan dan dapat lease ulang dengan identity
yang sama. Timeout, response loss, atau marker inspection yang tidak pasti menjadi
`REVIEW_REQUIRED` dan tidak pernah dikirim ulang otomatis. Worker mencari marker deterministik
sebelum mengirim, mengadopsi pesan yang sudah ada, dan memfinalisasi delivery, source outbox, serta
status route dalam satu transaction. Delivery `TEST` memiliki namespace dan history terpisah serta
menggunakan `AllowedMentions.none()`.

Personal DM, Marketplace watch DM, dan channel milik Giveaway mempertahankan destination domainnya.
Guild-wide birthday, level-up, Boss, booster, dan legacy market producer menggunakan reservation
deterministik setelah capability 910. Binomo deprecated tidak dipetakan ulang.

## Controlled Operations

Route update memerlukan `NOTIFICATION_ROUTING_CONTROL`. Pause/resume hanya untuk daftar emergency
feature existing dan memerlukan `ECONOMY_PAUSE_CONTROL`. Reviewed recovery memerlukan
`REVIEWED_RECOVERY_CONTROL`, target existing berstatus `REVIEW_REQUIRED`, stable request ID,
expected version, dan resolution allowlist. Semua mutation menggunakan `DashboardControlledOperation`,
CSRF satu kali, `BEGIN IMMEDIATE`, immutable receipt, dan `DashboardOperatorAudit` append-only.
Tidak ada editor balance, ledger, rate, fee, odds, payout, seed, atau product rule.

## Migrasi 910

Migrasi manual dan production-refusing membuat `DashboardNotificationRoute`,
`DashboardNotificationDelivery`, `DashboardNotificationLegacySnapshot`,
`DashboardEconomyReconciliationRun`, dan `DashboardRecoveryControl`.

Migrasi memerlukan capability 900, mendukung dry-run, backup, apply, replay idempotent, verify,
reconcile, restore, failure injection, `integrity_check`, dan `foreign_key_check`. `config.json`
tetap read-only historical evidence; import route hanya diterima dengan manifest channel guild yang
membuktikan ownership, visibility, dan send permission. Startup tidak pernah menjalankan migrasi.

## Guardrails

- Seluruh Economy flag tetap `false` secara default.
- Tidak ada Phase 9B feature flag atau Phase 9C.
- Tidak ada write API Discord baru di domain service atau command callback.
- Deal, Middleman, Trusted Vouch, `cogs/deal.py`, command ownership, dan nilai produk Phase 1-8 tidak berubah.
- Production dan connected Discord/OAuth staging tidak diakses dalam implementasi lokal ini.

## Verifikasi

Test mencakup migration lifecycle, schema constraint, reporting, overflow-safe transport,
route validation, immutable reservation, lease race, marker adoption, conclusive retry,
uncertain-send review, source outbox adoption, idempotency, expected version, audit, protected API,
dashboard page contract, TypeScript, Vitest, dan production build. Hasil final dicatat di
`docs/project_state.json`; connected staging tetap blocker rollout.

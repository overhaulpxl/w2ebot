# W2E Dashboard — Contoh Integrasi Next.js (UI siap pakai)

Admin dashboard **Next.js App Router (14+)** untuk W2E Bot API. UI sudah dipoles
(dark theme, design token, aksesibilitas, loading/error/empty state, toast).
Tinggal salin isi folder ini ke project Next.js web sebelah.

## Konsep keamanan (WAJIB dipahami)

```
Browser (komponen dashboard)
  ├─ READ  → diambil di Server Component (botGet) → token aman, tanpa CORS
  └─ WRITE → lewat Route Handler /api/admin/* (server) → baru ke bot API
```

`DASHBOARD_TOKEN` **cuma hidup di server Next.js**, gak pernah dikirim ke browser.

## Isi folder

```
app/
  globals.css                 # design token + semua style (CSS murni, no Tailwind)
  layout.tsx                  # root layout
  page.tsx                    # dashboard: stat cards + leaderboard + admin panel
  api/admin/
    coins/route.ts            # proxy POST /api/user/{id}/coins
    give-item/route.ts        # proxy POST /api/user/{id}/give-item
    boss-spawn/route.ts       # proxy POST /api/boss/spawn
    announce/route.ts         # proxy POST /api/announce
components/
  Icon.tsx                    # ikon SVG (tanpa emoji)
  Toast.tsx                   # toast provider (aria-live, auto-dismiss)
  AdminPanel.tsx              # form admin: loading + validasi + feedback
lib/
  botApi.ts                   # botGet (read) + botPost (write, server-only) + tipe TS
.env.local.example
```

## Setup

1. Salin folder `app/`, `components/`, `lib/` ke root project Next.js kamu.
2. Salin `.env.local.example` → `.env.local`, isi nilainya.
3. Pastikan alias `@/*` aktif di `tsconfig.json` (default di Next.js):
   ```json
   { "compilerOptions": { "paths": { "@/*": ["./*"] } } }
   ```
4. Di sisi BOT, set `ALLOWED_ORIGINS=https://dashboard-kamu.com` dan
   `DASHBOARD_TOKEN` yang sama persis dengan `.env.local`.
5. `npm install && npm run dev`.

## Env (`.env.local`)

```env
# server-only — JANGAN kasih prefix NEXT_PUBLIC
BOT_API_URL=https://api.way2eternal.com
DASHBOARD_TOKEN=token_rahasia_sama_persis_dengan_di_bot

# boleh dibaca browser (read langsung dari client, opsional)
NEXT_PUBLIC_BOT_API_URL=https://api.way2eternal.com
```

## Fitur UI yang sudah dihandle

- **Dark theme** via design token semantik (`--surface`, `--text`, `--primary`, …) — gampang re-skin.
- **Aksesibilitas:** label di tiap input, focus ring terlihat, kontras teks ≥4.5:1, `aria-live` untuk toast & error, ikon SVG (bukan emoji), `prefers-reduced-motion`.
- **State lengkap:** loading spinner per tombol, disabled saat proses, validasi inline (User ID/angka), empty state leaderboard, error state kalau bot mati.
- **Touch-friendly:** input & tombol tinggi 44px, spacing 8px, responsif sampai 375px.
- **Angka tabular** (`.tnum`) supaya kolom koin/level tidak goyang.

## Catatan penting

- **Tambahkan auth admin sendiri** (NextAuth/Clerk/session) di tiap Route Handler
  `app/api/admin/*` (ada penanda `TODO`). Token jagain bot dari publik, BUKAN
  jagain siapa yang boleh klik tombol admin.
- Endpoint write balikin `409` (boss sudah aktif), `400` (input salah), `401`
  (token salah) — sudah dihandle & ditampilkan via toast.
- Daftar lengkap endpoint ada di `../API.md`.
- CSS sengaja murni (tanpa Tailwind) biar zero-config. Kalau project kamu pakai
  Tailwind, `globals.css` tetap aman berdampingan.

# Cultra as an Android app (APK)

The phone app is the same pages as the website, wrapped in an Android app with
[Capacitor](https://capacitorjs.com/). Three parts work together:

| Part | What it is | Where |
|---|---|---|
| **App** | The pages + Android's camera scanner (Google ML Kit) | The phones, as an APK |
| **Server** | `main.py`, unchanged in how it works | [Render](https://render.com), free plan |
| **Database** | Where the server saves users, cards, balances and history | [Supabase](https://supabase.com) (PostgreSQL), free plan |

Your laptop keeps working like before: `uvicorn main:app --reload` saves into the file `cultra.db`
and doesn't touch the online database.

**Already done in the code:** the server saves its data (`storage.py`) and reads its settings
from Render (`render.yaml`); passwords are stored hashed; every page finds the server through
`config.js`; the app stays logged in; the Android back button works; the Kassa and Skan et pages
use the phone's own scanner; the libraries are inside the app instead of loaded from a CDN; the
icon, colours, camera permission and version number are set by `scripts/patch-android.js`.

Your part is below. Never paste the database connection string or its password into a chat, into
GitHub or into the code: it only goes into Render.

---

## 1. Database: Supabase (≈10 min)

1. Sign up at [supabase.com](https://supabase.com) and create a **New project**:
   - Name: `cultra`
   - Database password: press **Generate a password** (letters and digits only, which keeps the
     connection string simple). Save it somewhere private on your laptop.
   - Region: **Central EU (Frankfurt)**, the same city as the server.
2. When the project is ready, press **Connect** at the top, choose **Session pooler** and copy the
   URI. It looks like:
   ```
   postgresql://postgres.abcdefghijklmnop:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
   ```
3. Replace `[YOUR-PASSWORD]`, square brackets included, with the database password.

Use **Session pooler**, not "Direct connection": Render can only reach Supabase through the pooler
(the direct address is IPv6-only).

## 2. Code on GitHub

Merge the pull request with the app on GitHub (**Merge pull request**). Render builds from the
`main` branch.

## 3. Server: Render (≈15 min)

1. Sign up at [render.com](https://render.com) with your GitHub account.
2. **New > Blueprint**, pick the `Cultra` repository. Render reads `render.yaml` and shows one web
   service, `cultra-api`.
3. It asks for **DATABASE_URL**: paste the connection string from step 1. Create it.
4. Wait until the service says **Live** (a few minutes). In its **Logs** you should see:
   ```
   Data: PostgreSQL (aws-0-eu-central-1.pooler.supabase.com:5432/postgres) - 15 users, 0 transactions
   ```
5. The address is at the top of the service page, e.g. `https://cultra-api.onrender.com`. Open
   `<address>/health` in a browser: `{"status":"ok","storage":"PostgreSQL"}`.
6. **If your address isn't exactly `https://cultra-api.onrender.com`**, open `config.js` and put
   yours in `SERVER_URL`. That's the only line to change.

In Supabase, **Table Editor > cultra_data** now has five rows: users, bankcards, transactions,
pending_payments and short_codes.

Free plan: the server falls asleep after 15 minutes without visitors, and the first request then
takes up to a minute. The app shows "Server oyanır…" meanwhile. Before a demo, open the app a minute
early. Supabase pauses a free project after a week without use (**Restore** in its dashboard).

## 4. Install the tools (once, ≈1–2 h, mostly downloads)

1. **Node.js** 22 or newer: the LTS **Windows Installer** from [nodejs.org](https://nodejs.org).
   Check in a *new* terminal: `node -v`.
2. **Android Studio** (Otter 2025.2.1 or newer) from
   [developer.android.com/studio](https://developer.android.com/studio). Install with the default
   options, open it once and let the setup wizard download the Android SDK.

## 5. Build the APK

In VS Code's terminal, in the Cultra folder:

```bash
npm install              # downloads Capacitor and the scanner plugin (node_modules/)
npm run android:setup    # once: pages -> www/, creates android/, camera permission, icon, colours
npm run open             # opens android/ in Android Studio
```

If `npm run open` can't find Android Studio, open Android Studio yourself and choose
**Open > (the Cultra folder) > android**.

The first time, Android Studio downloads Gradle and the libraries (5–15 min, progress at the
bottom). If it offers to upgrade the Android Gradle Plugin, say no ("Don't ask for this
project"): Capacitor picked versions that work together. When it's done:

- **Build > Generate App Bundles or APKs > Generate APKs** (in older versions:
  **Build > Build Bundle(s) / APK(s) > Build APK(s)**).
- Click **locate** in the notification: `android/app/build/outputs/apk/debug/app-debug.apk`.

To install it, send the APK to the phone (USB cable, Telegram to yourself, Google Drive), open it
and allow installing apps from that source. Or connect the phone by USB with **USB debugging** on
and press **Run ▶** in Android Studio.

Errors in this step are usually Java/Gradle versions on a new machine: copy the red text from
Android Studio's **Build** window and send it to me.

## 6. Test on two phones

- [ ] First start: welcome page (maybe "Server oyanır…" first). Register, log in.
- [ ] Close the app completely, open it again: still logged in.
- [ ] Add card `1234123412341234` (05/30, CVV 123) and top up the Cultra balance.
- [ ] **Skan et:** the camera opens by itself; scan the other phone's Receive QR and pay.
- [ ] **Biznes > Kassa:** press **📷 Skan et**, scan product barcodes, then the other phone's
      Payment QR or barcode. The other phone approves.
      For product barcodes, open `http://localhost:5500/products.html?server=online` on the laptop
      (Live Server running), or print that page.
- [ ] Cashback, level badge and history after paying.
- [ ] Android back button: goes back a page; on the home page it leaves the app.
- [ ] Deny the camera once: the page explains it and offers **Parametrləri aç**.

The laptop can join the same demo (for example as the shop's till with your hardware barcode
scanner): open any page with `?server=online` at the end of the address, and the browser uses the
online server from then on. `?server=local` switches back. On the Kassa page, click into the
barcode field under the cart before using the hardware scanner: it types the digits and presses
Enter for you.

When something goes wrong, send me what you did, what you expected and a screenshot. For crashes:
Android Studio > **Logcat**.

## 7. Updating the app later

- **Pages changed:** `npm run sync`, build the APK again and install it over the old one (users
  stay logged in).
- **Sharing an update with others:** first raise `"version"` in `package.json`
  (`1.0.0` → `1.0.1`), then `npm run sync`. Android installs an update over the old app only if
  it's signed with the same key and its version isn't lower.
- **`main.py` changed:** push to GitHub. Render redeploys by itself, and the data stays in Supabase.
- **Start over from the demo data:** in Render **Suspend** the service (its Settings page), in
  Supabase delete all rows of `cultra_data`, then **Resume** the service: it starts with the demo
  data. On the laptop: stop the server and delete `cultra.db`.

## 8. A signed APK to share

1. Android Studio: **Build > Generate Signed App Bundle or APK > APK > Next**.
2. **Create new…** key store. Save it *outside* the project, e.g.
   `C:\Users\Katana\keys\cultra-release.jks`, with a password, alias `cultra` and 25+ years.
3. **release > Create**. The APK ends up in `android/app/release/app-release.apk`.

Back up the `.jks` file and its passwords (cloud + USB stick). Every update must be signed with the
same key: without it, people would have to uninstall the app (and lose its data on the phone)
before installing a new one.

---

## Good to know

- **No Google Play on the phone** (Huawei, many Chinese phones): the scanner still works, ML Kit's
  barcode model is inside the app.
- **In China** Render and Supabase can be slow or unreachable without a VPN.
- **Security:** fine for test money, not for real money. Passwords are hashed now, but the server
  still trusts the user id the app sends (see Known limitations in the README).
- **Bank logos** on the welcome page are the real banks' logos. Fine for a private demo; before
  sharing the app widely, consider neutral icons.
- **What the app is made of:** `capacitor.config.json` (name `Cultra`, id `com.emilaliyev.cultra`),
  `package.json` (versions, npm scripts), `scripts/build-web.js` (pages → `www/`),
  `scripts/patch-android.js` (Android settings), `resources/android/res/` (icons),
  `native_scanner.js` (the phone's scanner). `www/`, `android/` and `node_modules/` are generated
  and not in git.

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Per-destination setup guides for Mirror-Leech.

Single source of truth consumed by two surfaces:

  * /settings → Mirror-Leech → <provider> → 📖 Setup Guide
  * /help     → Mirror-Leech → Destinations → <provider>

Each guide is a small list of pages rendered with the shared UI chrome
(`frame_plain`), so the visual style stays consistent with every other
Mirror-Leech screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GuidePage:
    """One screen in a setup guide. Rendered with frame_plain."""

    title: str
    body: str


@dataclass(frozen=True)
class DestinationGuide:
    """A multi-page walkthrough for linking one destination."""

    provider_id: str
    display_name: str
    summary: str
    required_values: list[str] = field(default_factory=list)
    pages: list[GuidePage] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)


# ---------------------------------------------------------------------------
# Troubleshooting-page helper
# ---------------------------------------------------------------------------
def _trouble_page(provider: str, items: list[tuple[str, str]]) -> GuidePage:
    """Render a uniformly-styled troubleshooting page.

    Each entry is `(error_label, fix)` — label becomes a bold header,
    fix is a short paragraph. Entries are separated by a blank line so
    the Telegram renderer keeps them visually distinct.
    """
    parts: list[str] = [
        "> Common errors and how to recover from them. If your issue",
        "> isn't here, run **🔌 Test connection** first — the message it",
        "> returns usually matches one of the entries below.",
        "",
    ]
    for err, fix in items:
        parts.append(f"**{err}**")
        parts.append(fix)
        parts.append("")
    return GuidePage(
        title=f"Troubleshooting — {provider}",
        body="\n".join(parts).rstrip(),
    )


# ---------------------------------------------------------------------------
# Google Drive — 3 pages (OAuth project, refresh token, paste)
# ---------------------------------------------------------------------------
_GDRIVE = DestinationGuide(
    provider_id="gdrive",
    display_name="Google Drive",
    summary=(
        "OAuth-based upload to your own Google Drive folder. "
        "Needs three values: refresh_token, client_id, client_secret."
    ),
    required_values=["refresh_token", "client_id", "client_secret"],
    pages=[
        GuidePage(
            title="Step 1 / 3 — Google Cloud project",
            body=(
                "> Create an OAuth 2.0 client in Google Cloud so the bot can\n"
                "> talk to the Drive API on your behalf.\n\n"
                "**1.** Open https://console.cloud.google.com\n"
                "**2.** Create a new project (or pick an existing one).\n"
                "**3.** APIs & Services → Library → enable **Google Drive API**.\n"
                "**4.** APIs & Services → Credentials → **Create Credentials**\n"
                "    → OAuth client ID → Application type **Desktop app**.\n"
                "**5.** Note the `client_id` and `client_secret` shown —\n"
                "    you'll paste them in Step 3.\n"
            ),
        ),
        GuidePage(
            title="Step 2 / 3 — Get the refresh token",
            body=(
                "> Use Google's OAuth Playground to exchange the client\n"
                "> credentials for a long-lived refresh token.\n\n"
                "**1.** Open https://developers.google.com/oauthplayground\n"
                "**2.** Gear icon (top-right) → enable\n"
                "    **Use your own OAuth credentials** → paste `client_id`\n"
                "    and `client_secret` from Step 1.\n"
                "**3.** Left panel → **Drive API v3** → tick\n"
                "    `https://www.googleapis.com/auth/drive`.\n"
                "**4.** **Authorize APIs** → log in → allow.\n"
                "**5.** **Exchange authorization code for tokens**.\n"
                "**6.** Copy the `refresh_token` value (long string).\n"
            ),
        ),
        GuidePage(
            title="Step 3 / 3 — Link to the bot",
            body=(
                "> Paste all three values in a single message. The bot\n"
                "> encrypts them with Fernet and deletes your message.\n\n"
                "Tap **📝 Paste / update credentials** below, then send:\n"
                "```\n"
                "<refresh_token>\n"
                "<client_id>\n"
                "<client_secret>\n"
                "```\n"
                "One value per line, in that exact order.\n\n"
                "Verify the link afterwards with **🔌 Test connection**."
            ),
        ),
        _trouble_page(
            "Google Drive",
            [
                (
                    "`invalid_grant` / Token expired",
                    "Google invalidated the refresh token (happens after 6 "
                    "months of inactivity, password change, or revoked "
                    "access). Re-run Step 2 in OAuth Playground to mint a "
                    "fresh `refresh_token`, then paste the three values "
                    "again.",
                ),
                (
                    "`storageQuotaExceeded`",
                    "Your Drive is full. Either free up space in the "
                    "Google account, empty the Drive Trash (files there "
                    "still count against quota), or switch to a different "
                    "Drive account. Workspace accounts may need an admin "
                    "to lift a shared-drive quota.",
                ),
                (
                    "`403 rateLimitExceeded` / `userRateLimitExceeded`",
                    "Drive API quota hit on the OAuth project. Open the "
                    "Cloud Console → APIs & Services → Quotas, search for "
                    "**Drive**, and request a higher per-user quota. For "
                    "bursty uploads, the bot auto-retries with backoff — "
                    "you usually don't need to do anything.",
                ),
                (
                    "Scope mismatch / `insufficientPermissions`",
                    "The OAuth flow was completed with a narrower scope "
                    "than `drive`. Re-run Step 2 and make sure the "
                    "`https://www.googleapis.com/auth/drive` checkbox is "
                    "ticked before authorising.",
                ),
                (
                    "`File not found` on a shared drive folder",
                    "Shared-drive folders need the `supportsAllDrives` "
                    "flag. The bot already sends it for uploads, but the "
                    "OAuth account must be a **member** of the shared "
                    "drive with at least Contributor rights.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Rclone — 3 pages (install, rclone config, paste)
# ---------------------------------------------------------------------------
_RCLONE = DestinationGuide(
    provider_id="rclone",
    display_name="Rclone",
    summary=(
        "Universal uploader (70+ cloud backends). Needs a local rclone\n"
        "install to generate the config, then paste config + remote name."
    ),
    required_values=["config", "remote"],
    pages=[
        GuidePage(
            title="Step 1 / 3 — Install rclone locally",
            body=(
                "> rclone needs to run on your own machine once to produce\n"
                "> the config; the bot itself does not generate it for you.\n\n"
                "**macOS / Linux:**\n"
                "```\n"
                "curl https://rclone.org/install.sh | sudo bash\n"
                "```\n"
                "**Windows:** download the binary from\n"
                "https://rclone.org/downloads and unzip it.\n\n"
                "Check the install:\n"
                "```\n"
                "rclone version\n"
                "```\n"
            ),
        ),
        GuidePage(
            title="Step 2 / 3 — Create a remote",
            body=(
                "> Run the interactive wizard to configure the backend\n"
                "> you want to upload to (Drive, S3, OneDrive, …).\n\n"
                "```\n"
                "rclone config\n"
                "```\n"
                "**1.** `n` → new remote.\n"
                "**2.** Pick a name, e.g. `mydrive` — remember it.\n"
                "**3.** Pick the storage type (list shown in prompt).\n"
                "**4.** Follow the per-backend instructions (most flows\n"
                "    open a browser for OAuth).\n"
                "**5.** `q` → quit when done.\n\n"
                "Show the resulting config:\n"
                "```\n"
                "rclone config show\n"
                "```\n"
            ),
        ),
        GuidePage(
            title="Step 3 / 3 — Link to the bot",
            body=(
                "> Paste the config + the remote name in one message.\n\n"
                "Tap **📝 Paste / update credentials** below, then send:\n"
                "```\n"
                "<full rclone.conf contents>\n"
                "---\n"
                "<remote name from step 2, e.g. mydrive>\n"
                "```\n"
                "Separate the config block and the remote name with a\n"
                "single line containing exactly `---`.\n\n"
                "Verify with **🔌 Test connection**."
            ),
        ),
        _trouble_page(
            "Rclone",
            [
                (
                    "`rclone: not found` on the host",
                    "The bot's host doesn't have the rclone binary "
                    "installed — that's an admin-level issue, not a user "
                    "one. Ask the admin to install it with the one-liner "
                    "from Step 1, or pick a different destination.",
                ),
                (
                    "`Failed to load config` / parse error",
                    "The pasted `rclone.conf` is malformed. Re-run "
                    "`rclone config show` locally and copy the output "
                    "verbatim — don't hand-edit it. Common pitfalls: "
                    "Windows CRLF line-endings and missing the `[name]` "
                    "section header.",
                ),
                (
                    "`remote <name> not found`",
                    "The remote name in the second block doesn't match "
                    "any `[section]` in the pasted config. Re-paste using "
                    "the exact name you chose in `rclone config` (case-"
                    "sensitive), the one shown in `rclone listremotes`.",
                ),
                (
                    "`oauth2: token expired` / `AuthError`",
                    "The backend's OAuth token is stale. Run `rclone "
                    "config reconnect <name>:` locally, re-export with "
                    "`rclone config show`, and paste the refreshed "
                    "config into the bot.",
                ),
                (
                    "Upload hangs / very slow",
                    "Increase concurrency by adding `--transfers 4 "
                    "--checkers 8` on the backend side, or pick a closer "
                    "endpoint region. For large files, rclone does "
                    "chunked multipart automatically — no bot-side knob.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# MEGA.nz — 1 page (email + password)
# ---------------------------------------------------------------------------
_MEGA = DestinationGuide(
    provider_id="mega",
    display_name="MEGA.nz",
    summary=(
        "End-to-end encrypted cloud storage. Needs your MEGA account\n"
        "email + password."
    ),
    required_values=["email", "password"],
    pages=[
        GuidePage(
            title="Link your MEGA account",
            body=(
                "> The bot logs in as you via MEGA's SDK. Credentials are\n"
                "> stored Fernet-encrypted — never in plain text.\n\n"
                "**1.** Make sure you have a MEGA account at\n"
                "    https://mega.nz (free plan is fine).\n"
                "**2.** Tap **📝 Paste / update credentials** below.\n"
                "**3.** Send the email + password in one message:\n"
                "```\n"
                "<email>\n"
                "<password>\n"
                "```\n"
                "**4.** Verify with **🔌 Test connection**.\n\n"
                "**Security tip:** if you reuse this password elsewhere,\n"
                "consider creating a dedicated MEGA sub-account instead."
            ),
        ),
        _trouble_page(
            "MEGA.nz",
            [
                (
                    "`EACCESS` / Login failed (wrong credentials)",
                    "Triple-check the email and password, watching for "
                    "trailing whitespace. If the account has 2FA enabled "
                    "the plain password won't work — MEGA's SDK needs an "
                    "**app-specific password**. Generate one under "
                    "https://mega.nz → Settings → Security → Session "
                    "Management.",
                ),
                (
                    "`ETOOMANY` / Temporary IP ban",
                    "MEGA bans an IP for up to an hour after repeated "
                    "failed logins. Wait ~60 minutes, fix the credentials, "
                    "then retry. The bot will not keep hammering — it "
                    "aborts after the first EACCESS.",
                ),
                (
                    "`EOVERQUOTA` / Storage full",
                    "Your MEGA quota is exhausted. Free tier caps at 20 "
                    "GB, paid tiers go higher. Either upgrade, move "
                    "uploads to another destination, or clear the "
                    "**Rubbish Bin** — deleted files in the Bin still "
                    "count against quota until emptied.",
                ),
                (
                    "Upload stalls at 99%",
                    "MEGA finalises large files on the server side and "
                    "occasionally takes 30–60 s after the last chunk. If "
                    "the task status keeps showing 99% for more than 2 "
                    "minutes, cancel and retry — usually a transient "
                    "MEGA-side issue.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# GoFile — 1 page (optional API token)
# ---------------------------------------------------------------------------
_GOFILE = DestinationGuide(
    provider_id="gofile",
    display_name="GoFile",
    summary=(
        "Free file host. Anonymous upload works out of the box; add a\n"
        "token to have uploads land in your GoFile account."
    ),
    required_values=["token (optional)"],
    pages=[
        GuidePage(
            title="Link your GoFile account (optional)",
            body=(
                "> You can skip this entirely — GoFile accepts anonymous\n"
                "> uploads. Only link a token if you want your files to\n"
                "> appear in your GoFile dashboard.\n\n"
                "**1.** Sign in at https://gofile.io → **My Profile**.\n"
                "**2.** Copy the **API Token**.\n"
                "**3.** Tap **📝 Paste / update credentials** below.\n"
                "**4.** Send the token as a single line:\n"
                "```\n"
                "<api_token>\n"
                "```\n"
                "**5.** Verify with **🔌 Test connection**.\n"
            ),
        ),
        _trouble_page(
            "GoFile",
            [
                (
                    "`server not found` / `upload server error`",
                    "GoFile rotates its upload servers frequently. The "
                    "bot auto-retries against `store1` as a fallback when "
                    "the primary server fails. If every server fails at "
                    "once, it's a GoFile-side outage — check "
                    "https://status.gofile.io before retrying.",
                ),
                (
                    "`invalid token` / unauthorized",
                    "The API token was revoked or regenerated. Sign into "
                    "gofile.io → **My Profile** and copy the **current** "
                    "token — tokens shown on the profile page are always "
                    "the active ones. Re-paste into the bot.",
                ),
                (
                    "Upload succeeds but file not in my dashboard",
                    "You uploaded anonymously. GoFile only attaches "
                    "files to your dashboard when a valid account token "
                    "is linked — re-run Step 3 with the token, the next "
                    "upload will show up.",
                ),
                (
                    "File disappears a few days later",
                    "Anonymous files on GoFile auto-expire. Attach a "
                    "token to keep uploads tied to your account; that "
                    "raises the retention window to match your GoFile "
                    "plan.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Pixeldrain — 1 page (API key)
# ---------------------------------------------------------------------------
_PIXELDRAIN = DestinationGuide(
    provider_id="pixeldrain",
    display_name="Pixeldrain",
    summary=(
        "Fast file host (EU-hosted). Anonymous upload works; add an API\n"
        "key to have uploads attached to your account."
    ),
    required_values=["api_key (optional)"],
    pages=[
        GuidePage(
            title="Link your Pixeldrain account (optional)",
            body=(
                "> Skip this if you don't mind anonymous uploads.\n\n"
                "**1.** Sign in at https://pixeldrain.com → **User Settings**\n"
                "    → **API keys**.\n"
                "**2.** Create a new API key and copy it.\n"
                "**3.** Tap **📝 Paste / update credentials** below.\n"
                "**4.** Send the API key as a single line:\n"
                "```\n"
                "<api_key>\n"
                "```\n"
                "**5.** Verify with **🔌 Test connection**.\n"
            ),
        ),
        _trouble_page(
            "Pixeldrain",
            [
                (
                    "`rate-limit exceeded`",
                    "Pixeldrain applies per-IP rate limits to anonymous "
                    "uploads. Linking an API key raises your ceiling "
                    "significantly — if you upload often, the key is "
                    "worth the one-minute setup.",
                ),
                (
                    "`file too large` / rejected",
                    "Each Pixeldrain tier has its own per-file cap. "
                    "Check your tier at "
                    "https://pixeldrain.com/user/subscriptions — the "
                    "free plan is capped at a few GB per file. Split "
                    "large uploads or pick a different destination.",
                ),
                (
                    "`unauthorized` when pasting a new API key",
                    "Pixeldrain API keys are 32-char hex strings. Make "
                    "sure you copied the full value (without the "
                    "surrounding whitespace the UI sometimes adds). "
                    "Generate a new key if in doubt.",
                ),
                (
                    "Uploaded but link returns 404",
                    "Pixeldrain occasionally needs a few seconds to "
                    "propagate new file entries through their CDN. If "
                    "the 404 persists after 60 s, re-run the upload — "
                    "the previous attempt may have been aborted server-"
                    "side without the bot noticing.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Telegram — 1 page (DM vs channel)
# ---------------------------------------------------------------------------
_TELEGRAM = DestinationGuide(
    provider_id="telegram",
    display_name="Telegram (DM / channel)",
    summary=(
        "Deliver finished uploads straight back to you in DM, or to a\n"
        "channel you own. No credentials needed — the bot uses its own\n"
        "session."
    ),
    required_values=["chat_id (optional)"],
    pages=[
        GuidePage(
            title="Pick a Telegram destination",
            body=(
                "> Default is **DM to you**. You only need to set a\n"
                "> `chat_id` if you want uploads pushed to a channel or\n"
                "> group instead.\n\n"
                "**DM (default):** nothing to do — uploads arrive in this\n"
                "chat.\n\n"
                "**Channel / group:**\n"
                "**1.** Add the bot to the channel as an **admin** with\n"
                "    `Post Messages` permission.\n"
                "**2.** Forward any message from that channel to @RawDataBot\n"
                "    (or @JsonDumpBot) and copy the `chat.id` it shows\n"
                "    — a negative integer like `-1001234567890`.\n"
                "**3.** Tap **📝 Paste / update credentials** below.\n"
                "**4.** Send the chat id on a single line:\n"
                "```\n"
                "-1001234567890\n"
                "```\n"
                "**5.** Verify with **🔌 Test connection**.\n"
            ),
        ),
        _trouble_page(
            "Telegram",
            [
                (
                    "`CHAT_WRITE_FORBIDDEN`",
                    "The bot isn't an admin in the target channel, or "
                    "the `Post Messages` permission was revoked. Go to "
                    "the channel → **Administrators** → promote the bot "
                    "(or toggle Post Messages back on).",
                ),
                (
                    "`PEER_ID_INVALID` / `CHAT_ID_INVALID`",
                    "The `chat_id` doesn't point to a chat the bot can "
                    "see. Common causes: typo, forgotten leading `-100`, "
                    "or the bot was removed from the chat. Re-forward a "
                    "message via @RawDataBot and copy `chat.id` "
                    "verbatim.",
                ),
                (
                    "`FILE_TOO_LARGE` on DM delivery",
                    "Standard Telegram bot API caps outgoing files at 2 "
                    "GB (4 GB with Premium via the Userbot tunnel). Set "
                    "up **𝕏TV Pro™** in `/settings → Admin` to unlock "
                    "the 4 GB path, or pick a non-Telegram destination "
                    "for >2 GB files.",
                ),
                (
                    "`SLOWMODE_WAIT_X` on a channel",
                    "The target channel has slow-mode enabled. The bot "
                    "waits out the cooldown automatically, but the "
                    "upload will appear delayed. Either disable slow-"
                    "mode for the bot (channel admins can exempt bots) "
                    "or accept the spacing.",
                ),
                (
                    "Thumbnail is wrong / missing",
                    "Telegram strips metadata below a size threshold and "
                    "may pick an arbitrary frame for videos. The bot "
                    "relies on Telegram's auto-thumbnail — there's no "
                    "knob here. For critical thumbnails, upload a still "
                    "image separately as a caption.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Dropbox — 3 pages (app console, refresh token, paste) + troubleshooting
# ---------------------------------------------------------------------------
_DROPBOX = DestinationGuide(
    provider_id="dropbox",
    display_name="Dropbox",
    summary=(
        "OAuth-based upload to your own Dropbox. "
        "Needs three values: refresh_token, app_key, app_secret."
    ),
    required_values=["refresh_token", "app_key", "app_secret"],
    pages=[
        GuidePage(
            title="Step 1 / 3 — Create a Dropbox app",
            body=(
                "> Register a scoped app on Dropbox's developer console so\n"
                "> the bot gets its own `app_key` and `app_secret`.\n\n"
                "**1.** Open https://www.dropbox.com/developers/apps\n"
                "**2.** **Create app** → choose **Scoped access**.\n"
                "**3.** Access type: **Full Dropbox** (or **App folder**\n"
                "    for sandboxed uploads).\n"
                "**4.** Pick a unique app name.\n"
                "**5.** In the app's **Permissions** tab, enable\n"
                "    `files.content.write` and `files.content.read`\n"
                "    (plus `sharing.write` if you want shared links).\n"
                "    Press **Submit** at the bottom.\n"
                "**6.** The **Settings** tab shows `App key` and\n"
                "    `App secret` — you'll paste them in Step 3.\n"
            ),
        ),
        GuidePage(
            title="Step 2 / 3 — Get the refresh token",
            body=(
                "> Dropbox refresh tokens are minted by exchanging a\n"
                "> one-time authorization code. rclone automates this.\n\n"
                "**Easiest path — via rclone:**\n"
                "```\n"
                "rclone authorize \"dropbox\" \"<app_key>\" \"<app_secret>\"\n"
                "```\n"
                "A browser opens; after **Allow** you'll see a JSON blob\n"
                "containing `refresh_token` (and `access_token` — ignore).\n\n"
                "**Manual path** (no rclone): follow\n"
                "https://developers.dropbox.com/oauth-guide with\n"
                "`token_access_type=offline` and exchange the returned\n"
                "`code` against `/oauth2/token` for a `refresh_token`.\n"
            ),
        ),
        GuidePage(
            title="Step 3 / 3 — Link to the bot",
            body=(
                "> Paste all three values in a single message. The bot\n"
                "> encrypts them with Fernet and deletes your message.\n\n"
                "Tap **📝 Paste / update credentials** below, then send:\n"
                "```\n"
                "<refresh_token>\n"
                "<app_key>\n"
                "<app_secret>\n"
                "```\n"
                "One value per line, in that exact order.\n\n"
                "Verify the link afterwards with **🔌 Test connection** —\n"
                "the bot replies `linked as <your name>` on success."
            ),
        ),
        _trouble_page(
            "Dropbox",
            [
                (
                    "`invalid_grant` / `expired_refresh_token`",
                    "The refresh token was revoked (password change, app "
                    "removed from connected-apps, or manually regenerated "
                    "app secret). Re-run Step 2 to mint a new one and "
                    "paste the three values again.",
                ),
                (
                    "`missing_scope` / `insufficient_permissions`",
                    "The Dropbox app doesn't have the right permission "
                    "scopes. Open the app in Dropbox's developer console, "
                    "enable `files.content.write` + `files.content.read` "
                    "(and `sharing.write` for shared links), press Submit, "
                    "then re-run Step 2 — scopes are baked into the "
                    "refresh token.",
                ),
                (
                    "`path/conflict/file`",
                    "A file with the same name already exists at the "
                    "destination. The bot uploads in overwrite mode, so "
                    "this usually means two concurrent uploads collided. "
                    "Wait a few seconds and retry.",
                ),
                (
                    "`upload.write_failed` on large files",
                    "A resumable chunk failed mid-upload. The bot doesn't "
                    "auto-resume across restarts for Dropbox — just "
                    "re-queue the upload. For repeatable failures, check "
                    "free quota in the Dropbox account.",
                ),
                (
                    "Shared link shows `dropbox://…`",
                    "The app lacks `sharing.write` and the bot fell back "
                    "to a path-style reference. Add the scope in the app "
                    "console, re-mint the refresh token, and re-link.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# OneDrive — 3 pages (Azure app, refresh token, paste) + troubleshooting
# ---------------------------------------------------------------------------
_ONEDRIVE = DestinationGuide(
    provider_id="onedrive",
    display_name="OneDrive",
    summary=(
        "Microsoft Graph upload to your own OneDrive. "
        "Needs three values: refresh_token, client_id, tenant."
    ),
    required_values=["refresh_token", "client_id", "tenant"],
    pages=[
        GuidePage(
            title="Step 1 / 3 — Register an Azure app",
            body=(
                "> The Graph API needs an app registration in Entra ID\n"
                "> (Azure AD) so the bot can sign in on your behalf.\n\n"
                "**1.** Open https://entra.microsoft.com → **Identity** →\n"
                "    **Applications** → **App registrations**.\n"
                "**2.** **New registration** → pick a name.\n"
                "**3.** Supported account types:\n"
                "    • *Personal Microsoft accounts* → tenant = `common`\n"
                "    • *Your organization only* → tenant = directory id\n"
                "**4.** Redirect URI → **Public client / native** →\n"
                "    `http://localhost`.\n"
                "**5.** **Register**. Copy the **Application (client) ID** —\n"
                "    that's `client_id` for Step 3.\n"
                "**6.** **API permissions** → **Add a permission** →\n"
                "    Microsoft Graph → **Delegated permissions** →\n"
                "    enable `Files.ReadWrite` and `offline_access`.\n"
            ),
        ),
        GuidePage(
            title="Step 2 / 3 — Get the refresh token",
            body=(
                "> MSAL's refresh-token flow is easiest to drive through\n"
                "> rclone, which speaks the same OAuth 2.0 authorization-\n"
                "> code dance the bot needs.\n\n"
                "**Easiest path — via rclone:**\n"
                "```\n"
                "rclone authorize \"onedrive\"\n"
                "```\n"
                "Pick **OneDrive Personal** or **OneDrive for Business**\n"
                "when prompted, paste the `client_id` from Step 1, then\n"
                "allow in the browser. The JSON blob it prints contains\n"
                "`refresh_token`.\n\n"
                "**Manual path:** hit `https://login.microsoftonline.com/\n"
                "<tenant>/oauth2/v2.0/authorize` with\n"
                "`scope=Files.ReadWrite%20offline_access` and exchange the\n"
                "returned `code` against `/oauth2/v2.0/token`.\n"
            ),
        ),
        GuidePage(
            title="Step 3 / 3 — Link to the bot",
            body=(
                "> Paste all three values in a single message. The bot\n"
                "> encrypts them with Fernet and deletes your message.\n\n"
                "Tap **📝 Paste / update credentials** below, then send:\n"
                "```\n"
                "<refresh_token>\n"
                "<client_id>\n"
                "<tenant>\n"
                "```\n"
                "One value per line, in that exact order.\n\n"
                "Use `common` as `tenant` for personal Microsoft accounts;\n"
                "for org accounts paste the directory (tenant) ID.\n\n"
                "Verify afterwards with **🔌 Test connection** — the bot\n"
                "replies with the remaining OneDrive free space on success."
            ),
        ),
        _trouble_page(
            "OneDrive",
            [
                (
                    "`AADSTS70008` / `refresh token is expired`",
                    "Personal-account refresh tokens expire after 90 days "
                    "of inactivity; org tokens can be revoked by admin "
                    "policy sooner. Re-run Step 2 and paste the new "
                    "values — no need to recreate the Azure app.",
                ),
                (
                    "`AADSTS65001` / `consent required`",
                    "The app is missing a permission the scope requests. "
                    "In Azure → API permissions, grant admin consent for "
                    "`Files.ReadWrite` and `offline_access`, then re-run "
                    "Step 2 so the new scopes end up in the token.",
                ),
                (
                    "`AADSTS700016` / `application not found`",
                    "Wrong `client_id` or the Azure app was deleted. "
                    "Verify the **Application (client) ID** in Azure's "
                    "app overview and re-paste.",
                ),
                (
                    "`quotaLimitReached`",
                    "OneDrive free plans cap at 5 GB; paid plans at 1 TB. "
                    "The bot surfaces free space in **🔌 Test connection**. "
                    "Clear space or move to a different account — there's "
                    "no bot-side workaround.",
                ),
                (
                    "Uploads stall on files > 4 MB",
                    "The upload-session endpoint requires chunks that are "
                    "a multiple of 320 KiB. The bot already uses 10 MiB "
                    "chunks. If stalls persist, check that no corporate "
                    "proxy is stripping `Content-Range` headers.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Box — 3 pages (custom app, refresh token, paste) + troubleshooting
# ---------------------------------------------------------------------------
_BOX = DestinationGuide(
    provider_id="box",
    display_name="Box",
    summary=(
        "OAuth-based upload to your own Box account. "
        "Needs three values: refresh_token, client_id, client_secret."
    ),
    required_values=["refresh_token", "client_id", "client_secret"],
    pages=[
        GuidePage(
            title="Step 1 / 3 — Create a Box custom app",
            body=(
                "> Box calls its OAuth apps *Custom Apps*; you create one\n"
                "> on the Box developer console.\n\n"
                "**1.** Open https://app.box.com/developers/console\n"
                "**2.** **Create New App** → **Custom App**.\n"
                "**3.** Authentication method → **User Authentication\n"
                "    (OAuth 2.0)**.\n"
                "**4.** Pick a unique app name → **Create App**.\n"
                "**5.** In the app's **Configuration** tab:\n"
                "    • Redirect URI → `http://localhost`\n"
                "    • Application Scopes → tick **Write all files** and\n"
                "      **Read all files**.\n"
                "    • Save changes.\n"
                "**6.** Copy **Client ID** and **Client Secret** — you'll\n"
                "    paste them in Step 3.\n"
            ),
        ),
        GuidePage(
            title="Step 2 / 3 — Get the refresh token",
            body=(
                "> Box rotates refresh tokens on every refresh. The bot\n"
                "> persists rotated tokens automatically, so you only\n"
                "> have to mint one refresh token here.\n\n"
                "**Easiest path — via rclone:**\n"
                "```\n"
                "rclone authorize \"box\"\n"
                "```\n"
                "Paste the `client_id` and `client_secret` from Step 1 when\n"
                "prompted, then allow in the browser. The JSON blob it\n"
                "prints contains `refresh_token`.\n\n"
                "**Manual path:** navigate to\n"
                "`https://account.box.com/api/oauth2/authorize` with\n"
                "`response_type=code&client_id=<id>&redirect_uri=\n"
                "http://localhost`, exchange the returned `code` against\n"
                "`/api/oauth2/token` for a refresh token.\n"
            ),
        ),
        GuidePage(
            title="Step 3 / 3 — Link to the bot",
            body=(
                "> Paste all three values in a single message. The bot\n"
                "> encrypts them with Fernet and deletes your message.\n\n"
                "Tap **📝 Paste / update credentials** below, then send:\n"
                "```\n"
                "<refresh_token>\n"
                "<client_id>\n"
                "<client_secret>\n"
                "```\n"
                "One value per line, in that exact order.\n\n"
                "Verify afterwards with **🔌 Test connection** — the bot\n"
                "replies `linked as <your@email>` on success.\n\n"
                "Uploads land in **All Files** by default. Set a different\n"
                "folder id later via the provider's config screen."
            ),
        ),
        _trouble_page(
            "Box",
            [
                (
                    "`invalid_grant` after days of silence",
                    "Box's rotating refresh tokens expire after 60 days "
                    "of inactivity. The bot normally rotates them on "
                    "every upload; if uploads haven't happened in a "
                    "while, re-run Step 2 and paste the new values.",
                ),
                (
                    "`insufficient_scope` / can't upload",
                    "The custom app is missing a permission. Open the "
                    "app in Box's developer console → Configuration → "
                    "Application Scopes, tick **Write all files** + "
                    "**Read all files**, save, then re-run Step 2 so "
                    "the new scopes end up in the token.",
                ),
                (
                    "Custom app pending admin approval",
                    "Enterprise Box accounts default to admin approval "
                    "for new custom apps. Ask a Box admin to authorise "
                    "the app under **Admin Console → Apps → Custom "
                    "Apps**, then re-run Step 2.",
                ),
                (
                    "`item_name_in_use`",
                    "A file with the same name already exists in the "
                    "destination folder. Box doesn't auto-overwrite — "
                    "either pick a different `folder_id` in the provider "
                    "config, rename the source file, or delete the "
                    "existing one.",
                ),
                (
                    "Shared link shows the Box file URL instead",
                    "The app lacks the shared-link permission. Enable "
                    "`Generate share links` on the app's Configuration "
                    "tab, save, then re-run Step 2.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# S3 (generic) — 3 pages (pick backend, credentials, paste) + troubleshooting
# ---------------------------------------------------------------------------
_S3 = DestinationGuide(
    provider_id="s3",
    display_name="S3-compatible",
    summary=(
        "One uploader for AWS S3, Wasabi, Cloudflare R2, MinIO, iDrive "
        "e2, Storj S3 Gateway, and anything else speaking the S3 API."
    ),
    required_values=["endpoint_url", "region", "bucket", "access_key", "secret_key"],
    pages=[
        GuidePage(
            title="Step 1 / 3 — Pick a backend and bucket",
            body=(
                "> You'll need one S3-compatible bucket. The endpoint and\n"
                "> region values depend on the provider.\n\n"
                "**AWS S3** — console.aws.amazon.com/s3\n"
                "    endpoint: `https://s3.<region>.amazonaws.com`\n"
                "**Wasabi** — console.wasabisys.com/#/file_manager\n"
                "    endpoint: `https://s3.<region>.wasabisys.com`\n"
                "**Cloudflare R2** — dash.cloudflare.com → R2\n"
                "    endpoint: `https://<account>.r2.cloudflarestorage.com`\n"
                "    region: `auto`\n"
                "**Backblaze B2 (S3 API)** — secure.backblaze.com → Buckets\n"
                "    endpoint: `https://s3.<region>.backblazeb2.com`\n"
                "**MinIO (self-hosted)** — whatever URL you serve MinIO on\n"
                "**iDrive e2** — idrivee2.com → Buckets\n"
                "    endpoint: `https://<region>.e2.idrivee2.com`\n\n"
                "Create the bucket in the provider's console before\n"
                "continuing — the bot doesn't auto-create buckets."
            ),
        ),
        GuidePage(
            title="Step 2 / 3 — Generate access credentials",
            body=(
                "> Every S3-compatible provider uses the same two values:\n"
                "> an **access key** and a **secret key**. Names for the\n"
                "> creation screen differ, though.\n\n"
                "**AWS** — IAM → Users → **Create access key** → use case\n"
                "    `Third-party service`. Attach a policy limiting the\n"
                "    key to just the target bucket (least privilege).\n"
                "**Wasabi** — Access Keys → **Create New Access Key**.\n"
                "**Cloudflare R2** → Manage R2 API Tokens → **Create API\n"
                "    token**. Scope = *Object Read & Write*, restrict to\n"
                "    the one bucket. R2 shows both keys once — save them.\n"
                "**Backblaze B2 (S3 API)** — App Keys → **Add a New\n"
                "    Application Key**. The *keyID* is the access_key,\n"
                "    the *applicationKey* is the secret_key.\n"
                "**MinIO** — Access Keys → Create. Or use the `mc admin\n"
                "    user add` CLI.\n"
                "**iDrive e2** — Access Keys → Create.\n"
            ),
        ),
        GuidePage(
            title="Step 3 / 3 — Link to the bot",
            body=(
                "> Paste all values as `key: value` lines in a single\n"
                "> message. The bot encrypts access_key + secret_key with\n"
                "> Fernet and deletes your message.\n\n"
                "Tap **📝 Paste / update credentials** below, then send:\n"
                "```\n"
                "endpoint: https://s3.eu-central-1.wasabisys.com\n"
                "region: eu-central-1\n"
                "bucket: mybucket\n"
                "access_key: AKIA...\n"
                "secret_key: wJalrXUt...\n"
                "prefix: optional/sub/path\n"
                "```\n"
                "`prefix` is optional — every uploaded file lands under it\n"
                "if set. `endpoint` is optional for AWS (gets inferred from\n"
                "`region`).\n\n"
                "Verify with **🔌 Test connection** — the bot does a\n"
                "HEAD on the bucket and replies `bucket ok: <name>`."
            ),
        ),
        _trouble_page(
            "S3-compatible",
            [
                (
                    "`SignatureDoesNotMatch`",
                    "secret_key typo, or the key rotates trailing whitespace. "
                    "Re-copy from the provider console paying attention to "
                    "any `+` / `/` characters, and make sure no shell auto-"
                    "escaped them.",
                ),
                (
                    "`AccessDenied` on `head_bucket`",
                    "The key is valid but doesn't have `s3:ListBucket` or "
                    "`s3:GetBucketLocation`. Broaden the IAM policy (or for "
                    "R2, widen the token scope to the target bucket).",
                ),
                (
                    "`NoSuchBucket`",
                    "Bucket doesn't exist in the region you specified. "
                    "Either create it in the provider console, fix the "
                    "`bucket` value, or switch `region` to the bucket's "
                    "actual region.",
                ),
                (
                    "Cloudflare R2 rejects uploads",
                    "R2 ignores `region` and requires `region: auto`. Also "
                    "make sure the endpoint uses your R2 account id, not "
                    "the generic `r2.cloudflarestorage.com` host.",
                ),
                (
                    "MinIO self-signed cert errors",
                    "boto3 verifies TLS by default. Either put a valid "
                    "cert in front of MinIO, or add a reverse proxy that "
                    "terminates TLS cleanly. Disabling verification is "
                    "not exposed as a knob in the bot on purpose.",
                ),
                (
                    "Files upload but return no usable URL",
                    "Private buckets return a canonical URL that isn't "
                    "publicly accessible. Either flip the bucket to public-"
                    "read, put a CDN in front, or implement signed URLs in "
                    "a downstream workflow.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Backblaze B2 (native) — 2 pages (app key, paste) + troubleshooting
# ---------------------------------------------------------------------------
_B2 = DestinationGuide(
    provider_id="b2",
    display_name="Backblaze B2 (native)",
    summary=(
        "Native B2 SDK — pick this over the S3 endpoint for B2-specific "
        "features like app-key capability info and hash verification."
    ),
    required_values=["app_key_id", "app_key", "bucket"],
    pages=[
        GuidePage(
            title="Step 1 / 2 — Create a B2 app key",
            body=(
                "> B2 app keys are scoped and restrictable — you can pin\n"
                "> one key to a single bucket with specific capabilities.\n\n"
                "**1.** Open https://secure.backblaze.com/app_keys.htm\n"
                "**2.** **Add a New Application Key**.\n"
                "**3.** Name the key (shows up in audit logs).\n"
                "**4.** **Allow access to Bucket:** pick the bucket you\n"
                "    want the bot to upload to. *Restricting to one bucket\n"
                "    is recommended* — a leaked key can only harm that one.\n"
                "**5.** **Type of Access:** **Read and Write** (the bot\n"
                "    needs both so it can hash-verify uploads after the\n"
                "    fact via `b2_get_file_info`).\n"
                "**6.** File name prefix / duration — leave empty unless\n"
                "    you want extra limits.\n"
                "**7.** **Create New Key**. Backblaze shows the `keyID`\n"
                "    and `applicationKey` **once** — copy both now.\n"
            ),
        ),
        GuidePage(
            title="Step 2 / 2 — Link to the bot",
            body=(
                "> Paste as `key: value` lines in a single message. The\n"
                "> bot encrypts app_key_id + app_key with Fernet and\n"
                "> deletes your message.\n\n"
                "Tap **📝 Paste / update credentials** below, then send:\n"
                "```\n"
                "app_key_id: 005a1b2c3d...\n"
                "app_key: K005f6g7h...\n"
                "bucket: mybucket\n"
                "prefix: optional/sub/path\n"
                "```\n"
                "`prefix` is optional.\n\n"
                "Verify with **🔌 Test connection** — the bot resolves the\n"
                "bucket by name and replies `bucket ok: <name>` on success.\n"
                "Resolution failures usually mean the app key is scoped to\n"
                "a different bucket."
            ),
        ),
        _trouble_page(
            "Backblaze B2",
            [
                (
                    "`unauthorized` on `authorize_account`",
                    "keyID or applicationKey is wrong, or the key was "
                    "deleted in the B2 console. Create a fresh key (the "
                    "applicationKey value is only shown once) and re-paste.",
                ),
                (
                    "`bad_request` / `caps exceeded`",
                    "App key doesn't include `writeFiles` + `readFiles`. "
                    "Create a new key with **Read and Write** access — "
                    "you can't grow capabilities on an existing key.",
                ),
                (
                    "`bucket_name_not_found`",
                    "Either the bucket name is wrong, or the app key is "
                    "restricted to a different bucket. Match them up in "
                    "the B2 console's **App Keys** tab.",
                ),
                (
                    "Slow uploads past 100 MB",
                    "B2 SDK's default upload concurrency is conservative. "
                    "For speed-critical users, consider switching to the "
                    "generic S3 uploader pointed at the B2 S3 endpoint — "
                    "boto3's multipart-upload code is more aggressive.",
                ),
                (
                    "Download URL returns `not_authorized`",
                    "The bucket is private. B2 public-readability is a "
                    "per-bucket flag — flip the bucket to Public in the "
                    "B2 console if you want the returned URLs to serve "
                    "directly without extra auth.",
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
GUIDES: dict[str, DestinationGuide] = {
    "gdrive": _GDRIVE,
    "rclone": _RCLONE,
    "mega": _MEGA,
    "gofile": _GOFILE,
    "pixeldrain": _PIXELDRAIN,
    "telegram": _TELEGRAM,
    "dropbox": _DROPBOX,
    "onedrive": _ONEDRIVE,
    "box": _BOX,
    "s3": _S3,
    "b2": _B2,
    # Intentionally no "ddl" entry: DDL is host-admin-only (env var based);
    # when it's available the user has nothing to configure, and when it
    # isn't available it's already hidden from the public settings menu.
}


def get_guide(provider_id: str) -> DestinationGuide | None:
    """Return the guide for `provider_id`, or None if none exists."""
    return GUIDES.get(provider_id)

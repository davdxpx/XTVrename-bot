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
    # Intentionally no "ddl" entry: DDL is host-admin-only (env var based);
    # when it's available the user has nothing to configure, and when it
    # isn't available it's already hidden from the public settings menu.
}


def get_guide(provider_id: str) -> DestinationGuide | None:
    """Return the guide for `provider_id`, or None if none exists."""
    return GUIDES.get(provider_id)

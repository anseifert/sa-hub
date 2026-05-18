"""
Slack service - plug-in ready for when IT approves the app.

To set up:
1. Go to https://api.slack.com/apps and create a new app
2. Request the following Bot Token Scopes:
   - channels:history
   - channels:read
   - groups:history
   - im:history
   - mpim:history
   - users:read
3. Install to your workspace (requires admin approval for corporate Slack)
4. Add SLACK_BOT_TOKEN to your .env
"""
import os
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import SyncLog

try:
    from slack_sdk.web.async_client import AsyncWebClient
    from slack_sdk.errors import SlackApiError
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False


async def is_connected() -> bool:
    return bool(os.getenv("SLACK_BOT_TOKEN")) and SLACK_AVAILABLE


async def fetch_recent_messages(db: AsyncSession, days_back: int = 7) -> str:
    """Fetch recent Slack messages for one-pager context."""
    if not await is_connected():
        return ""

    log = SyncLog(sync_type="slack", status="running", started_at=datetime.utcnow())
    db.add(log)
    await db.commit()

    try:
        client = AsyncWebClient(token=os.getenv("SLACK_BOT_TOKEN"))
        oldest = (datetime.utcnow() - timedelta(days=days_back)).timestamp()

        # Get list of channels the bot is in
        channels_response = await client.conversations_list(
            types="public_channel,private_channel",
            limit=50
        )
        channels = channels_response.get("channels", [])

        all_messages = []

        for channel in channels[:10]:  # limit channels for performance
            try:
                history = await client.conversations_history(
                    channel=channel["id"],
                    oldest=str(oldest),
                    limit=50
                )
                msgs = history.get("messages", [])
                for msg in msgs:
                    if msg.get("text") and not msg.get("bot_id"):
                        all_messages.append(
                            f"[#{channel['name']}] {msg.get('text', '')[:200]}"
                        )
            except SlackApiError:
                continue

        log.status = "success"
        log.message = f"Fetched messages from {len(channels)} channels"
        log.finished_at = datetime.utcnow()
        await db.commit()

        return "\n".join(all_messages[:100])

    except Exception as e:
        log.status = "error"
        log.message = str(e)
        log.finished_at = datetime.utcnow()
        await db.commit()
        return ""

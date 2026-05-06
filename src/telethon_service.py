"""
Telethon (MTProto user account) service: create groups, add members, promote admins.
Bots cannot create groups or promote; this uses a user session.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from telethon import TelegramClient
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    InviteToChannelRequest,
)
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.types import ChatAdminRights, InputUserEmpty

from .config_loader import (
    get_admins,
    get_members,
    get_welcome_message,
    username_for_telegram,
)

logger = logging.getLogger(__name__)

# Always invited and given admin on every group creation (all codes, including dynamic).
_DEFAULT_ADMIN_USERNAME = "realcryptomoses"


def _ensure_default_admin(members: List[str], admins: List[str]) -> Tuple[List[str], List[str]]:
    key = username_for_telegram(_DEFAULT_ADMIN_USERNAME)
    m = list(members)
    if key not in {username_for_telegram(x) for x in m}:
        m.append(_DEFAULT_ADMIN_USERNAME)
    a = list(admins)
    if key not in {username_for_telegram(x) for x in a}:
        a.append(_DEFAULT_ADMIN_USERNAME)
    return m, a


@dataclass
class CreateGroupResult:
    success: bool
    group_name: str = ""
    invite_link: str = ""
    members_added: List[str] = field(default_factory=list)
    members_failed: List[str] = field(default_factory=list)
    admins_promoted: List[str] = field(default_factory=list)
    admins_failed: List[str] = field(default_factory=list)
    error: str = ""


# Full admin rights for promoted users (change_info, post, edit, delete, invite, pin, etc.)
def _admin_rights() -> ChatAdminRights:
    return ChatAdminRights(
        change_info=True,
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        invite_users=True,
        restrict_members=True,
        pin_messages=True,
        manage_topics=True,
        promote_members=True,
        manage_call=True,
        other=True,
    )


async def create_group_and_setup(
    client: TelegramClient,
    code: str,
    company: str,
    group_title: str,
) -> CreateGroupResult:
    """
    Create a supergroup, add members, promote admins, send welcome, export invite link.
    """
    result = CreateGroupResult(success=False, group_name=group_title)
    members = get_members(code)
    admins = get_admins(code)
    members, admins = _ensure_default_admin(members, admins)
    welcome = get_welcome_message(code)

    try:
        # Create supergroup (megagroup = group with history and invite link)
        create = await client(
            CreateChannelRequest(
                title=group_title,
                about="",
                megagroup=True,
                broadcast=False,
            )
        )
        channel = create.chats[0]
        result.group_name = group_title

        # Resolve and add members
        for name in members:
            username = username_for_telegram(name)
            try:
                entity = await client.get_input_entity(username)
                if entity and not isinstance(entity, InputUserEmpty):
                    await client(InviteToChannelRequest(channel=channel, users=[entity]))
                    result.members_added.append(name)
                else:
                    result.members_failed.append(name)
            except Exception as e:
                logger.warning("Failed to add %s: %s", name, e)
                result.members_failed.append(name)

        # Invites are not always instant joins (privacy / pending). Promoting requires the user
        # to already be in the megagroup, so retry on USER_NOT_PARTICIPANT.
        await asyncio.sleep(1.5)

        # Promote admins (creator is already admin)
        for name in admins:
            username = username_for_telegram(name)
            try:
                entity = await client.get_input_entity(username)
            except Exception as e:
                logger.warning("Failed to resolve admin %s: %s", name, e)
                result.admins_failed.append(name)
                continue

            if not entity or isinstance(entity, InputUserEmpty):
                result.admins_failed.append(name)
                continue

            promoted = False
            for attempt in range(8):
                try:
                    await client(
                        EditAdminRequest(
                            channel=channel,
                            user_id=entity,
                            admin_rights=_admin_rights(),
                            rank="Admin",
                        )
                    )
                    result.admins_promoted.append(name)
                    promoted = True
                    break
                except UserNotParticipantError:
                    if attempt < 7:
                        await asyncio.sleep(2.0)
                    else:
                        logger.warning(
                            "Admin %s never joined the group after invite (still not participant)",
                            name,
                        )
                except Exception as e:
                    logger.warning("Failed to promote %s: %s", name, e)
                    result.admins_failed.append(name)
                    promoted = True
                    break

            if not promoted and name not in result.admins_promoted:
                result.admins_failed.append(name)

        # Send welcome message in the group
        if welcome:
            await client.send_message(channel, welcome)

        # Export invite link (no expiry, no limit for MVP)
        export = await client(
            ExportChatInviteRequest(peer=channel)
        )
        result.invite_link = export.link
        result.success = True

    except Exception as e:
        logger.exception("Create group failed")
        result.error = str(e)

    return result


def create_telethon_client(
    api_id: int,
    api_hash: str,
    session_name: str = "group_automation",
    session_dir: Optional[Path] = None,
) -> TelegramClient:
    base = Path(__file__).resolve().parent.parent
    session_dir = session_dir or (base / "session")
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / session_name
    return TelegramClient(
        str(session_path),
        api_id,
        api_hash,
    )

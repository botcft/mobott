from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections.abc import Awaitable, Callable
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.functions.channels import EditAdminRequest, InviteToChannelRequest
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.types import ChatAdminRights


@dataclass
class ActionResult:
    success: list[str]
    failed: dict[str, str]


class TelegramUserService:
    """MTProto-backed service for creating and configuring groups."""

    def __init__(self, session: str, api_id: int, api_hash: str) -> None:
        self._client = TelegramClient(session=session, api_id=api_id, api_hash=api_hash)

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def start(self) -> None:
        await self._connect_with_lock_retry(authorize=True)

    async def connect(self) -> None:
        await self._connect_with_lock_retry(authorize=False)

    async def is_authorized(self) -> bool:
        return await self._client.is_user_authorized()

    async def stop(self) -> None:
        await self._client.disconnect()

    async def _connect_with_lock_retry(self, authorize: bool) -> None:
        for attempt in range(1, 6):
            try:
                if authorize:
                    await self._client.start()
                else:
                    await self._client.connect()
                return
            except sqlite3.OperationalError as exc:
                is_locked = "database is locked" in str(exc).lower()
                if not is_locked or attempt == 5:
                    raise
                await asyncio.sleep(attempt)

    async def create_supergroup(self, title: str, about: str) -> Any:
        response = await self._client(
            CreateChannelRequest(
                title=title,
                about=about[:255],
                megagroup=True,
            )
        )
        return response.chats[0]

    async def invite_many(
        self, chat: Any, users: list[tuple[str, int, str | None]], retries: int = 3
    ) -> ActionResult:
        result = ActionResult(success=[], failed={})
        for alias, user_id, username in users:
            identifier = username or user_id
            try:
                await self._run_with_retry(
                    lambda: self._invite_one(chat=chat, user_identifier=identifier),
                    retries=retries,
                )
                result.success.append(alias)
            except Exception as exc:  # noqa: BLE001
                result.failed[alias] = str(exc)
        return result

    async def promote_many(
        self,
        chat: Any,
        users: list[tuple[str, int, str | None]],
        retries: int = 3,
        include_manage_topics: bool = True,
    ) -> ActionResult:
        result = ActionResult(success=[], failed={})
        rights = ChatAdminRights(
            change_info=False,
            post_messages=False,
            edit_messages=False,
            delete_messages=False,
            ban_users=False,
            invite_users=True,
            pin_messages=True,
            add_admins=False,
            anonymous=False,
            manage_call=False,
            other=True,
            manage_topics=include_manage_topics,
        )
        for alias, user_id, username in users:
            identifier = username or user_id
            try:
                await self._run_with_retry(
                    lambda: self._promote_one(chat=chat, user_identifier=identifier, rights=rights),
                    retries=retries,
                )
                result.success.append(alias)
            except Exception as exc:  # noqa: BLE001
                result.failed[alias] = str(exc)
        return result

    async def add_bot_as_admin(
        self, chat: Any, bot_username: str, retries: int = 3
    ) -> str | None:
        normalized_username = bot_username.lstrip("@")
        await self._run_with_retry(
            lambda: self._invite_one(chat=chat, user_identifier=normalized_username),
            retries=retries,
        )
        rights = ChatAdminRights(
            change_info=False,
            post_messages=False,
            edit_messages=False,
            delete_messages=False,
            ban_users=False,
            invite_users=True,
            pin_messages=True,
            add_admins=False,
            anonymous=False,
            manage_call=False,
            other=True,
            manage_topics=True,
        )
        await self._run_with_retry(
            lambda: self._promote_one(chat=chat, user_identifier=normalized_username, rights=rights),
            retries=retries,
        )
        return normalized_username

    async def _invite_one(self, chat: Any, user_identifier: int | str) -> None:
        user_entity = await self._client.get_input_entity(user_identifier)
        await self._client(InviteToChannelRequest(channel=chat, users=[user_entity]))

    async def _promote_one(
        self, chat: Any, user_identifier: int | str, rights: ChatAdminRights
    ) -> None:
        user_entity = await self._client.get_input_entity(user_identifier)
        await self._client(
            EditAdminRequest(
                channel=chat,
                user_id=user_entity,
                admin_rights=rights,
                rank="Admin",
            )
        )

    async def _run_with_retry(
        self, operation_factory: Callable[[], Awaitable[None]], retries: int = 3
    ) -> None:
        last_exception: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                return await operation_factory()
            except FloodWaitError as exc:
                wait_for = max(int(exc.seconds), 1)
                last_exception = Exception(f"Rate limited by Telegram, waited {wait_for}s.")
                await asyncio.sleep(wait_for)
            except RPCError as exc:
                last_exception = Exception(f"{exc.__class__.__name__}: {exc}")
                if attempt < retries:
                    await asyncio.sleep(attempt * 2)
                else:
                    break
            except Exception as exc:  # noqa: BLE001
                last_exception = exc
                if attempt < retries:
                    await asyncio.sleep(attempt * 2)
                else:
                    break
        if last_exception:
            raise last_exception

    @staticmethod
    def invite_expiry(expire_hours: int) -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=expire_hours)

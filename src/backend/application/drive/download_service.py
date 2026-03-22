"""Application service for provider download resolution and account fallback."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import DriveOrganizerError
from backend.db.models import LinkedAccount
from backend.security.token_manager import TokenManager
from backend.services.providers.factory import build_drive_client


class DriveDownloadService:
    """Resolve download-capable accounts and execute provider download flows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.token_manager = TokenManager(session)

    async def get_download_url(
        self,
        *,
        account_id: str,
        item_id: str,
        auto_resolve_account: bool = False,
    ) -> str:
        candidate_accounts = await self._build_download_candidates(
            account_id=account_id,
            auto_resolve_account=auto_resolve_account,
        )
        last_error: Exception | None = None

        for index, candidate in enumerate(candidate_accounts):
            try:
                candidate_client = build_drive_client(candidate, self.token_manager)
                return await candidate_client.get_download_url(candidate, item_id)
            except DriveOrganizerError as exc:
                last_error = exc
                should_try_next = (
                    auto_resolve_account
                    and exc.status_code in {400, 404}
                    and index < len(candidate_accounts) - 1
                )
                if should_try_next:
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise HTTPException(status_code=404, detail="Account not found")

    async def download_file_bytes(
        self,
        *,
        account_id: str,
        item_id: str,
        auto_resolve_account: bool = False,
    ) -> tuple[str, bytes]:
        candidate_accounts = await self._build_download_candidates(
            account_id=account_id,
            auto_resolve_account=auto_resolve_account,
        )
        last_error: Exception | None = None

        for index, candidate in enumerate(candidate_accounts):
            try:
                candidate_client = build_drive_client(candidate, self.token_manager)
                return await candidate_client.download_file_bytes(candidate, item_id)
            except DriveOrganizerError as exc:
                last_error = exc
                should_try_next = (
                    auto_resolve_account
                    and exc.status_code in {400, 404}
                    and index < len(candidate_accounts) - 1
                )
                if should_try_next:
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise HTTPException(status_code=404, detail="Account not found")

    async def _resolve_download_account(
        self,
        *,
        account_id: str,
        auto_resolve_account: bool,
    ) -> LinkedAccount | None:
        try:
            account_uuid = uuid.UUID(str(account_id))
        except (TypeError, ValueError):
            account_uuid = None

        if account_uuid is not None:
            account = await self.session.get(LinkedAccount, account_uuid)
            if account is not None:
                return account

        if auto_resolve_account:
            return None

        raise HTTPException(status_code=404, detail="Account not found")

    async def _build_download_candidates(
        self,
        *,
        account_id: str,
        auto_resolve_account: bool,
    ) -> list[LinkedAccount]:
        requested_account = await self._resolve_download_account(
            account_id=account_id,
            auto_resolve_account=auto_resolve_account,
        )
        stmt = select(LinkedAccount).where(LinkedAccount.is_active.is_(True))
        if requested_account is not None:
            stmt = stmt.where(LinkedAccount.id != requested_account.id)
        other_accounts = (await self.session.execute(stmt)).scalars().all()
        if requested_account is None:
            return list(other_accounts)
        return [requested_account, *other_accounts]

"""`/imports`: upload ING exports and list the import history."""

from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.api.deps import get_session
from skarbonka.db.models import ImportBatch
from skarbonka.domain.imports import ImportStats, import_ing_file, to_stats

router = APIRouter(prefix="/imports", tags=["imports"])

SessionDep = Annotated[Session, Depends(get_session)]


class ImportResponse(BaseModel):
    imports: list[ImportStats]


@router.post("")
async def create_imports(files: list[UploadFile], session: SessionDep) -> ImportResponse:
    """Import every file; one broken file is reported in its stats and does not stop the rest."""
    results: list[ImportStats] = []
    for upload in files:
        raw = await upload.read()
        results.append(import_ing_file(session, upload.filename or "unnamed.csv", raw))
        session.commit()
    return ImportResponse(imports=results)


@router.get("")
def list_imports(session: SessionDep, limit: int = 50) -> list[ImportStats]:
    """Newest first."""
    batches = session.scalars(
        select(ImportBatch).order_by(ImportBatch.id.desc()).limit(limit)
    ).all()
    return [to_stats(batch) for batch in batches]

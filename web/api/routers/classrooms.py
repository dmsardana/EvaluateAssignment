"""Lightweight classrooms list — served from a Postgres cache so the
queue-page dropdown doesn't have to wait for /api/queue (which makes
N+M Google API round trips). See web/api/services/classrooms_store.py
for refresh semantics (5-min TTL, stale-if-error)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from web.api.deps import get_classroom
from web.api.models import ClassroomCourse, ClassroomsResponse
from web.api.services import classrooms_store

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/classrooms", tags=["classrooms"])


@router.get("", response_model=ClassroomsResponse)
def get_classrooms(classroom=Depends(get_classroom)) -> ClassroomsResponse:
    rows = classrooms_store.list_classrooms(classroom)
    return ClassroomsResponse(
        classrooms=[ClassroomCourse(**r) for r in rows],
    )

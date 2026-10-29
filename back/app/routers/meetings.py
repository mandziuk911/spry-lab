from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.agenda_schemas import AgendaSave
from app.auth import require_access_token
from app.db import get_db
from app.schemas import MeetingCreate, MeetingRead
from app.services import meetings as service

router = APIRouter(prefix="/meetings", tags=["meetings"], dependencies=[Depends(require_access_token)])


@router.get("", response_model=list[MeetingRead])
def list_meetings(db: Session = Depends(get_db)):
    return service.list_meetings(db)


@router.post("", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
def create_meeting(data: MeetingCreate, db: Session = Depends(get_db)):
    return service.create_meeting(db, data)


@router.get("/{meeting_id}/agenda", response_model=AgendaSave)
def get_agenda(meeting_id: UUID, db: Session = Depends(get_db)):
    exists, agenda = service.get_agenda(db, meeting_id)
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if agenda is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agenda not found")
    return agenda


@router.post("/{meeting_id}/agenda", response_model=AgendaSave)
def save_agenda(meeting_id: UUID, data: AgendaSave, db: Session = Depends(get_db)):
    agenda = service.save_agenda(db, meeting_id, data)
    if agenda is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return agenda


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: UUID, db: Session = Depends(get_db)):
    if not service.delete_meeting(db, meeting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

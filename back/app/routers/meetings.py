from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import MeetingCreate, MeetingRead
from app.services import meetings as service

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("", response_model=list[MeetingRead])
def list_meetings(db: Session = Depends(get_db)):
    return service.list_meetings(db)


@router.post("", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
def create_meeting(data: MeetingCreate, db: Session = Depends(get_db)):
    return service.create_meeting(db, data)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: UUID, db: Session = Depends(get_db)):
    if not service.delete_meeting(db, meeting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

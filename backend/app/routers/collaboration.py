from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator
from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth import assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError, get_connection

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])

class ConversationCreate(BaseModel):
    organization_id: UUID
    kind: Literal["direct", "group"]
    member_ids: list[UUID] = Field(min_length=1, max_length=30)
    title: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_kind(self):
        if self.kind == "direct" and len(self.member_ids) != 1:
            raise ValueError("Direct conversations require exactly one other member")
        if self.kind == "group" and not (self.title and self.title.strip()):
            raise ValueError("Group title is required")
        return self

class GroupMembersAdd(BaseModel):
    member_ids: list[UUID] = Field(min_length=1, max_length=30)

class GroupTitleUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)

class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    client_message_id: UUID | None = None

    @field_validator("body")
    @classmethod
    def body_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be empty")
        return value

def _member(cursor, conversation_id: UUID, user_id: UUID):
    cursor.execute("""
      select cm.joined_at
      from public.conversation_members cm
      join public.conversations c on c.id = cm.conversation_id
      join public.organization_members om
        on om.organization_id = c.organization_id and om.user_id = cm.user_id
      where cm.conversation_id=%s and cm.user_id=%s
        and cm.left_at is null and c.archived_at is null
    """, [conversation_id, user_id])
    membership = cursor.fetchone()
    if membership is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return membership

def _check_org_members(cursor, organization_id: UUID, user_ids: list[UUID]):
    cursor.execute("""
      select user_id from public.organization_members
      where organization_id=%s and user_id = any(%s)
    """, [organization_id, user_ids])
    found = {row["user_id"] for row in cursor.fetchall()}
    if set(user_ids) != found:
        raise HTTPException(status_code=422, detail="One or more members do not belong to this organization")

@router.get("/contacts")
async def contacts(organization_id: UUID, q: str = Query(default="", max_length=100),
                   user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    pattern = "%" + q.strip().replace("%", "\\%").replace("_", "\\_") + "%"
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
              select p.id, p.full_name, m.role
              from public.organization_members m join public.profiles p on p.id=m.user_id
              where m.organization_id=%s and p.id <> %s
                and (%s = '' or coalesce(p.full_name,'') ilike %s)
              order by p.full_name nulls last limit 100
            """, [organization_id, user_id, q.strip(), pattern])
            return [{"id": str(r["id"]), "full_name": r["full_name"] or "AQERITH user", "role": r["role"]} for r in cursor.fetchall()]

@router.get("/conversations")
async def list_conversations(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
              select c.id, c.kind, c.title, c.updated_at, cm.is_pinned, cm.last_read_at,
                (select m.body from public.messages m where m.conversation_id=c.id and m.deleted_at is null
                 order by m.created_at desc, m.id desc limit 1) as last_message,
                (select m.created_at from public.messages m where m.conversation_id=c.id and m.deleted_at is null
                 order by m.created_at desc, m.id desc limit 1) as last_message_at,
                (select count(*) from public.messages m where m.conversation_id=c.id and m.deleted_at is null
                 and m.sender_user_id <> %s and (cm.last_read_at is null or m.created_at > cm.last_read_at)) as unread_count,
                (select coalesce(json_agg(json_build_object('id',p.id,'full_name',p.full_name,'role',m2.member_role)), '[]'::json)
                 from public.conversation_members m2
                 join public.profiles p on p.id=m2.user_id
                 join public.organization_members om2 on om2.organization_id=c.organization_id and om2.user_id=m2.user_id
                 where m2.conversation_id=c.id and m2.left_at is null) as members
              from public.conversation_members cm join public.conversations c on c.id=cm.conversation_id
              where cm.user_id=%s and cm.left_at is null and c.organization_id=%s and c.archived_at is null
              order by cm.is_pinned desc, coalesce(c.updated_at,c.created_at) desc limit 100
            """, [user_id, user_id, organization_id])
            return [{**r, "id": str(r["id"]), "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                     "last_read_at": r["last_read_at"].isoformat() if r["last_read_at"] else None,
                     "last_message_at": r["last_message_at"].isoformat() if r["last_message_at"] else None}
                    for r in cursor.fetchall()]

@router.post("/conversations", status_code=201)
async def create_conversation(payload: ConversationCreate, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, payload.organization_id)
    members = sorted(set(payload.member_ids + [user_id]), key=str)
    if payload.kind == "direct" and len(members) != 2:
        raise HTTPException(status_code=422, detail="Direct conversations require one other user")
    if payload.kind == "group" and len(members) < 2:
        raise HTTPException(status_code=422, detail="Group conversations require at least one other member")
    direct_key = ":".join(map(str, members)) if payload.kind == "direct" else None
    title = payload.title.strip() if payload.title else None
    if payload.kind == "group" and not title:
        raise HTTPException(status_code=422, detail="Group title is required")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _check_org_members(cursor, payload.organization_id, members)
            if direct_key:
                cursor.execute("""
                  insert into public.conversations (organization_id,kind,direct_key,created_by)
                  values (%s,'direct',%s,%s)
                  on conflict (organization_id,direct_key) where direct_key is not null
                  do update set updated_at=public.conversations.updated_at
                  returning id
                """, [payload.organization_id, direct_key, user_id])
            else:
                cursor.execute("""
                  insert into public.conversations (organization_id,kind,title,created_by)
                  values (%s,'group',%s,%s) returning id
                """, [payload.organization_id, title, user_id])
            conversation_id = cursor.fetchone()["id"]
            for member_id in members:
                cursor.execute("""
                  insert into public.conversation_members (conversation_id,user_id,member_role,last_read_at)
                  values (%s,%s,%s,now()) on conflict (conversation_id,user_id) do nothing
                """, [conversation_id, member_id, "owner" if member_id == user_id else "member"])
            return {"id": str(conversation_id), "kind": payload.kind, "title": title}

@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: UUID, before: datetime | None = None,
                        limit: int = Query(default=50, ge=1, le=100),
                        user_id: UUID = Depends(get_current_user_id)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            membership = _member(cursor, conversation_id, user_id)
            joined_at = membership["joined_at"]
            if before:
                cursor.execute("""
                  select id,sender_user_id,body,created_at,edited_at,deleted_at
                  from public.messages
                  where conversation_id=%s and created_at >= %s and created_at < %s
                  order by created_at desc,id desc limit %s
                """, [conversation_id, joined_at, before, limit])
            else:
                cursor.execute("""
                  select id,sender_user_id,body,created_at,edited_at,deleted_at
                  from public.messages where conversation_id=%s and created_at >= %s
                  order by created_at desc,id desc limit %s
                """, [conversation_id, joined_at, limit])
            rows = cursor.fetchall()
            return [{"id":str(r["id"]), "sender_user_id":str(r["sender_user_id"]),
                     "body":"This message was deleted" if r["deleted_at"] else r["body"],
                     "created_at":r["created_at"].isoformat(), "edited_at":r["edited_at"].isoformat() if r["edited_at"] else None,
                     "deleted":bool(r["deleted_at"])} for r in reversed(rows)]

@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def send_message(conversation_id: UUID, payload: MessageCreate, user_id: UUID = Depends(get_current_user_id)):
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _member(cursor, conversation_id, user_id)
            cursor.execute("""
              insert into public.messages (conversation_id,sender_user_id,body,client_message_id)
              values (%s,%s,%s,%s)
              on conflict (conversation_id,sender_user_id,client_message_id)
              do update set client_message_id=excluded.client_message_id
              returning id,sender_user_id,body,created_at
            """, [conversation_id,user_id,body,payload.client_message_id])
            message = cursor.fetchone()
            cursor.execute("update public.conversations set updated_at=now() where id=%s", [conversation_id])
            return {"id":str(message["id"]), "sender_user_id":str(message["sender_user_id"]),
                    "body":message["body"], "created_at":message["created_at"].isoformat()}

@router.post("/conversations/{conversation_id}/read")
async def mark_read(conversation_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _member(cursor, conversation_id, user_id)
            cursor.execute("update public.conversation_members set last_read_at=now() where conversation_id=%s and user_id=%s",
                           [conversation_id,user_id])
            return {"ok": True}

@router.post("/conversations/{conversation_id}/pin")
async def set_pinned(conversation_id: UUID, pinned: bool = Query(...), user_id: UUID = Depends(get_current_user_id)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _member(cursor, conversation_id, user_id)
            cursor.execute("update public.conversation_members set is_pinned=%s where conversation_id=%s and user_id=%s",
                           [pinned,conversation_id,user_id])
            return {"pinned": pinned}


def _assert_group_owner(cursor, conversation_id: UUID, user_id: UUID):
    cursor.execute("""
      select c.kind, cm.member_role
      from public.conversations c
      join public.conversation_members cm on cm.conversation_id=c.id
      join public.organization_members om on om.organization_id=c.organization_id and om.user_id=cm.user_id
      where c.id=%s and cm.user_id=%s and cm.left_at is null
    """, [conversation_id, user_id])
    row = cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if row["kind"] != "group" or row["member_role"] != "owner":
        raise HTTPException(status_code=403, detail="Only group owners can manage members")

@router.post("/conversations/{conversation_id}/members")
async def add_group_members(conversation_id: UUID, payload: GroupMembersAdd,
                            user_id: UUID = Depends(get_current_user_id)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _assert_group_owner(cursor, conversation_id, user_id)
            cursor.execute("select organization_id from public.conversations where id=%s and archived_at is null", [conversation_id])
            conversation = cursor.fetchone()
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
            member_ids = list(set(payload.member_ids))
            _check_org_members(cursor, conversation["organization_id"], member_ids)
            for target_id in member_ids:
                cursor.execute("""
                  insert into public.conversation_members (conversation_id,user_id,member_role,last_read_at)
                  values (%s,%s,'member',now())
                  on conflict (conversation_id,user_id) do update set left_at=null, joined_at=now(), last_read_at=now()
                """, [conversation_id, target_id])
                cursor.execute("""
                  insert into public.conversation_events (conversation_id,actor_user_id,event_type,target_user_id)
                  values (%s,%s,'member_added',%s)
                """, [conversation_id,user_id,target_id])
            return {"added": [str(x) for x in member_ids]}

@router.delete("/conversations/{conversation_id}/members/{target_user_id}")
async def remove_group_member(conversation_id: UUID, target_user_id: UUID,
                              user_id: UUID = Depends(get_current_user_id)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _assert_group_owner(cursor, conversation_id, user_id)
            if target_user_id == user_id:
                raise HTTPException(status_code=422, detail="Use the leave endpoint to leave this group")
            cursor.execute("""
              update public.conversation_members set left_at=now()
              where conversation_id=%s and user_id=%s and left_at is null
            """, [conversation_id,target_user_id])
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Active group member not found")
            cursor.execute("""
              insert into public.conversation_events (conversation_id,actor_user_id,event_type,target_user_id)
              values (%s,%s,'member_removed',%s)
            """, [conversation_id,user_id,target_user_id])
            return {"removed": str(target_user_id)}

@router.post("/conversations/{conversation_id}/leave")
async def leave_group(conversation_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _member(cursor, conversation_id, user_id)
            cursor.execute("""
              select c.kind, cm.member_role
              from public.conversations c
              join public.conversation_members cm on cm.conversation_id=c.id
              where c.id=%s and cm.user_id=%s and cm.left_at is null
            """, [conversation_id, user_id])
            row = cursor.fetchone()
            if row is None or row["kind"] != "group":
                raise HTTPException(status_code=422, detail="Only group conversations can be left")
            was_owner = row["member_role"] == "owner"
            cursor.execute("update public.conversation_members set left_at=now() where conversation_id=%s and user_id=%s", [conversation_id,user_id])
            if was_owner:
                cursor.execute("""
                  select cm.user_id from public.conversation_members cm
                  join public.organization_members om on om.user_id=cm.user_id
                  join public.conversations c on c.organization_id=om.organization_id and c.id=cm.conversation_id
                  where cm.conversation_id=%s and cm.left_at is null
                  order by cm.joined_at asc limit 1
                """, [conversation_id])
                successor = cursor.fetchone()
                if successor:
                    cursor.execute("""
                      update public.conversation_members set member_role='owner'
                      where conversation_id=%s and user_id=%s
                    """, [conversation_id, successor["user_id"]])
                else:
                    cursor.execute("update public.conversations set archived_at=now() where id=%s", [conversation_id])
            cursor.execute("""
              insert into public.conversation_events (conversation_id,actor_user_id,event_type,target_user_id)
              values (%s,%s,'member_left',%s)
            """, [conversation_id,user_id,user_id])
            return {"left": True, "ownership_transferred": was_owner}

@router.patch("/conversations/{conversation_id}/title")
async def update_group_title(conversation_id: UUID, payload: GroupTitleUpdate,
                             user_id: UUID = Depends(get_current_user_id)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Group title cannot be empty")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            _assert_group_owner(cursor, conversation_id, user_id)
            cursor.execute("update public.conversations set title=%s,updated_at=now() where id=%s", [title,conversation_id])
            cursor.execute("""
              insert into public.conversation_events (conversation_id,actor_user_id,event_type,metadata)
              values (%s,%s,'title_changed',jsonb_build_object('title',%s))
            """, [conversation_id,user_id,title])
            return {"title": title}

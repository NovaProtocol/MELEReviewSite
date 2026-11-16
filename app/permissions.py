"""Bit-flag permissions.

One integer column holds every grant. A bit is added by introducing a constant
below and never renumbering an existing one: old rows keep their meaning.
"""

from __future__ import annotations

from fastapi import HTTPException

POST_QUESTION = 1 << 0
ANSWER_QUESTION = 1 << 1
INVITE = 1 << 2
MODERATE = 1 << 3
VIEW_HIDDEN = 1 << 4
MANAGE_TAXONOMY = 1 << 5
MANAGE_USERS = 1 << 6
MANAGE_INVITES = 1 << 7
EDIT_TOPIC_CONTENT = 1 << 8

ALL = 0
for _bit in (
    POST_QUESTION,
    ANSWER_QUESTION,
    INVITE,
    MODERATE,
    VIEW_HIDDEN,
    MANAGE_TAXONOMY,
    MANAGE_USERS,
    MANAGE_INVITES,
    EDIT_TOPIC_CONTENT,
):
    ALL |= _bit

DEFAULT = POST_QUESTION | ANSWER_QUESTION | INVITE

LABELS: dict[int, str] = {
    POST_QUESTION: "Post questions",
    ANSWER_QUESTION: "Answer questions",
    INVITE: "Invite users",
    MODERATE: "Moderate content",
    VIEW_HIDDEN: "View hidden content",
    MANAGE_TAXONOMY: "Manage subjects and topics",
    MANAGE_USERS: "Manage users",
    MANAGE_INVITES: "Manage invitations",
    EDIT_TOPIC_CONTENT: "Administrator",
}

SHORT: dict[int, str] = {
    POST_QUESTION: "post",
    ANSWER_QUESTION: "answer",
    INVITE: "invite",
    MODERATE: "moderate",
    VIEW_HIDDEN: "see hidden",
    MANAGE_TAXONOMY: "taxonomy",
    MANAGE_USERS: "users",
    MANAGE_INVITES: "invites",
    EDIT_TOPIC_CONTENT: "administrator",
}

ORDER: tuple[int, ...] = tuple(LABELS)


def has(permissions: int, bit: int) -> bool:
    return bool(permissions & bit)


def describe(permissions: int) -> list[str]:
    return [name for bit, name in LABELS.items() if permissions & bit]


def require(permissions: int, bit: int) -> None:
    if not has(permissions, bit):
        raise HTTPException(status_code=403, detail="You do not have permission for that")

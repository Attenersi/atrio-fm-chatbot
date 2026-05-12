"""Users, sessions, and chat-thread persistence.

Phase-4 transitional shim: implementations still live in ``app.database``.
"""

from ..database import (
    append_chat_exchange,
    authenticate_user,
    create_session,
    create_user_account,
    delete_session,
    get_active_chat_thread,
    get_session,
    get_user_by_id,
    list_active_chat_messages,
    list_chat_messages,
    list_users,
    start_new_chat_thread,
    update_user_admin_fields,
)

__all__ = [
    "append_chat_exchange",
    "authenticate_user",
    "create_session",
    "create_user_account",
    "delete_session",
    "get_active_chat_thread",
    "get_session",
    "get_user_by_id",
    "list_active_chat_messages",
    "list_chat_messages",
    "list_users",
    "start_new_chat_thread",
    "update_user_admin_fields",
]

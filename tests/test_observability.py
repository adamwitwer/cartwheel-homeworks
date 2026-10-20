"""Authentication tests for the Homework 2 endpoint.

Offline: no Langfuse, Docker, or model provider key. Tracing is checked in Langfuse.
"""

import asyncio

import pytest
from fastapi import HTTPException

from server import app as server_app


def test_create_session_rejects_role_that_differs_from_database(world: dict) -> None:
    # User 1 is a shopper in the database; claiming support must not work.
    server_app._SESSIONS.clear()
    with pytest.raises(HTTPException) as exc:
        server_app.create_session(server_app.SessionCreate(user_id=1, role="support"))
    assert exc.value.status_code == 403
    assert server_app._SESSIONS == {}


def test_token_for_one_session_cannot_authorize_another(world: dict) -> None:
    server_app._SESSIONS.clear()
    shopper = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))
    merchant = server_app.create_session(
        server_app.SessionCreate(user_id=9002, role="merchant")
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server_app.post_message(
                merchant["session_id"],
                server_app.MessageIn(message="Show me order 4127."),
                authorization=f"Bearer {shopper['token']}",
            )
        )
    assert exc.value.status_code == 403

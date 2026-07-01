"""System test: message archive + embedding storage on a copied DB."""

import datetime

import numpy as np

from deps.ai.embeddings import from_blob, to_blob
from deps.message_data_access import (
    get_embedded_messages_for_guild,
    get_messages_without_embedding,
    set_message_embedding,
    store_message,
)


def test_message_archive_and_embedding_crud(system_db):  # pylint: disable=unused-argument
    """Store messages, backfill embeddings, and read them back via real SQL."""
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)

    store_message(1, 1, 10, "general", 100, "mom", "we should plan a trip", now)
    store_message(2, 1, 10, "general", 101, "dad", "great idea", now)
    # Idempotent: storing the same message id again does not duplicate.
    store_message(1, 1, 10, "general", 100, "mom", "we should plan a trip", now)
    # Empty content is skipped.
    store_message(3, 1, 10, "general", 102, "kid", "   ", now)

    pending = get_messages_without_embedding()
    assert {mid for mid, _ in pending} == {1, 2}

    for message_id, _content in pending:
        set_message_embedding(message_id, to_blob(np.array([0.1, 0.2, 0.3], dtype=np.float32)))

    assert get_messages_without_embedding() == []

    rows = get_embedded_messages_for_guild(1)
    assert len(rows) == 2
    # Embedding round-trips through the database blob column.
    _mid, _author, _content, _created, blob = rows[0]
    assert np.allclose(from_blob(blob), np.array([0.1, 0.2, 0.3], dtype=np.float32))

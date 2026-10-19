"""Document store abstraction over Firestore with an in-memory fallback.

STORE_BACKEND
- "firestore" (default): Firestore via firebase-admin service account credentials.
- "memory": process-local dict store for local development and tests.

Every user-owned document carries a `user_id` field. Callers are responsible for
passing the token-verified UID; the store never infers ownership on its own.
"""

import copy
import os
import threading
import uuid
from functools import lru_cache
from typing import Any, Optional

USER_OWNED_COLLECTIONS = (
    "goals",
    "tasks",
    "study_logs",
    "reflections",
    "conversations",
    "consent_records",
)


class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._data.clear()

    def create(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        doc_id = uuid.uuid4().hex
        return self.set(collection, doc_id, data)

    def set(self, collection: str, doc_id: str, data: dict[str, Any]) -> dict[str, Any]:
        doc = {**copy.deepcopy(data), "id": doc_id}
        with self._lock:
            self._data.setdefault(collection, {})[doc_id] = doc
        return copy.deepcopy(doc)

    def get(self, collection: str, doc_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            doc = self._data.get(collection, {}).get(doc_id)
            return copy.deepcopy(doc) if doc else None

    def update(self, collection: str, doc_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            doc = self._data[collection][doc_id]
            doc.update(copy.deepcopy(changes))
            return copy.deepcopy(doc)

    def delete(self, collection: str, doc_id: str) -> None:
        with self._lock:
            self._data.get(collection, {}).pop(doc_id, None)

    def find(self, collection: str, **filters: Any) -> list[dict[str, Any]]:
        with self._lock:
            docs = self._data.get(collection, {}).values()
            return [copy.deepcopy(d) for d in docs if all(d.get(k) == v for k, v in filters.items())]

    def delete_where(self, collection: str, **filters: Any) -> int:
        with self._lock:
            bucket = self._data.get(collection, {})
            ids = [i for i, d in bucket.items() if all(d.get(k) == v for k, v in filters.items())]
            for i in ids:
                del bucket[i]
            return len(ids)


class FirestoreStore:
    _BATCH_LIMIT = 400

    def __init__(self) -> None:
        from firebase_admin import firestore

        from auth import get_firebase_app

        self._db = firestore.client(app=get_firebase_app())

    def _query(self, collection: str, filters: dict[str, Any]):
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self._db.collection(collection)
        for key, value in filters.items():
            query = query.where(filter=FieldFilter(key, "==", value))
        return query

    def create(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        ref = self._db.collection(collection).document()
        return self.set(collection, ref.id, data)

    def set(self, collection: str, doc_id: str, data: dict[str, Any]) -> dict[str, Any]:
        doc = {**data, "id": doc_id}
        self._db.collection(collection).document(doc_id).set(doc)
        return doc

    def get(self, collection: str, doc_id: str) -> Optional[dict[str, Any]]:
        snap = self._db.collection(collection).document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def update(self, collection: str, doc_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        ref = self._db.collection(collection).document(doc_id)
        ref.update(changes)
        return ref.get().to_dict()

    def delete(self, collection: str, doc_id: str) -> None:
        self._db.collection(collection).document(doc_id).delete()

    def find(self, collection: str, **filters: Any) -> list[dict[str, Any]]:
        return [snap.to_dict() for snap in self._query(collection, filters).stream()]

    def delete_where(self, collection: str, **filters: Any) -> int:
        refs = [snap.reference for snap in self._query(collection, filters).stream()]
        for start in range(0, len(refs), self._BATCH_LIMIT):
            batch = self._db.batch()
            for ref in refs[start:start + self._BATCH_LIMIT]:
                batch.delete(ref)
            batch.commit()
        return len(refs)


def store_backend() -> str:
    return os.getenv("STORE_BACKEND", "firestore").strip().lower()


def assert_safe_store_config() -> None:
    """Fail fast if the in-memory store is enabled on a deployed environment."""
    if store_backend() == "memory" and os.getenv("RENDER"):
        raise RuntimeError("STORE_BACKEND=memory must not be used in a deployed (Render) environment.")


@lru_cache(maxsize=1)
def get_store():
    if store_backend() == "memory":
        return MemoryStore()
    return FirestoreStore()

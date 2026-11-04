"""Bounded folder hierarchy; serialise topology changes without locking media."""
from fastapi import HTTPException

MAX_DEPTH = 4


def locked_tree(database):
    database.execute("SELECT pg_advisory_xact_lock(hashtext('gm:library-folder-tree'))")
    return list(database.execute("SELECT id,parent_id FROM library_collections ORDER BY id").fetchall())


def validate_parent(rows, folder_id, parent_id):
    parents = {row['id']: row['parent_id'] for row in rows}
    if parent_id is not None and parent_id not in parents:
        raise HTTPException(status_code=409, detail="destination folder is no longer available; refresh the library")
    if folder_id is not None and folder_id not in parents:
        raise HTTPException(status_code=404, detail="folder not found")
    # Test the complete proposed subtree, not just the moved root. An unchanged
    # sibling cannot make a move exceed the cap or conceal a cycle.
    node = folder_id if folder_id is not None else object()
    proposed = {**parents, node: parent_id}
    for start in proposed:
        current, seen = start, set()
        while current is not None:
            if current not in proposed:
                raise HTTPException(status_code=409, detail="a parent folder is unavailable; refresh the library")
            if current in seen:
                raise HTTPException(status_code=409, detail="a folder cannot be moved into itself or its subfolders")
            seen.add(current)
            if len(seen) > MAX_DEPTH:
                raise HTTPException(status_code=409, detail="folders can be nested up to four levels")
            current = proposed.get(current)

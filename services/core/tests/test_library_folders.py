import unittest
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app.library import create_collection, delete_collection, move_collection, rename_collection, update_collection_batch
from app.library_folder_tree import validate_parent
from app.schemas import LibraryCollectionBatch, LibraryCollectionCreate, LibraryCollectionMove, LibraryCollectionRename

FOLDER = UUID('11111111-1111-4111-8111-111111111111')
OTHER = UUID('22222222-2222-4222-8222-222222222222')
A = UUID('33333333-3333-4333-8333-333333333333')
B = UUID('44444444-4444-4444-8444-444444444444')


class FolderDatabase:
    def __init__(self):
        self.folders = {FOLDER: 'Creams', OTHER: 'Campaign'}
        self.parents = {FOLDER: None, OTHER: None}
        self.assets = {A: {'name': 'VID_1.mp4', 'jobs': 3}, B: {'name': 'Review.png', 'jobs': 1}}
        self.members = {(OTHER, A)}
        self.statements = []
        self.results = []
        self.rowcount = 0

    @contextmanager
    def connection(self):
        before = deepcopy((self.folders, self.assets, self.members, self.parents))
        try:
            yield self
        except Exception:
            self.folders, self.assets, self.members, self.parents = before
            raise

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        self.results = []
        if 'pg_advisory_xact_lock' in sql:
            pass
        elif 'SELECT id,parent_id FROM library_collections' in sql:
            self.results = [{'id': id, 'parent_id': self.parents[id]} for id in self.folders]
        elif 'INSERT INTO library_collections' in sql:
            self.folders[A] = params[0]
            self.parents[A] = params[2]
            self.results = [{'id': A, 'name': params[0], 'parent_id': params[2]}]
        elif 'UPDATE library_collections SET parent_id' in sql:
            self.parents[params[1]] = params[0]
            self.results = [{'id': params[1], 'name': self.folders[params[1]], 'parent_id': params[0]}]
        elif 'SELECT id FROM library_collections' in sql:
            self.results = [{'id': params[0]}] if params[0] in self.folders else []
        elif 'SELECT id FROM assets' in sql:
            self.results = [{'id': key} for key in params[0] if key in self.assets]
        elif 'INSERT INTO library_collection_assets' in sql:
            self.members.update((params[0], key) for key in params[1])
        elif 'DELETE FROM library_collection_assets' in sql:
            self.members.difference_update((params[0], key) for key in params[1])
        elif 'UPDATE library_collections SET name' in sql:
            if params[2] in self.folders:
                self.folders[params[2]] = params[0]
                self.results = [{'id': params[2], 'name': params[0]}]
        elif 'DELETE FROM library_collections' in sql:
            self.rowcount = int(params[0] in self.folders)
            self.folders.pop(params[0], None)
            self.parents.pop(params[0], None)
            self.members = {item for item in self.members if item[0] != params[0]}
        elif 'UPDATE library_collections SET updated_at' not in sql:
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return self.results[0] if self.results else None

    def fetchall(self):
        return self.results


class LibraryFolderTests(unittest.TestCase):
    def setUp(self):
        self.database = FolderDatabase()
        mocked = patch('app.library.connection', self.database.connection)
        mocked.start()
        self.addCleanup(mocked.stop)

    def test_add_is_idempotent_and_keeps_other_memberships_originals_and_edits(self):
        before = deepcopy(self.database.assets)
        for _ in range(2):
            result = update_collection_batch(FOLDER, LibraryCollectionBatch(asset_ids=[A, B], action='add'))
            self.assertEqual(result['updated'], 2)
        self.assertEqual(self.database.members, {(OTHER, A), (FOLDER, A), (FOLDER, B)})
        self.assertEqual(self.database.assets, before)
        self.assertIn('ORDER BY id FOR UPDATE', self.database.statements[1][0])

    def test_remove_changes_only_the_selected_folder_memberships(self):
        self.database.members.update({(FOLDER, A), (FOLDER, B)})
        before = deepcopy(self.database.assets)
        update_collection_batch(FOLDER, LibraryCollectionBatch(asset_ids=[A], action='remove'))
        self.assertEqual(self.database.members, {(OTHER, A), (FOLDER, B)})
        self.assertEqual(self.database.assets, before)

    def test_missing_original_rejects_whole_batch_before_any_membership_write(self):
        del self.database.assets[B]
        with self.assertRaises(HTTPException) as raised:
            update_collection_batch(FOLDER, LibraryCollectionBatch(asset_ids=[A, B], action='add'))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self.database.members, {(OTHER, A)})
        self.assertEqual(len(self.database.statements), 2)

    def test_missing_folder_never_writes_or_changes_originals(self):
        with self.assertRaises(HTTPException) as raised:
            update_collection_batch(B, LibraryCollectionBatch(asset_ids=[A], action='add'))
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(len(self.database.statements), 1)

    def test_batch_is_bounded_unique_and_explicit(self):
        for payload in ({'asset_ids': [], 'action': 'add'}, {'asset_ids': [A, A], 'action': 'add'},
                        {'asset_ids': [A] * 501, 'action': 'remove'}, {'asset_ids': [A], 'action': 'move'}):
            with self.assertRaises(ValidationError):
                LibraryCollectionBatch(**payload)

    def test_removing_folder_keeps_originals_job_references_and_other_folders(self):
        before = deepcopy(self.database.assets)
        self.database.members.add((FOLDER, A))
        delete_collection(FOLDER)
        self.assertEqual(self.database.assets, before)
        self.assertEqual(self.database.members, {(OTHER, A)})
        self.assertFalse(any('DELETE FROM assets' in sql for sql, _ in self.database.statements))

    def test_rename_changes_folder_identity_neither_assets_nor_membership(self):
        before = deepcopy(self.database.assets)
        result = rename_collection(FOLDER, LibraryCollectionCreate(name='  Cream   collection '))
        self.assertEqual(result['id'], FOLDER)
        self.assertEqual(result['name'], 'Cream collection')
        self.assertEqual(self.database.assets, before)
        self.assertEqual(self.database.members, {(OTHER, A)})

    def test_rename_missing_folder_has_clear_not_found(self):
        with self.assertRaises(HTTPException) as raised:
            rename_collection(B, LibraryCollectionCreate(name='Missing'))
        self.assertEqual(raised.exception.status_code, 404)

    def test_create_child_does_not_move_or_reanalyze_existing_media(self):
        before = deepcopy((self.database.assets, self.database.members))
        row = create_collection(LibraryCollectionCreate(name='Cream B-roll', parent_id=FOLDER))
        self.assertEqual(row['parent_id'], FOLDER)
        self.assertEqual((self.database.assets, self.database.members), before)
        self.assertIn('pg_advisory_xact_lock', self.database.statements[0][0])

    def test_move_keeps_descendants_memberships_and_historical_references(self):
        self.database.folders[B] = 'Reviews'
        self.database.parents[B] = FOLDER
        before = deepcopy((self.database.assets, self.database.members))
        row = move_collection(FOLDER, LibraryCollectionMove(parent_id=OTHER, expected_parent_id=None))
        self.assertEqual(row['parent_id'], OTHER)
        self.assertEqual(self.database.parents[B], FOLDER)
        self.assertEqual((self.database.assets, self.database.members), before)
        move_collection(FOLDER, LibraryCollectionMove(parent_id=None, expected_parent_id=OTHER))
        self.assertIsNone(self.database.parents[FOLDER])

    def test_move_refuses_self_descendant_missing_parent_and_stale_request(self):
        self.database.parents[OTHER] = FOLDER
        for parent, expected in ((FOLDER,None), (OTHER,None), (B,None), (None,OTHER)):
            before = deepcopy(self.database.parents)
            with self.assertRaises(HTTPException) as raised:
                move_collection(FOLDER, LibraryCollectionMove(parent_id=parent, expected_parent_id=expected))
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(self.database.parents, before)
        self.assertFalse(any('UPDATE library_collections' in sql for sql, _ in self.database.statements))

    def test_parent_with_children_cannot_be_deleted(self):
        self.database.parents[OTHER] = FOLDER
        before = deepcopy((self.database.folders,self.database.members))
        with self.assertRaises(HTTPException) as raised:
            delete_collection(FOLDER)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual((self.database.folders,self.database.members), before)
        self.assertFalse(any('DELETE' in sql for sql, _ in self.database.statements))

    def test_depth_limit_checks_the_complete_moving_subtree(self):
        rows = [{'id': FOLDER, 'parent_id': None}, {'id': OTHER, 'parent_id': FOLDER},
                {'id': A, 'parent_id': OTHER}, {'id': B, 'parent_id': A}]
        validate_parent(rows, None, A)  # New fourth level.
        for id, parent in ((None,B), (FOLDER,B), (OTHER,A)):
            with self.assertRaises(HTTPException):
                validate_parent(rows,id,parent)
        # A two-level subtree cannot be placed under an existing third level.
        rows += [{'id': 'root', 'parent_id': None}, {'id': 'child', 'parent_id': 'root'}]
        with self.assertRaises(HTTPException):
            validate_parent(rows,'root',A)
        validate_parent(rows,'root',OTHER)

    def test_missing_moving_folder_and_malformed_hierarchy_fail_closed(self):
        with self.assertRaises(HTTPException) as raised:
            validate_parent([],FOLDER,None)
        self.assertEqual(raised.exception.status_code,404)
        with self.assertRaises(HTTPException):
            validate_parent([{'id':FOLDER,'parent_id':OTHER},{'id':OTHER,'parent_id':FOLDER}],None,None)
        with self.assertRaises(HTTPException):
            validate_parent([{'id':FOLDER,'parent_id':OTHER}],None,None)

    def test_moves_are_explicit_and_rename_cannot_silently_reparent(self):
        for payload in ({'parent_id': None}, {'expected_parent_id':None}, {'parent_id':'bad','expected_parent_id':None}):
            with self.assertRaises(ValidationError): LibraryCollectionMove(**payload)
        with self.assertRaises(ValidationError): LibraryCollectionRename(name='Cream',parent_id=FOLDER)

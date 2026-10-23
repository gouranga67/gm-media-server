import unittest
from uuid import UUID

from app.uploads import parse_upload_hook


class ParseUploadHookTests(unittest.TestCase):
    def test_parses_finished_upload(self) -> None:
        payload = {
            "Type": "post-finish",
            "Event": {
                "Upload": {
                    "ID": "tus-123",
                    "Size": 2048,
                    "MetaData": {
                        "assetId": "11111111-1111-4111-8111-111111111111",
                        "projectId": "22222222-2222-4222-8222-222222222222",
                        "filetype": "video/quicktime",
                    },
                    "Storage": {"Type": "filestore", "Key": "clip-key"},
                }
            },
        }

        facts = parse_upload_hook(payload)

        self.assertEqual(facts.event_type, "post-finish")
        self.assertEqual(facts.asset_id, UUID("11111111-1111-4111-8111-111111111111"))
        self.assertEqual(facts.project_id, UUID("22222222-2222-4222-8222-222222222222"))
        self.assertEqual(facts.upload_id, "tus-123")
        self.assertEqual(facts.storage_key, "clip-key")
        self.assertEqual(facts.byte_size, 2048)
        self.assertEqual(facts.mime_type, "video/quicktime")

    def test_rejects_missing_metadata(self) -> None:
        with self.assertRaisesRegex(ValueError, "metadata"):
            parse_upload_hook(
                {
                    "Type": "post-finish",
                    "Event": {"Upload": {"ID": "tus-123", "Size": 1}},
                }
            )

    def test_pre_create_uses_asset_id_until_tusd_assigns_an_id(self) -> None:
        payload = {
            "Type": "pre-create",
            "Event": {
                "Upload": {
                    "ID": "",
                    "Size": 512,
                    "MetaData": {
                        "assetId": "11111111-1111-4111-8111-111111111111",
                        "projectId": "22222222-2222-4222-8222-222222222222",
                        "filetype": "video/mp4",
                    },
                }
            },
        }

        facts = parse_upload_hook(payload)

        self.assertEqual(facts.upload_id, "11111111-1111-4111-8111-111111111111")
        self.assertEqual(facts.storage_key, "")
        self.assertEqual(facts.mime_type, "video/mp4")


if __name__ == "__main__":
    unittest.main()

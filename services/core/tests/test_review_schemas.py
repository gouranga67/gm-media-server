import unittest

from pydantic import ValidationError

from app.schemas import RevisionCreate


class RevisionSchemaTests(unittest.TestCase):
    def test_requires_feedback_or_caption_correction(self) -> None:
        with self.assertRaises(ValidationError):
            RevisionCreate()

    def test_normalizes_feedback_and_caption_text(self) -> None:
        revision = RevisionCreate.model_validate(
            {
                "note": "  Shorten   the opening. ",
                "caption_corrections": [
                    {
                        "original_text": "  Sidney ",
                        "replacement_text": " Sydney ",
                    }
                ],
            }
        )

        self.assertEqual(revision.note, "Shorten the opening.")
        self.assertEqual(revision.caption_corrections[0].original_text, "Sidney")
        self.assertEqual(revision.caption_corrections[0].replacement_text, "Sydney")

    def test_rejects_duplicate_caption_targets(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot repeat"):
            RevisionCreate.model_validate(
                {
                    "caption_corrections": [
                        {"original_text": "Sidney", "replacement_text": "Sydney"},
                        {"original_text": "Sidney", "replacement_text": "Sydney, Australia"},
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()

"""Unit tests for scripts/contract_sync.py (card E1.1).

Proves: committed zod mirror matches the pydantic contract (the CI
contract-sync gate), the generator subset renders correctly, and unsupported
schema shapes fail loudly instead of generating a wrong contract.
"""
from __future__ import annotations

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts import contract_sync as cs  # noqa: E402


class DriftTest(unittest.TestCase):
    def test_committed_contract_in_sync(self):
        self.assertEqual(cs.main(["--check"]), 0)

    def test_generated_output_matches_committed(self):
        target = os.path.join(REPO, "frontend", "src", "lib", "contract", "contract.ts")
        with open(target, encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(cs.generate(), committed)


class RenderTest(unittest.TestCase):
    def test_primitives(self):
        self.assertEqual(cs.render({"type": "string"}, {}, "x"), "z.string()")
        self.assertEqual(cs.render({"type": "number"}, {}, "x"), "z.number()")
        self.assertEqual(cs.render({"type": "integer"}, {}, "x"), "z.number().int()")
        self.assertEqual(cs.render({"type": "boolean"}, {}, "x"), "z.boolean()")

    def test_const_and_enum(self):
        self.assertEqual(cs.render({"const": "ok"}, {}, "x"), 'z.literal("ok")')
        self.assertEqual(cs.render({"enum": ["a", "b"]}, {}, "x"), 'z.enum(["a", "b"])')

    def test_nullable_optional_object(self):
        schema = {
            "type": "object",
            "properties": {
                "req": {"type": "string"},
                "opt": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None},
            },
            "required": ["req"],
            "additionalProperties": False,
        }
        out = cs.render(schema, {}, "x")
        self.assertIn("req: z.string(),", out)
        self.assertIn("opt: z.number().int().nullable().optional(),", out)
        self.assertTrue(out.endswith("}).strict()"))

    def test_array_of_ref(self):
        defs = {
            "Item": {"type": "object", "properties": {"a": {"type": "number"}}, "required": ["a"]},
        }
        schema = {"type": "array", "items": {"$ref": "#/$defs/Item"}}
        self.assertEqual(cs.render(schema, defs, "x"), "z.array(z.lazy(() => ItemSchema))")

    def test_unsupported_fails_loud(self):
        with self.assertRaises(cs.ContractSyncError):
            cs.render({"type": "map"}, {}, "x")
        with self.assertRaises(cs.ContractSyncError):
            cs.render({"anyOf": [{"type": "string"}, {"type": "integer"}]}, {}, "x")
        with self.assertRaises(cs.ContractSyncError):
            cs.render({"enum": [1, 2]}, {}, "x")


if __name__ == "__main__":
    unittest.main()

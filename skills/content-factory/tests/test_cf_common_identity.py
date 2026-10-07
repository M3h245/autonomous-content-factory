"""Every skill ships its own copy of the contract library; they must stay byte-identical.

    python -m unittest discover -s content-factory/tests -p "test_cf_common_identity.py" -v
"""
import hashlib
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "content-factory" / "scripts" / "cf_common.py"
EXPECTED_COPIES = 15


class CfCommonIdentity(unittest.TestCase):
    def test_all_copies_identical(self):
        copies = sorted(ROOT.glob("*/scripts/cf_common.py"))
        self.assertEqual(len(copies), EXPECTED_COPIES,
                         f"expected {EXPECTED_COPIES} cf_common.py copies, found {len(copies)}: "
                         f"{[c.parent.parent.name for c in copies]}")
        groups = defaultdict(list)
        for c in copies:
            groups[hashlib.sha256(c.read_bytes()).hexdigest()].append(c.parent.parent.name)
        ref = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
        if len(groups) > 1:
            lines = [f"cf_common.py copies DIVERGED ({len(groups)} versions). Reference = content-factory ({ref[:12]})."]
            for h, skills in sorted(groups.items(), key=lambda kv: -len(kv[1])):
                lines.append(f"  {h[:12]} {'(reference)' if h == ref else '(DIFFERENT)':12} {', '.join(sorted(skills))}")
            lines.append("Fix: copy content-factory/scripts/cf_common.py over every other copy, or apply the same edit to all.")
            self.fail("\n".join(lines))


if __name__ == "__main__":
    unittest.main()

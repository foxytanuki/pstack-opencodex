import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def case_collisions(paths):
    """Return groups of distinct tracked spellings that only differ by case.

    Every directory prefix counts as a path too, so a file named UPSTREAM and a
    directory named upstream/ collide on case-insensitive filesystems (default
    macOS and Windows), where one of them cannot be checked out.
    """
    spellings = {}
    for path in paths:
        parts = path.split("/")
        for depth in range(1, len(parts) + 1):
            name = "/".join(parts[:depth])
            spellings.setdefault(name.casefold(), set()).add(name)
    return sorted(sorted(group) for group in spellings.values() if len(group) > 1)


class CaseCollisions(unittest.TestCase):
    def test_helper_flags_a_file_that_collides_with_a_directory(self):
        self.assertEqual(case_collisions(["UPSTREAM", "upstream/LICENSE"]), [["UPSTREAM", "upstream"]])

    def test_helper_allows_shared_parents(self):
        self.assertEqual(case_collisions(["upstream/a", "upstream/b", "tools/x.py"]), [])

    def test_tracked_paths_check_out_on_case_insensitive_filesystems(self):
        if shutil.which("git") is None:
            self.skipTest("git is not available")
        probe = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
        if probe.returncode != 0:
            self.skipTest("not a git work tree")
        listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True)
        paths = [p for p in listed.stdout.decode("utf-8").split("\0") if p]
        self.assertEqual(case_collisions(paths), [])


if __name__ == "__main__":
    unittest.main()

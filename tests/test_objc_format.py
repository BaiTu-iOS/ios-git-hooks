#!/usr/bin/env python3

import sys
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

from check_objc_format import changed_ranges  # noqa: E402
from xcindent import Reindenter  # noqa: E402


class ChangedRangesTests(unittest.TestCase):
    def test_returns_new_side_closed_ranges(self):
        before = "a\nold\nkeep\n"
        after = "a\nnew\nextra\nkeep\n"
        self.assertEqual(changed_ranges(before, after), [(2, 3)])

    def test_pure_deletion_has_no_format_range(self):
        self.assertEqual(changed_ranges("a\ndeleted\nb\n", "a\nb\n"), [])


class XcindentTests(unittest.TestCase):
    def test_router_block_uses_scope_indent(self):
        source = """\
@implementation Foo
- (void)bar {
[router registerProto:@"system.RoomInMessageWrapper"
wrapperClass:BTRoomInMessageWrapper.class
ownedActions:[NSSet setWithObject:kLiveRoomUserRoomIn]
handler:^BTRoomPBMessageHandlerResult(BTMQTTMessage *message, GPBMessage *wrapper) {
__strong __typeof(weakSelf) strongSelf = weakSelf;
if (!strongSelf) {
return BTRoomPBMessageHandlerResultTargetUnavailable;
}
return [strongSelf _handlePBRoomInMessage:message
wrapper:(BTRoomInMessageWrapper *)wrapper];
}];
}
@end
"""
        expected = """\
@implementation Foo
- (void)bar {
    [router registerProto:@"system.RoomInMessageWrapper"
             wrapperClass:BTRoomInMessageWrapper.class
             ownedActions:[NSSet setWithObject:kLiveRoomUserRoomIn]
                  handler:^BTRoomPBMessageHandlerResult(BTMQTTMessage *message, GPBMessage *wrapper) {
        __strong __typeof(weakSelf) strongSelf = weakSelf;
        if (!strongSelf) {
            return BTRoomPBMessageHandlerResultTargetUnavailable;
        }
        return [strongSelf _handlePBRoomInMessage:message
                                          wrapper:(BTRoomInMessageWrapper *)wrapper];
    }];
}
@end
"""
        formatter = Reindenter(width=4)
        actual = formatter.reindent(source)
        self.assertEqual(actual, expected)
        self.assertEqual(formatter.reindent(actual), actual)

    def test_line_ranges_preserve_unchanged_lines(self):
        source = "void f() {\nif (a) {\nx();\n}\n}\n"
        expected = "void f() {\nif (a) {\n        x();\n}\n}\n"
        self.assertEqual(
            Reindenter(width=4).reindent(source, ranges=[(3, 3)]),
            expected,
        )


class PipelineIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        xcrun = shutil.which("xcrun")
        if not xcrun:
            raise unittest.SkipTest("需要 Xcode xcrun")
        result = subprocess.run(
            [xcrun, "--find", "clang-format"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise unittest.SkipTest("需要 Xcode clang-format")
        cls.clang_format = result.stdout.strip()

    def run_command(self, command, cwd, input_text=None):
        return subprocess.run(
            command,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_clang_then_xcindent_accepts_scope_indented_block(self):
        repo_root = Path(__file__).resolve().parents[1]
        checker = repo_root / "hooks/check_objc_format.py"
        style = repo_root / "config/clang-format-config"
        unformatted = """\
@implementation BTFormat
- (void)bar {
[router register:@"x"
handler:^(id value) {
doWork(value);
}];
}
@end
"""

        clang_result = self.run_command(
            [
                self.clang_format,
                "-style=file:{}".format(style),
                "-assume-filename=BTFormat.m",
            ],
            str(repo_root),
            input_text=unformatted,
        )
        self.assertEqual(clang_result.returncode, 0, clang_result.stderr)
        clang_only = clang_result.stdout
        combined = Reindenter(width=4).reindent(clang_only)
        self.assertNotEqual(clang_only, combined)
        self.assertIn("        doWork(value);", combined)

        with tempfile.TemporaryDirectory() as directory:
            temporary_repo = Path(directory)
            self.run_command(["git", "init", "-q"], directory)
            self.run_command(["git", "config", "user.name", "Format Test"], directory)
            self.run_command(
                ["git", "config", "user.email", "format@test.invalid"], directory
            )
            source = temporary_repo / "BTFormat.m"
            source.write_text("@implementation BTFormat\n@end\n")
            self.run_command(["git", "add", "BTFormat.m"], directory)
            commit = self.run_command(
                [
                    "git",
                    "-c",
                    "core.hooksPath=.git/no-hooks",
                    "commit",
                    "-qm",
                    "baseline",
                ],
                directory,
            )
            self.assertEqual(commit.returncode, 0, commit.stderr)

            report = temporary_repo / "format.diff"
            command = [
                sys.executable,
                str(checker),
                "--clang-format",
                self.clang_format,
                "--style",
                str(style),
                "--output",
                str(report),
            ]

            source.write_text(combined)
            valid = self.run_command(command, directory)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)

            source.write_text(clang_only)
            invalid = self.run_command(command, directory)
            self.assertEqual(invalid.returncode, 1, invalid.stdout + invalid.stderr)
            self.assertIn("doWork(value);", report.read_text())


if __name__ == "__main__":
    unittest.main()

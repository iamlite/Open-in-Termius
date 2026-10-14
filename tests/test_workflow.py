"""Regression checks for the embedded AppleScript; no terminal UI is opened."""

import plistlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "Open-in-Termius.app/Contents/document.wflow"


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix="open-in-termius-test-")
        cls.addClassCleanup(cls.work.cleanup)
        cls.compiled = Path(cls.work.name) / "workflow.scpt"
        cls.source = plistlib.loads(WORKFLOW.read_bytes())["actions"][0]["action"][
            "ActionParameters"
        ]["source"]
        script = Path(cls.work.name) / "workflow.applescript"
        script.write_text(cls.source)
        subprocess.run(
            ["osacompile", "-o", str(cls.compiled), str(script)],
            check=True, capture_output=True, text=True,
        )

    def applescript(self, body, *args, overrides=None):
        script = Path(self.work.name) / "check.applescript"
        # Run the actual handlers in the same script context as Automator.
        # Loading an AppKit script into a second script fails with -1700 on
        # this macOS host, before any workflow handler can be called.
        harness = 'on run argv\n' + body.replace("workflow's ", "my ") + '\nend run'
        source, count = re.subn(
            r"on run \{input, parameters\}.*?^end run", lambda _: harness,
            self.source, count=1, flags=re.S | re.M,
        )
        self.assertEqual(count, 1)
        for name, replacement in (overrides or {}).items():
            source, count = re.subn(
                rf"^on {name}\(.*?^end {name}$", lambda _: replacement,
                source, count=1, flags=re.S | re.M,
            )
            self.assertEqual(count, 1, f"Missing handler: {name}")
        script.write_text(source)
        return subprocess.run(
            ["osascript", str(script), *args],
            capture_output=True, text=True, timeout=20,
        )

    def startup(self, states, body):
        # Exercise production sequencing with delayed UI snapshots, without
        # opening apps or sending keys. Exhausted snapshots repeat the last one.
        overrides = {
            "launchTermius": 'on launchTermius()\nset end of my callHistory to "launch"\nend launchTermius',
            "requestTermiusFocus": 'on requestTermiusFocus()\nset end of my callHistory to "focus"\nend requestTermiusFocus',
            "openLocalTerminal": 'on openLocalTerminal()\nset end of my callHistory to "open"\nend openLocalTerminal',
            "pauseForTermius": 'on pauseForTermius()\nend pauseForTermius',
            "readTermiusState": '''on readTermiusState()
set nextIndex to (my snapshotIndex) + 1
if nextIndex > (count of my snapshots) then set nextIndex to count of my snapshots
set my snapshotIndex to nextIndex
set end of my callHistory to "read" & nextIndex
return item nextIndex of my snapshots
end readTermiusState''',
        }
        # Script properties keep stub state visible inside the actual handlers.
        overrides["readTermiusState"] += '''
property snapshots : {}
property snapshotIndex : 0
property callHistory : {}'''
        return self.applescript(
            "set my snapshots to {" + ", ".join(states) + "}\n"
            "set my snapshotIndex to 0\nset my callHistory to {}\n" + body,
            overrides=overrides,
        )

    @staticmethod
    def state(window=False, menu=False, focused=False, title="Termius"):
        flag = lambda value: str(value).lower()
        return (
            "{windowAvailable:" + flag(window) + ", menuAvailable:" + flag(menu)
            + ", isForeground:" + flag(focused) + ', windowTitle:"' + title + '"}'
        )

    def test_cold_start_waits_for_menu_and_focus_before_opening_terminal(self):
        result = self.startup([
            self.state(),
            self.state(window=True),
            self.state(window=True, menu=True),
            self.state(window=True, menu=True),
            self.state(window=True, menu=True, focused=True),
            self.state(window=True, menu=True, focused=True),
            self.state(window=True, menu=True, title="Termius - Local Terminal"),
            self.state(window=True, menu=True, focused=True, title="Termius - Local Terminal"),
        ], 'my prepareLocalTerminal()\nreturn my callHistory')
        self.assertEqual(
            (result.returncode, result.stdout.strip()),
            (0, "launch, read1, read2, read3, focus, read4, read5, open, read6, read7, focus, read8"),
            result.stderr,
        )

    def test_startup_timeout_identifies_unavailable_window_or_menu(self):
        result = self.startup([self.state(window=True)], 'my prepareLocalTerminal()')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("window/menu readiness", result.stderr)
        self.assertIn("menu=false", result.stderr)

    def test_startup_focus_timeout_does_not_open_terminal(self):
        result = self.startup([self.state(window=True, menu=True)], '''
try
    my prepareLocalTerminal()
    error "Expected a focus error"
on error messageText
    if messageText does not contain "foreground focus" then error messageText
    if my callHistory contains "open" then error "Opened terminal before focus"
    return "PASS"
end try''')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "PASS"), result.stderr)

    def test_local_terminal_timeout_names_the_current_window(self):
        result = self.startup(
            [self.state(window=True, menu=True, focused=True)],
            'my prepareLocalTerminal()',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local terminal creation", result.stderr)
        self.assertIn('title=Termius', result.stderr)

    def test_command_guard_rejects_focus_loss_and_nonlocal_windows(self):
        cases = [
            (self.state(window=True, title="Termius - Local Terminal"), "lost focus"),
            (self.state(window=True, focused=True), "not a local terminal"),
        ]
        for state, message in cases:
            with self.subTest(message=message):
                result = self.startup([state], 'my requireLocalTerminal()')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def command(self, path):
        result = self.applescript(
            "return workflow's shellCommand(item 1 of argv)", str(path)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.rstrip("\n")

    def test_enters_literal_paths_and_prints_the_current_directory(self):
        names = [
            "plain", "中文 空格", "single' and \"double\"",
            "$(touch INJECTED)`touch BACKTICK` & ; [x] !",
            "back\\slash $HOME",
        ]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            for name in names:
                with self.subTest(name=name):
                    target = base / name
                    target.mkdir()
                    (target / "expected-entry").touch()
                    result = subprocess.run(
                        ["zsh", "-f", "-c", self.command(target)],
                        cwd=base, capture_output=True, text=True,
                    )
                    self.assertEqual(
                        (result.returncode, result.stdout),
                        (0, f"{target}\n"), result.stderr,
                    )
            self.assertFalse((base / "INJECTED").exists())
            self.assertFalse((base / "BACKTICK").exists())

    def test_failed_cd_does_not_print_the_previous_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            result = subprocess.run(
                ["zsh", "-f", "-c", self.command(base / "missing")],
                cwd=base, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_rejects_line_breaks_before_pasting(self):
        for name in ("/tmp/a\nb", "/tmp/a\rb"):
            with self.subTest(name=name):
                result = self.applescript(
                    "return workflow's shellCommand(item 1 of argv)", name
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("line breaks", result.stderr)

    def check_clipboard(self, body):
        # A private pasteboard exercises real AppKit behavior without touching
        # the user's general clipboard or requiring any UI permissions.
        result = self.applescript(
            "set pb to current application's NSPasteboard's pasteboardWithUniqueName()\n"
            + body
            + '\npb\'s releaseGlobally()\nreturn "PASS"'
        )
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "PASS"), result.stderr)

    def test_restores_multiple_clipboard_items_and_binary_formats(self):
        self.check_clipboard('''
set firstItem to current application's NSPasteboardItem's alloc()'s init()
firstItem's setString:"original 中文" forType:(current application's NSPasteboardTypeString)
set binaryData to current application's NSData's alloc()'s initWithBase64EncodedString:"AAEC//4=" options:0
firstItem's setData:binaryData forType:"org.open-in-termius.test-binary"
set secondItem to current application's NSPasteboardItem's alloc()'s init()
secondItem's setString:"file:///tmp/example" forType:"public.file-url"
pb's writeObjects:{firstItem, secondItem}
set savedItems to workflow's copyClipboard(pb)
pb's clearContents()
pb's setString:"temporary command" forType:(current application's NSPasteboardTypeString)
set ownedCount to pb's changeCount() as integer
workflow's restoreClipboard(pb, savedItems, ownedCount)
set restoredItems to pb's pasteboardItems()
if (restoredItems's |count|() as integer) is not 2 then error "Item count changed"
set restoredFirst to restoredItems's objectAtIndex:0
if ((restoredFirst's stringForType:(current application's NSPasteboardTypeString)) as text) is not "original 中文" then error "Text changed"
set restoredData to restoredFirst's dataForType:"org.open-in-termius.test-binary"
if not (restoredData's isEqualToData:binaryData) then error "Binary data changed"
set restoredSecond to restoredItems's objectAtIndex:1
if ((restoredSecond's stringForType:"public.file-url") as text) is not "file:///tmp/example" then error "File URL changed"
''')

    def test_restores_an_empty_clipboard(self):
        self.check_clipboard('''
set savedItems to workflow's copyClipboard(pb)
pb's setString:"temporary command" forType:(current application's NSPasteboardTypeString)
set ownedCount to pb's changeCount() as integer
workflow's restoreClipboard(pb, savedItems, ownedCount)
if (pb's pasteboardItems()'s |count|() as integer) is not 0 then error "Clipboard is not empty"
''')

    def test_preserves_content_copied_during_the_workflow(self):
        self.check_clipboard('''
pb's setString:"original" forType:(current application's NSPasteboardTypeString)
set savedItems to workflow's copyClipboard(pb)
pb's clearContents()
pb's setString:"temporary command" forType:(current application's NSPasteboardTypeString)
set ownedCount to pb's changeCount() as integer
pb's clearContents()
pb's setString:"new user copy" forType:(current application's NSPasteboardTypeString)
if workflow's restoreClipboard(pb, savedItems, ownedCount) then error "Unexpected restoration"
if ((pb's stringForType:(current application's NSPasteboardTypeString)) as text) is not "new user copy" then error "New copy was overwritten"
''')

    def test_rejects_a_changed_clipboard_before_sending_keys(self):
        self.check_clipboard('''
pb's setString:"temporary command" forType:(current application's NSPasteboardTypeString)
set ownedCount to pb's changeCount() as integer
pb's clearContents()
pb's setString:"new user copy" forType:(current application's NSPasteboardTypeString)
set rejected to false
try
    workflow's requireClipboard(pb, ownedCount)
on error errorMessage
    if errorMessage contains "clipboard changed" then set rejected to true
end try
if not rejected then error "Changed clipboard was accepted"
''')


if __name__ == "__main__":
    unittest.main()

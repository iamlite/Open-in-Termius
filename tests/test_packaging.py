"""Packaging safeguards, plus opt-in real Keychain signing checks."""

import importlib.util
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("package_app", ROOT / "scripts/package_app.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class PackagingTests(unittest.TestCase):
    def test_missing_identity_requires_explicit_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "Run:.*setup"):
                package.load_identity(Path(directory))

    def test_bundle_id_change_is_rejected_before_signing(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "Changed.app"
            (app / "Contents").mkdir(parents=True)
            (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "other.app"}))
            with self.assertRaisesRegex(RuntimeError, "Bundle ID changed"):
                package.sign_app(app, {})

    def test_missing_key_does_not_fall_back_to_ad_hoc_signing(self):
        identity = {"sha1": "A" * 40, "keychain": "missing.keychain"}
        with patch.object(package, "run") as command:
            command.return_value.stdout = "0 valid identities found"
            with self.assertRaisesRegex(RuntimeError, "Do not generate a replacement"):
                package.require_identity(identity)

    def test_install_rejects_a_symlink_without_touching_its_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.app"
            original.mkdir()
            link = root / package.APP_NAME
            link.symlink_to(original)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                package.install_app(root / "new.app", link, {}, root / "backups")
            self.assertTrue(link.is_symlink())

    def test_successful_install_removes_obsolete_files_but_keeps_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "new.app", root / package.APP_NAME
            for app in (source, target):
                (app / "Contents").mkdir(parents=True)
                (app / "Contents/Info.plist").write_bytes(
                    plistlib.dumps({"CFBundleIdentifier": package.BUNDLE_ID})
                )
            (source / "new-file").write_text("new")
            (target / "old-file").write_text("original")
            inode = target.stat().st_ino
            with patch.object(package, "verify_app"):
                backup = package.install_app(source, target, {}, root / "backups")
            self.assertEqual(
                (target.stat().st_ino, (target / "new-file").read_text(), (target / "old-file").exists()),
                (inode, "new", False),
            )
            self.assertEqual((backup / "old-file").read_text(), "original")

    def test_failed_install_restores_old_contents_and_toolbar_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "new.app", root / package.APP_NAME
            source.mkdir()
            (source / "new-file").write_text("new")
            (target / "Contents").mkdir(parents=True)
            (target / "Contents/Info.plist").write_bytes(
                plistlib.dumps({"CFBundleIdentifier": package.BUNDLE_ID})
            )
            (target / "old-file").write_text("original")
            inode = target.stat().st_ino
            with patch.object(package, "verify_app", side_effect=[None, RuntimeError("bad install")]):
                with self.assertRaisesRegex(RuntimeError, "bad install"):
                    package.install_app(source, target, {}, root / "backups")
            self.assertEqual(
                (target.stat().st_ino, (target / "old-file").read_text(), (target / "new-file").exists()),
                (inode, "original", False),
            )
            self.assertEqual(len(list((root / "backups").glob("*/Open-in-Termius.app/old-file"))), 1)


@unittest.skipUnless(os.environ.get("OPEN_IN_TERMIUS_SIGNING_TESTS") == "1", "Opt-in real signing test")
class RealSigningTests(unittest.TestCase):
    def test_changed_workflow_keeps_identity_and_zip_preserves_signatures(self):
        identity = package.load_identity()
        package.require_identity(identity)
        with tempfile.TemporaryDirectory(prefix="termius signing test ") as directory:
            root = Path(directory)
            apps = []
            for version in (1, 2):
                app = root / str(version) / package.APP_NAME
                package.copy_app(ROOT / package.APP_NAME, app)
                workflow = app / "Contents/document.wflow"
                data = plistlib.loads(workflow.read_bytes())
                data["actions"][0]["action"]["ActionParameters"]["source"] += f"\n-- signing test {version}\n"
                workflow.write_bytes(plistlib.dumps(data))
                package.sign_app(app, identity)
                apps.append(app)
            results = [package.run(package.CODESIGN, "-d", "-r-", "--verbose=4", app) for app in apps]
            outputs = [result.stdout + result.stderr for result in results]
            requirements = [next(line for line in out.splitlines() if line.startswith("designated =>")) for out in outputs]
            hashes = [next(line for line in out.splitlines() if line.startswith("CDHash=")) for out in outputs]
            self.assertEqual(requirements[0], requirements[1])
            self.assertNotEqual(hashes[0], hashes[1])
            self.assertNotIn("cdhash", requirements[0])
            for app in apps:
                package.run(package.CODESIGN, "--verify", "--deep", "--strict", "-R", "=" + requirements[0].split("=>", 1)[1].strip(), app)
            package.archive_app(apps[1], root / "local update.zip", identity)
            workflow = apps[1] / "Contents/document.wflow"
            workflow.write_bytes(workflow.read_bytes() + b"\n")
            with self.assertRaises(RuntimeError):
                package.verify_app(apps[1], identity)


if __name__ == "__main__":
    unittest.main()

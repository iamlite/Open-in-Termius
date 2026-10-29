#!/usr/bin/env python3
"""Local-only signing and packaging using one persistent Keychain identity."""

import argparse
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import ssl
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "Open-in-Termius.app"
BUNDLE_ID = "com.apple.automator.TermiusLocal"
CERT_NAME = "Open-in-Termius Local Code Signing"
STATE = Path.home() / "Library/Application Support/Open-in-Termius"
SECURITY = "/usr/bin/security"
OPENSSL = "/usr/bin/openssl"
CODESIGN = "/usr/bin/codesign"


def run(*args, check=True):
    result = subprocess.run(
        [str(arg) for arg in args], capture_output=True, text=True,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"{Path(str(args[0])).name} failed ({result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def fingerprint(pem):
    return hashlib.sha1(ssl.PEM_cert_to_DER_cert(pem)).hexdigest().upper()


def load_identity(state=STATE):
    path = state / "signing.json"
    if not path.exists():
        raise RuntimeError("No fixed signing identity. Run: python3 scripts/package_app.py setup")
    identity = json.loads(path.read_text())
    if (identity.get("bundle_id") != BUNDLE_ID
            or not re.fullmatch(r"[0-9A-F]{40}", identity.get("sha1", ""))
            or not Path(identity.get("keychain", "")).is_file()):
        raise RuntimeError(f"Invalid signing configuration: {path}. Restore the original identity.")
    return identity


def require_identity(identity):
    result = run(SECURITY, "find-identity", "-v", "-p", "codesigning", identity["keychain"])
    hashes = re.findall(r"\b[0-9A-F]{40}\b", result.stdout)
    if identity["sha1"] not in hashes:
        raise RuntimeError(
            "The saved certificate/private key is unavailable or untrusted. "
            "Unlock the original keychain or run setup to restore its code-signing trust. "
            "Do not generate a replacement certificate."
        )


def setup_identity():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = STATE / "signing.json"
    public_cert = STATE / "signing-certificate.pem"
    if config.exists():
        identity = load_identity()
        pem = public_cert.read_text()
        if fingerprint(pem) != identity["sha1"]:
            raise RuntimeError("Saved certificate does not match signing.json; restore the original files.")
    else:
        keychain = run(SECURITY, "default-keychain", "-d", "user").stdout.strip().strip('"')
        existing = run(
            SECURITY, "find-certificate", "-a", "-p", "-c", CERT_NAME, keychain, check=False,
        )
        if existing.returncode not in (0, 44):
            raise RuntimeError(f"Cannot inspect signing certificates: {existing.stderr.strip()}")
        certificates = re.findall(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", existing.stdout, re.S,
        )
        if len(certificates) > 1:
            raise RuntimeError("Multiple local signing certificates found. Resolve the ambiguity first.")
        if certificates:
            pem = certificates[0] + "\n"
        else:
            # Private material exists only in this owner-only temporary directory.
            with tempfile.TemporaryDirectory(prefix="signing-", dir=STATE) as work:
                work = Path(work)
                settings = work / "certificate.cnf"
                settings.write_text(
                    "[req]\nprompt = no\ndistinguished_name = subject\n"
                    "x509_extensions = signing\n[subject]\nCN = " + CERT_NAME + "\n"
                    "[signing]\nbasicConstraints = critical,CA:false\n"
                    "keyUsage = critical,digitalSignature\nextendedKeyUsage = codeSigning\n"
                    "subjectKeyIdentifier = hash\n"
                )
                run(
                    OPENSSL, "req", "-new", "-newkey", "rsa:3072", "-nodes", "-x509",
                    "-sha256", "-days", "3650", "-config", settings,
                    "-keyout", work / "key.pem", "-out", work / "certificate.pem",
                )
                # security's openssl importer expects traditional RSA PEM, not PKCS#8.
                run(OPENSSL, "rsa", "-in", work / "key.pem", "-out", work / "key-rsa.pem")
                print("Importing the local signing identity into your keychain…", flush=True)
                run(
                    SECURITY, "import", work / "key-rsa.pem", "-k", keychain,
                    "-f", "openssl", "-t", "priv", "-T", CODESIGN,
                )
                run(SECURITY, "import", work / "certificate.pem", "-k", keychain, "-t", "cert")
                pem = (work / "certificate.pem").read_text()
        identity = {"sha1": fingerprint(pem), "keychain": keychain, "bundle_id": BUNDLE_ID}
        # Persist before requesting trust, so an interrupted setup reuses this certificate.
        public_cert.write_text(pem)
        config.write_text(json.dumps(identity, indent=2) + "\n")

    available = run(SECURITY, "find-identity", "-p", "codesigning", identity["keychain"])
    if identity["sha1"] not in available.stdout:
        raise RuntimeError("The original private key is missing. Restore it from your Keychain backup.")
    valid = run(SECURITY, "find-identity", "-v", "-p", "codesigning", identity["keychain"])
    if identity["sha1"] not in valid.stdout:
        print("Setting user-level trust for code signing only; macOS may request authentication…", flush=True)
        run(
            SECURITY, "add-trusted-cert", "-r", "trustRoot", "-p", "codeSign",
            "-k", identity["keychain"], public_cert,
        )
    require_identity(identity)
    print(f"Fixed signing identity ready: {CERT_NAME}\nSHA-1: {identity['sha1']}\nConfig: {config}")


def requirement(identity, identifier=BUNDLE_ID):
    return f'identifier "{identifier}" and certificate leaf = H"{identity["sha1"]}"'


def validate_bundle_id(app):
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise RuntimeError("Bundle ID changed; refusing to create a different permission identity.")


def copy_app(source, destination):
    # ditto preserves signatures stored in extended attributes on document.wflow.
    run("/usr/bin/ditto", "--rsrc", "--extattr", source, destination)


def verify_app(app, identity):
    run(CODESIGN, "--verify", "--deep", "--strict", "-R", "=" + requirement(identity), app)


def sign_app(app, identity):
    validate_bundle_id(app)
    # Clear stale signatures and download/Finder metadata only on the build copy.
    run("/usr/bin/xattr", "-cr", app)
    # Automator's workflow is nested signed code. Sign it before the enclosing app.
    for target, identifier in (
        (app / "Contents/document.wflow", BUNDLE_ID + ".workflow"), (app, BUNDLE_ID),
    ):
        run(
            CODESIGN, "--force", "--sign", identity["sha1"], "--keychain", identity["keychain"],
            "--timestamp=none", "--identifier", identifier,
            "--requirements", "=designated => " + requirement(identity, identifier), target,
        )
    verify_app(app, identity)


def archive_app(app, archive, identity):
    run("/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, archive)
    with tempfile.TemporaryDirectory(prefix="archive-check-", dir=archive.parent) as extracted:
        run("/usr/bin/ditto", "-x", "-k", archive, extracted)
        verify_app(Path(extracted) / app.name, identity)


def clear_app_contents(app):
    for child in app.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def install_app(source, destination, identity, backup_root):
    if destination.is_symlink():
        raise RuntimeError("Refusing to replace a symlink installation.")
    verify_app(source, identity)
    backup = None
    if destination.exists():
        validate_bundle_id(destination)
        backup = backup_root / datetime.now().strftime("%Y%m%d-%H%M%S-%f") / APP_NAME
        backup.parent.mkdir(parents=True)
        copy_app(destination, backup)
        print(f"Previous app backed up: {backup}", flush=True)
    try:
        if destination.exists():
            # Preserve the app directory inode so Finder toolbar aliases keep their target.
            clear_app_contents(destination)
        copy_app(source, destination)
        verify_app(destination, identity)
    except Exception:
        if destination.exists():
            clear_app_contents(destination)
        if backup is not None:
            copy_app(backup, destination)
            print(f"Installation failed; restored: {backup}", file=sys.stderr)
        raise
    print(f"Installed: {destination}")
    return backup


def build(install=False):
    identity = load_identity()
    require_identity(identity)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
    source = ROOT / APP_NAME
    run("/usr/bin/plutil", "-lint", source / "Contents/Info.plist", source / "Contents/document.wflow")
    output = ROOT / "dist" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output.mkdir(parents=True)
    app = output / APP_NAME
    copy_app(source, app)
    sign_app(app, identity)
    archive = output / "Open-in-Termius.zip"
    archive_app(app, archive, identity)
    print(f"Verified local app: {app}\nVerified archive: {archive}", flush=True)
    if install:
        destination = Path("/Applications") / APP_NAME
        executable = destination / "Contents/MacOS/Automator Application Stub"
        running = run(
            "/usr/bin/pgrep", "-f", "^" + re.escape(str(executable)) + r"([[:space:]]|$)", check=False,
        )
        if running.returncode != 1:
            raise RuntimeError("Close Open-in-Termius before installing, then rerun build --install.")
        install_app(app, destination, identity, STATE / "backups")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="Create or reuse the fixed local Keychain identity")
    package = commands.add_parser("build", help="Test, sign, verify and archive the local app")
    package.add_argument("--install", action="store_true", help="Back up and update /Applications")
    args = parser.parse_args()
    try:
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        # A second build/setup must not replace a live installation or create a second identity.
        with (STATE / "operation.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another local setup/build is running. Wait for it to finish.")
            if args.command == "setup":
                setup_identity()
            else:
                build(args.install)
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()

# Open-in-Termius

![Termius Logo](https://assets-global.website-files.com/5c7036349b5477bf13f828cf/6369e92d535e22776a8a681c_Brand%20Logo.svg)

Open-in-Termius is a simple macOS application created with Automator. It allows you to open the current Finder directory in a Termius terminal with just one click.

## Features

- **Convenience**: Quickly open the current Finder directory in a Termius terminal.
- **Easy Installation**: Simple steps to get up and running.
- **Automator Power**: Created using Automator, making it accessible to all users.

## Installation

1. Download the latest release of Open-in-Termius from the [Releases](https://github.com/iamlite/Open-in-Termius/releases) page.
2. Unzip the downloaded file.
3. Move the `Open-in-Termius.app` file to your Applications folder.
4. Open a Finder window and navigate to your Applications folder.
5. Command-drag the `Open-in-Termius.app` file to the Finder toolbar.

## Usage

1. Navigate to any directory in Finder.
2. Click the Open-in-Termius icon in the Finder toolbar.
3. This will open Termius and navigate to the current Finder directory in a new local terminal.

The command is pasted as a single string, so Chinese input methods do not
convert the command or path. Paths are shell-quoted, and `pwd` prints the
current directory only after `cd` succeeds. The previous clipboard items and
formats are restored after pasting, unless you copied something else while
the workflow was running.

Keep Termius in the foreground until the command finishes. Startup first waits
for a window and an enabled `File → New Local Terminal` menu item, then requests
foreground focus and uses that native menu item. It waits for the local-terminal
window separately and reacquires focus before preparing the command. The initial
window/menu wait allows 120 polls, local-terminal creation 60 polls, and each
focus wait 20 polls, with 0.25 seconds between polls. Timeout errors identify the
stage and last observed window, menu, focus, and title state.

A short settling period follows terminal creation. This is a UI readiness check,
not a shell prompt check; custom startup scripts or unusually slow systems may
still need another try. The workflow expects the English menu names above and a
window title containing `Local Terminal` (inspected with Termius 9.43.1).
After command preparation starts, losing focus aborts the operation instead of
redirecting a paste or Return to another app.

Open a Finder folder window first. Finder locations that cannot be converted
to a filesystem folder, and folder names containing line breaks, are not
supported. macOS must allow the app to control Finder and System Events and
send keystrokes through Accessibility. If it reports a permission error,
check the app's existing permissions in System Settings → Privacy & Security.

## Development and verification

The AppleScript source is embedded in
`Open-in-Termius.app/Contents/document.wflow`. No Maven or Java build is used.
On macOS, run the focused checks with Python 3 and the built-in AppleScript
compiler and zsh:

```bash
python3 -m unittest discover -s tests -v
plutil -lint Open-in-Termius.app/Contents/document.wflow
```

The checks compile the script and verify delayed startup states, focus guards,
stage-specific timeouts, literal path handling, failed `cd`, and clipboard
restoration using private pasteboards. Startup checks substitute UI snapshots
and actions; they do not open Finder or Termius. Also check the installed app
from the Finder toolbar with both
ABC and a Chinese input method, including a folder containing spaces and
Chinese characters. Verify that the new local terminal enters that folder
and that the previous clipboard content is still available.

### Local builds with a fixed signing identity

For this Mac, use a persistent self-signed certificate instead of ad-hoc signing.
Run the one-time setup in a terminal from this repository:

```bash
python3 scripts/package_app.py setup
```

Setup creates `Open-in-Termius Local Code Signing` in your default user keychain
(normally the login keychain), valid for ten years, and sets **user-level,
code-signing-only** trust. macOS may ask you to authenticate. The private key is
imported with access restricted to `/usr/bin/codesign`; temporary private-key
files are removed after import. Repeating setup reuses the original certificate.
The public certificate and its pinned fingerprint are stored outside Git in
`~/Library/Application Support/Open-in-Termius/`.

Build, verify, back up the previous installation, and update the app:

```bash
python3 scripts/package_app.py build --install
```

Omit `--install` to produce only the app and ZIP under `dist/<timestamp>/`.
Each build runs the automated checks, validates the plists, copies the source
bundle, signs the workflow and then the app, and verifies the result. ZIPs use
`ditto` to preserve the workflow's signature attributes and are verified again
after extraction. Use Finder/Archive Utility or `ditto` to extract them; a ZIP
tool that drops macOS extended attributes can invalidate the workflow signature.

The signature requirement pins both the existing Bundle ID
`com.apple.automator.TermiusLocal` and the certificate fingerprint, rather than a
particular build's code hash. A missing identity, changed Bundle ID, failed
check, or invalid archive stops the build. The script never falls back to ad-hoc
signing or silently replaces a lost certificate. Source bundles in Git are not
re-signed; always install the generated copy.

Before installation, close Open-in-Termius itself (Termius may stay open).
The previous app is copied to
`~/Library/Application Support/Open-in-Termius/backups/<timestamp>/`.
Installation preserves the app directory so Finder toolbar aliases retain their
target, and restores the backup if copying or verification fails. Older build
outputs and backups are retained.

The first use of the private key may show a `codesign` Keychain dialog. Choose
**Always Allow** for this signing key, rather than **Allow** for one operation.
If a background build reports `errSecInternalComponent` without a visible
dialog, run the command in your normal interactive terminal to complete that
one-time authorization. Do not send your login password to chat or put it in a
script. This key-access prompt is separate from the app's Automation and
Accessibility permissions.

Switching from the old ad-hoc identity to this certificate can require one final
app authorization under System Settings → Privacy & Security → Accessibility
and Automation. On this Mac's macOS 27, the Accessibility permission is listed
under **Device Control and Data Access**. If the old entry is enabled but the
new app still reports "not allowed assistive access", remove that app's old entry
and add `/Applications/Open-in-Termius.app` once to record its new identity.
After that, updates signed by the same identity should retain
those permissions. The build never edits or resets macOS's permission database.
This is a local-use signature, not Developer ID signing or notarization.

Keep the certificate **and its private key** in the login keychain. For recovery,
export that identity from Keychain Access as a password-protected `.p12` and keep
it in a secure backup outside Git, along with the signing configuration. The
public `.pem` file alone cannot restore signing ability. Recreating a certificate
with the same name does not preserve its identity; losing/replacing it, resetting
privacy permissions, or changing Bundle ID can require authorization again.

To test two different workflow builds against the same real signing identity,
including ZIP round-trip verification and tamper rejection, run:

```bash
OPEN_IN_TERMIUS_SIGNING_TESTS=1 python3 -m unittest discover -s tests -v
```

This opt-in check signs temporary copies without launching Finder or Termius.
It verifies code identity compatibility; actual permission retention must also
be checked by updating an already-authorized installed app and using its Finder
toolbar button again. See Apple's [code identity explanation](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements).

### Local signing acceptance (2026-10-15)

On this Mac (macOS 27), all 19 checks passed with real signing enabled, including
ZIP extraction, changed-build identity compatibility, and tamper rejection.
After the one-time Keychain authorization and replacement of the old
Accessibility entry, the Finder toolbar opened the expected directory in
Termius. A workflow build with a different code hash was then installed using
the same certificate and requirement; the toolbar still worked without another
permission prompt. Restoring the production build passed the same live check.
The installed workflow matches the repository source, and previous installations
are retained in the backup directory. This confirms the update path on this Mac;
it does not cover a replaced certificate or reset system permissions.

### Local acceptance (2026-10-14)

The installed app was verified with Termius 9.43.1 after re-adding it to macOS
control permissions. Finder toolbar clicks opened new local terminals in the
expected directory for all of these cases:

| Input mode | Finder folder | Result |
| --- | --- | --- |
| Existing input source | Project directory | Passed |
| ABC | `中文 空格 '引号' $符号` | Passed |
| Rime Chinese mode | `中文 空格 '引号' $符号` | Passed |

Rime Chinese composition was confirmed with the `ni` → `你` candidate before
the click. The new zsh processes' working directories matched the Finder
folder, and clipboard text was unchanged after both input-mode checks.
All seven automated checks also passed. Agent-run manual acceptance covered
an already-running Termius instance; the user subsequently confirmed that
cold launch also worked correctly with that build.

The follow-up change replaces `&& ls` with `&& pwd` to display the current
directory. Its automated checks verify the printed path and confirm that a
failed `cd` does not print the previous directory.

Subsequent agent-run cold-start checks of that follow-up build reproduced two
15-second readiness timeouts without creating a local terminal. The startup
repair separates window/menu readiness from focus and uses the native menu
instead of an early keyboard shortcut.

After re-signing and renewing the installed app's macOS control permission,
the startup repair passed these Finder toolbar checks:

| Termius state | Finder folder | Result |
| --- | --- | --- |
| Fully stopped, first launch | Existing folder containing Chinese and spaces | Passed |
| Fully stopped, second launch | Same Chinese/spaces folder | Passed |
| Already running | Project directory | Passed |

Both cold checks confirmed zero Termius processes before the click. Each run
displayed `cd -- '…' && pwd` and the expected path, and the new zsh process's
working directory matched it. Clipboard text was unchanged across the checks;
the selected input source was Rime. All 12 automated checks, AppleScript
compilation, workflow plist validation, and installed signature verification
passed. The real UI checks cover Termius 9.43.1 on this Mac, not arbitrary shell
startup delays or other Termius versions.

## Contributing

Contributions are welcome! If you have any ideas, suggestions, or bug reports, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

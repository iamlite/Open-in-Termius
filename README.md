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

Keep Termius in the foreground until the command finishes. The workflow checks
for a local-terminal window for up to 15 seconds and allows a short settling
period before pasting. This is a UI readiness check, not a shell prompt check;
custom startup scripts or unusually slow systems may still need another try.
The workflow expects the default `Command-L` shortcut and a window title
containing `Local Terminal` (verified with Termius 9.43.1).

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

The checks compile the script and verify literal path handling, failed `cd`,
and clipboard restoration using private pasteboards. They do not open Finder
or Termius. Also check the installed app from the Finder toolbar with both
ABC and a Chinese input method, including a folder containing spaces and
Chinese characters. Verify that the new local terminal enters that folder
and that the previous clipboard content is still available.

Back up the installed app before replacing its workflow. Editing a signed app
invalidates its signature; a local development copy can be signed again with
`codesign --force --deep --sign - /Applications/Open-in-Termius.app`, then
checked with `codesign --verify --deep --strict /Applications/Open-in-Termius.app`.
This is a local ad-hoc signature, not notarization. macOS may ask you to
re-authorize the updated app.

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

## Contributing

Contributions are welcome! If you have any ideas, suggestions, or bug reports, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

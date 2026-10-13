## Stage 1: Reliable command delivery
**Goal**: Quote Finder paths safely and paste commands without input-method conversion.
**Success Criteria**: Preserve clipboard formats, bound Termius waits, and report missing windows or permissions clearly.
**Tests**: Compile AppleScript; exercise shell quoting and clipboard preservation.
**Status**: Complete

## Stage 2: Regression checks and documentation
**Goal**: Add focused checks and document behavior and limitations.
**Success Criteria**: Commands handle Chinese, spaces, quotes, and shell metacharacters; failed cd does not run ls.
**Tests**: Standard-library Python tests using macOS osascript and zsh; plist validation.
**Status**: Complete

## Stage 3: Installed application verification
**Goal**: Back up the installed workflow, update it, and verify Finder-to-Termius behavior.
**Success Criteria**: Verify real local-terminal navigation and clipboard restoration; report any unavailable UI checks.
**Tests**: Finder launch under ABC and Chinese input; installed/source equality; final diff review.
**Status**: In Progress

Installed app backed up to ~/Library/Application Support/Open-in-Termius/Backups/20261014-001900/Open-in-Termius.app.zip and re-signed locally. Launch reaches the workflow, but macOS returns "TermiusLocal is not allowed assistive access". User re-authorization is required before UI verification can continue.

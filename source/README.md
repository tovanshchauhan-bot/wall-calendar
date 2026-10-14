# Wall Calendar: source

The repository root holds the built app that GitHub Pages serves. This folder holds what it is built from.

- `calendar.html` is the calendar itself: layout, styles and behaviour. The same file also runs as the claude.ai version.
- `build.py` turns it into the installable offline app. It adds Google sign-in and Firestore sync, the service worker, icons, manifest and self-hosted fonts.
- `config.prod.js` holds this app's Firebase project settings. They identify the project and are not a password. `config.test.js` points at local emulators instead.

## Change, check, publish

    ./test.sh      # end-to-end check against a local sign-in emulator
    ./build.sh     # writes the built app into the repository root
    git add -A && git commit -m "Describe the change" && git push

GitHub Pages redeploys within about a minute. An open app window picks up the new version the next time it is opened or reloaded (Cmd+R) while online.

`test.sh` needs Node and Python 3 with Pillow and Playwright (Chromium). It checks sign-in, importing a backup, ticking days, adding an assessment, opening and saving offline, and the sync status pill.

## Data

Data lives in Firestore under `users/{uid}/`, in `items`, `gym`, `run` and `config/settings`. Code changes never touch it. Keep these paths when changing the app, and add new collections beside them rather than renaming, so existing data keeps syncing. The Firestore security rules (set in the Firebase console, not in this repository) limit access to one Google account.

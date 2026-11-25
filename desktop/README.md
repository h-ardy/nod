# Nod Dot

A tiny dot in a corner of your screen. Most of the time you won't notice it. When an AI tool asks for approval, it turns amber, or red if the request is risky. Hold your Nod key for half a second and the dot pulses twice and opens into a panel with the whole request. Tap the key to approve, double-tap to reject.

Runs on macOS and Windows. It talks to the Nod daemon on your own computer (`nod daemon`), on 127.0.0.1 only.

## Run it

You need Node.js 20 or newer and the Nod daemon running.

```
cd desktop
npm install
npm start
```

The dot appears in the top-right corner. Click its icon in the menu bar (Mac) or system tray (Windows) to move it to another corner, turn on "Open at login", or quit.

## Build an installer

```
npm run dist:mac    # on a Mac: makes a .dmg in dist/
npm run dist:win    # on Windows: makes an installer .exe in dist/
```

These builds aren't code-signed yet, so the first launch shows a warning:
- Mac: right-click the app and choose Open, or allow it under System Settings > Privacy & Security.
- Windows: on the SmartScreen prompt, choose More info, then Run anyway.

## What it shows

- Where the request came from (Claude Code, git, Codex and so on) and which key it's on.
- A 3-letter code. Your key shows the same code once the panel is open, so you know you're approving the request you just read.
- Why it was flagged as risky, if it was.
- The short summary the key shows, then the full request: the whole command, the full diff of an edit, the commits in a push.
- Claude's own one-line reason, labelled as Claude's. The rest of the panel is built from the real command or file, never from what the model says it's doing.

## What it can't do

The panel can't approve or reject anything. It can only open and close itself. Answers come from a press on the key.

While the panel is closed, every click passes straight through the dot to whatever is underneath.

## Files

- `main.js`: the window, tray menu, corner setting and click-through.
- `preload.js`: the small bridge between the panel and the app.
- `renderer/`: the dot and panel (HTML, CSS, JS). For testing it also opens in a browser: `renderer/index.html?port=47823&token=<your token>&corner=top-right`.
- `assets/fonts/`: Bricolage Grotesque, Instrument Sans and JetBrains Mono, all under the SIL Open Font License (licenses included).

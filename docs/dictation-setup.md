# Dictation Setup Guide

## Step 1: Run `rec dictate` once to trigger permission prompts

macOS won't ask for permissions until the app actually tries to use them. Run:

    rec dictate

and attempt a double-tap. You will see two system permission dialogs:

### Input Monitoring

Required for `rec dictate` to detect global key presses from any app.

1. macOS shows: "Terminal wants to monitor input from your keyboard"
2. Click **Open System Settings**
3. Go to **Privacy & Security → Input Monitoring**
4. Toggle your terminal app (Terminal, iTerm2, Warp, etc.) **on**

### Accessibility

Required to simulate Cmd+V to paste the transcript at the cursor.

1. macOS shows: "Terminal wants access to control this computer"
2. Click **Open System Settings**
3. Go to **Privacy & Security → Accessibility**
4. Toggle your terminal app **on**

After granting both, re-run `rec dictate`. You should not see the prompts again.

---

> **Tip:** If you granted permission but `rec dictate` still can't listen, try removing
> the entry from Input Monitoring and re-adding it. macOS occasionally gets the permission
> state out of sync after updates.

---

## Step 2 (optional): Auto-start on login with a LaunchAgent

A LaunchAgent runs `rec dictate` automatically when you log in, so dictation is always
available without opening a terminal.

### Create the plist

Create `~/Library/LaunchAgents/com.liscribe.dictate.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.liscribe.dictate</string>

    <key>ProgramArguments</key>
    <array>
        <!-- Replace /path/to/liscribe/venv with your actual venv path -->
        <!-- Run: echo $(which rec) to find it -->
        <string>/path/to/liscribe/venv/bin/rec</string>
        <string>dictate</string>
        <string>--no-sounds</string>
    </array>

    <!-- Log stdout and stderr to files you can inspect -->
    <key>StandardOutPath</key>
    <string>/tmp/liscribe-dictate.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/liscribe-dictate-error.log</string>

    <!-- Restart automatically if it crashes -->
    <key>KeepAlive</key>
    <true/>

    <!-- Wait for login to complete before starting -->
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

Find your `rec` binary path with:

    which rec

### Load the agent

    launchctl load ~/Library/LaunchAgents/com.liscribe.dictate.plist

### Verify it is running

    launchctl list | grep liscribe

You should see a line like `- 0 com.liscribe.dictate`. The `0` exit code means it is
running.

### Check logs

    tail -f /tmp/liscribe-dictate.log
    tail -f /tmp/liscribe-dictate-error.log

### Stop / unload

    launchctl unload ~/Library/LaunchAgents/com.liscribe.dictate.plist

### Permanently remove auto-start

    launchctl unload ~/Library/LaunchAgents/com.liscribe.dictate.plist
    rm ~/Library/LaunchAgents/com.liscribe.dictate.plist

---

> **Note on sounds with LaunchAgent:** When running as a LaunchAgent, `rec dictate` has
> no terminal window. Use `--no-sounds` if you find the sounds play unexpectedly, or leave
> them on — macOS notifications still appear regardless.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not start keyboard listener" on first run | Grant Input Monitoring in System Settings |
| Paste does nothing (text not appearing) | Grant Accessibility in System Settings |
| Double-tap not detected | Check the hotkey matches your config: `rec config --show` |
| Wrong hotkey | Change in **Preferences → Dictation**, or `rec dictate --hotkey right_ctrl` |
| No sound but notifications appear | Expected if `afplay` is unavailable; sounds need macOS built-in `afplay` |
| LaunchAgent won't start | Run `launchctl list \| grep liscribe`; check error log at `/tmp/liscribe-dictate-error.log` |
| Permission granted but still failing | Remove from Input Monitoring, re-add, then re-run |

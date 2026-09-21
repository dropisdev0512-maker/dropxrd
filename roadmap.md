# DropX roadmap

## PC agent (public/agent.py) — brain + executor
- [ ] Rewrite as single-file server with full endpoint set
- [ ] /voice + /type natural-language intent engine (no frontend parsing)
- [ ] Power: wake, shutdown(+cancel), lock, sleep
- [ ] System: screenshot, volume, brightness, media, window, battery, disk, net, processes, kill, clipboard
- [ ] Apps/files: app, url, open, close, upload, command
- [ ] Notes + reminders
- [ ] Dev: scaffold, qa
- [ ] Email / Calls / DMs / Mods endpoints (status stubs where creds absent)
- [ ] /history

## Frontend redesign
- [ ] Design tokens: muted glass palette, typography, spacing
- [ ] Softer/slower galaxy background (opacity 0.4)
- [ ] Sticky glass header + status pill, live status bar
- [ ] Bottom floating nav: Home / Email / Calls / Messages / Mods
- [ ] Chat thread UI (bubbles, action chips, persist 100 in localStorage)
- [ ] Push-to-talk walkie-talkie button + Type button + command bar
- [ ] Quick action chips row
- [ ] Power card, PC stats card, file drop zone
- [ ] Settings modal (connection, voice, appearance, email, phone, messages, mods, data)
- [ ] Confirm modals for shutdown/kill/command/send/call
- [ ] Auto-reconnect banner, themes, notes pad, reminders, history drawer, driving mode
- [ ] PWA manifest + public/ cleanup

## Verify
- [ ] Run agent locally, confirm every endpoint responds
- [ ] Browser check of each button

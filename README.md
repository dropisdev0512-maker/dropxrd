# DropX Remote Console

Build a mobile-first web app called "DropX" — a remote control panel for my PC.



DESIGN:

- Mac-inspired glassmorphism theme

- Dark navy blue gradient background (#0a1229 → #0d1b3d → #050a1a)

- Translucent frosted glass cards with backdrop-blur

- Light blue accent (#7fb6ff) and secondary (#4a8fff)

- Rounded corners (22px radius), soft shadows

- Full-screen animated galaxy orb + wave background (canvas)

- Sticky glass header with brand "DropX" + connection status pill



LAYOUT (single column on phone, grid on tablet):

1. Header: "DropX" brand + status pill ("PC online" green / "PC offline" red)

2. Power card: Wake PC button, Shutdown button (red), Cancel Shutdown (ghost)

3. DevOps card: dropdown (Python CLI / Fabric Mod / Web), path input, Scaffold button, QA path input, Run QA button

4. Assist card: app path input, window title input, Open button, call message input, Call Me button

5. DropX card: big mic button "🎤 Speak", big button "Say DropX", live log box below



BEHAVIOR:

- On load, ask user for PC API URL (Tailscale IP like http://100.x.x.x:8765)

- Save it to localStorage as "dropx_api"

- Add a small gear icon top-right to change it later

- Every 5 seconds: GET /status → update pill

- All buttons send POST to the saved API base

- Mic button uses Web Speech API (SpeechRecognition) → routes voice commands

- Voice commands to support: "wake PC", "shutdown PC", "cancel shutdown", "is PC on", "DropX" (responds "Yes Drop, Sirr!"), "open X", "scaffold a python project at D:/X", "call me X"

- Log box shows timestamped responses

- speak() function uses SpeechSynthesis for voice replies



API ENDPOINTS (all on the PC, not on Lovable):

- GET  /status

- POST /wake

- POST /shutdown  { delay: 30 }

- POST /shutdown/cancel

- POST /scaffold  { kind, target }

- POST /qa        { path }

- POST /open      { target, window }

- POST /call      { message }

- POST /dropx



PWA:

- Make it installable (manifest + service worker)

- App name: DropX

- Theme color: #0a1229

- Standalone display mode

- Icons included



VOICE:

- En-IN language for Hinglish support

- Push-to-talk on mic button

- Route transcript through regex matcher

- Respond with speech synthesis

- "DropX" trigger → "Yes Drop, Sirr!"



SAFETY:

- All commands require the user to tap a button or speak — nothing auto-fires

- Shutdown always has 30s delay with visible cancel



Do NOT add login, signup, database, or any backend. This is a pure frontend that talks to my PC's local server via a saved URL. ┌────────────────────────────────────────────────────────────┐

│  LOVABLE builds this  →  the mobile web app (HTML/JS/CSS)  │

└──────────────────────┬─────────────────────────────────────┘

                       │

                       │  you export it and host it (or use

                       │  Lovable's URL on your phone)

                       │

                       ▼

┌────────────────────────────────────────────────────────────┐

│  📱 Phone opens the DropX web app                          │

│                                                            │

│  First time: a popup asks "Enter PC API URL"               │

│  You type:  http://100.x.x.x:8765                          │

│  Saved to localStorage → used forever                      │

└──────────────────────┬─────────────────────────────────────┘

                       │

                       │  App sends fetch() requests to that URL

                       │

                       ▼

┌────────────────────────────────────────────────────────────┐

│  🌐 Tailscale private tunnel (already set up on both)      │

│                                                            │

│  Phone (100.5.5.5) ──── encrypted ────▶ PC (100.x.x.x)     │

└──────────────────────┬─────────────────────────────────────┘

                       │

                       ▼

┌────────────────────────────────────────────────────────────┐

│  💻 Your PC running DropX FastAPI server on port 8765      │

│                                                            │

│  Receives:  POST /wake                                     │

│  Runs:      network/wol.py → sends magic packet            │

│  Returns:   { "ok": true }                                 │

└──────────────────────┬─────────────────────────────────────┘

                       │

                       ▼

┌────────────────────────────────────────────────────────────┐

│  📱 Phone shows result in log box + speaks reply           │

└────────────────────────────────────────────────────────────┘

This project was built with [Lovable](https://lovable.dev).

**Live app**: https://dropxrd.lovable.app

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/905ad7a5-816a-4a45-ac92-5ed6c79a6086).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```

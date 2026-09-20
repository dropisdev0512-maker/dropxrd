import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { GalaxyBackground } from "@/components/GalaxyBackground";
import { api, getApiBase, setApiBase, speak, stamp } from "@/lib/dropx";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "DropX — Remote control panel for your PC" },
      {
        name: "description",
        content:
          "DropX is a mobile glass-style remote for your PC: wake, shut down, scaffold projects and run voice commands over your private Tailscale network.",
      },
      { property: "og:title", content: "DropX — Remote control panel for your PC" },
      {
        property: "og:description",
        content:
          "Wake, shut down and command your PC from your phone with voice control over a private tunnel.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: DropX,
});

type LogLine = { time: string; text: string };

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="glass-card p-5">
      <header className="mb-4">
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {subtitle ? <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p> : null}
      </header>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function DropX() {
  const [apiUrl, setApiUrl] = useState<string | null>(null);
  const [askUrl, setAskUrl] = useState(false);
  const [urlDraft, setUrlDraft] = useState("http://100.");
  const [online, setOnline] = useState<boolean | null>(null);
  const [log, setLog] = useState<LogLine[]>([]);
  const [listening, setListening] = useState(false);

  const [kind, setKind] = useState("python-cli");
  const [scaffoldPath, setScaffoldPath] = useState("");
  const [qaPath, setQaPath] = useState("");
  const [appPath, setAppPath] = useState("");
  const [windowTitle, setWindowTitle] = useState("");
  const [callMessage, setCallMessage] = useState("");

  const logRef = useRef<HTMLDivElement | null>(null);
  const recRef = useRef<any>(null);

  const addLog = useCallback((text: string) => {
    setLog((prev) => [...prev.slice(-80), { time: stamp(), text }]);
  }, []);

  useEffect(() => {
    const saved = getApiBase();
    if (saved) setApiUrl(saved);
    else setAskUrl(true);
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  // Poll /status every 5s
  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;
    const tick = async () => {
      const res = await api.status();
      if (!cancelled) setOnline(res.ok);
    };
    tick();
    const id = window.setInterval(tick, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [apiUrl]);

  const run = useCallback(
    async (label: string, fn: () => Promise<{ ok: boolean; data?: unknown; error?: string }>) => {
      addLog(`→ ${label}`);
      const res = await fn();
      if (res.ok) {
        addLog(`✓ ${label}: ${typeof res.data === "string" ? res.data : JSON.stringify(res.data)}`);
      } else {
        addLog(`✗ ${label}: ${res.error ?? "failed"}`);
      }
      return res;
    },
    [addLog],
  );

  const saveUrl = () => {
    const clean = urlDraft.trim();
    if (!clean) return;
    setApiBase(clean);
    setApiUrl(clean.replace(/\/+$/, ""));
    setAskUrl(false);
    addLog(`PC API URL saved: ${clean}`);
  };

  // ---- voice command routing -------------------------------------------
  const handleTranscript = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      addLog(`🎤 "${text}"`);
      const t = text.toLowerCase();

      if (/\bdrop\s?x\b/.test(t) && !/(wake|shut|cancel|open|scaffold|call)/.test(t)) {
        speak("Yes Drop, Sirr!");
        addLog("DropX: Yes Drop, Sirr!");
        run("dropx", () => api.dropx());
        return;
      }
      if (/cancel\s+(the\s+)?shut\s?down/.test(t)) {
        speak("Shutdown cancelled.");
        run("cancel shutdown", () => api.cancelShutdown());
        return;
      }
      if (/(shut\s?down|switch off|band kar)/.test(t)) {
        speak("Shutting down in 30 seconds. Tap cancel to stop.");
        run("shutdown (30s)", () => api.shutdown(30));
        return;
      }
      if (/(wake|turn on|start|chalu)\b.*(pc|computer|system)|^wake/.test(t)) {
        speak("Waking your PC.");
        run("wake PC", () => api.wake());
        return;
      }
      if (/is\s+(the\s+)?pc\s+(on|online|up)/.test(t)) {
        const res = await run("status check", () => api.status());
        speak(res.ok ? "Yes Drop, your PC is online." : "Your PC looks offline.");
        return;
      }
      const scaffold = t.match(
        /scaffold\s+(?:a|an)?\s*(python|fabric|mod|web)?[a-z\s]*?(?:project)?\s*(?:at|in|on)\s+(.+)$/,
      );
      if (scaffold) {
        const k = scaffold[1]?.includes("fabric")
          ? "fabric-mod"
          : scaffold[1]?.includes("web")
            ? "web"
            : "python-cli";
        const target = (scaffold[2] ?? "").trim();
        speak(`Scaffolding ${k} at ${target}`);
        run(`scaffold ${k} → ${target}`, () => api.scaffold(k, target));
        return;
      }
      const call = t.match(/call\s+me\s+(.+)$/);
      if (call) {
        const message = (call[1] ?? "").trim();
        speak("Calling you now.");
        run(`call: ${message}`, () => api.call(message));
        return;
      }
      const open = t.match(/open\s+(.+)$/);
      if (open) {
        const target = (open[1] ?? "").trim();
        speak(`Opening ${target}`);
        run(`open ${target}`, () => api.open(target, target));
        return;
      }
      speak("Sorry Drop, I did not catch that command.");
      addLog("No matching command.");
    },
    [addLog, run],
  );

  const startListening = () => {
    const SR =
      (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition ?? null;
    if (!SR) {
      addLog("✗ Voice input is not supported in this browser.");
      speak("Voice input is not supported here.");
      return;
    }
    const rec = new SR();
    rec.lang = "en-IN";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.continuous = false;
    rec.onresult = (e: any) => handleTranscript(e.results[0][0].transcript as string);
    rec.onerror = (e: any) => addLog(`✗ mic error: ${e.error ?? "unknown"}`);
    rec.onend = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    addLog("Listening…");
    rec.start();
  };

  const stopListening = () => {
    try {
      recRef.current?.stop();
    } catch {
      /* ignore */
    }
    setListening(false);
  };

  return (
    <div className="min-h-screen">
      <GalaxyBackground />

      <header className="glass-bar sticky top-0 z-20">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <img src="/icon-192.png" alt="" width={32} height={32} className="h-8 w-8 rounded-xl" />
          <span className="text-lg font-semibold tracking-tight">DropX</span>
          <span
            className="ml-auto inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium"
            style={{
              background: "var(--color-glass)",
              color: online ? "var(--color-online)" : "var(--color-destructive)",
            }}
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{
                background: online ? "var(--color-online)" : "var(--color-destructive)",
                boxShadow: "0 0 10px currentColor",
              }}
            />
            {online === null ? "Checking…" : online ? "PC online" : "PC offline"}
          </span>
          <button
            aria-label="Change PC API URL"
            onClick={() => {
              setUrlDraft(apiUrl ?? "http://100.");
              setAskUrl(true);
            }}
            className="grid h-9 w-9 place-items-center rounded-full border text-base"
            style={{ background: "var(--color-glass)" }}
          >
            ⚙︎
          </button>
        </div>
      </header>

      <main className="mx-auto grid max-w-3xl gap-4 px-4 py-5 sm:grid-cols-2">
        <Card title="Power" subtitle="Shutdown always waits 30 seconds so you can cancel.">
          <button className="btn-base btn-primary" onClick={() => run("wake PC", () => api.wake())}>
            ⏻ Wake PC
          </button>
          <button
            className="btn-base btn-danger"
            onClick={() => run("shutdown (30s)", () => api.shutdown(30))}
          >
            Shutdown in 30s
          </button>
          <button
            className="btn-base btn-ghost"
            onClick={() => run("cancel shutdown", () => api.cancelShutdown())}
          >
            Cancel Shutdown
          </button>
        </Card>

        <Card title="DevOps" subtitle="Scaffold a project or run QA checks.">
          <select className="glass-field" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="python-cli">Python CLI</option>
            <option value="fabric-mod">Fabric Mod</option>
            <option value="web">Web</option>
          </select>
          <input
            className="glass-field"
            placeholder="Target path e.g. D:/Projects/demo"
            value={scaffoldPath}
            onChange={(e) => setScaffoldPath(e.target.value)}
          />
          <button
            className="btn-base btn-primary"
            disabled={!scaffoldPath.trim()}
            onClick={() => run(`scaffold ${kind}`, () => api.scaffold(kind, scaffoldPath.trim()))}
          >
            Scaffold
          </button>
          <input
            className="glass-field"
            placeholder="QA path e.g. D:/Projects/demo"
            value={qaPath}
            onChange={(e) => setQaPath(e.target.value)}
          />
          <button
            className="btn-base btn-ghost"
            disabled={!qaPath.trim()}
            onClick={() => run("run QA", () => api.qa(qaPath.trim()))}
          >
            Run QA
          </button>
        </Card>

        <Card title="Assist" subtitle="Open an app or ping yourself.">
          <input
            className="glass-field"
            placeholder="App path or name e.g. code"
            value={appPath}
            onChange={(e) => setAppPath(e.target.value)}
          />
          <input
            className="glass-field"
            placeholder="Window title (optional)"
            value={windowTitle}
            onChange={(e) => setWindowTitle(e.target.value)}
          />
          <button
            className="btn-base btn-primary"
            disabled={!appPath.trim()}
            onClick={() => run("open", () => api.open(appPath.trim(), windowTitle.trim()))}
          >
            Open
          </button>
          <input
            className="glass-field"
            placeholder="Message to call me with"
            value={callMessage}
            onChange={(e) => setCallMessage(e.target.value)}
          />
          <button
            className="btn-base btn-ghost"
            disabled={!callMessage.trim()}
            onClick={() => run("call me", () => api.call(callMessage.trim()))}
          >
            Call Me
          </button>
        </Card>

        <Card title="DropX Voice" subtitle="Hold the mic, speak your command, release.">
          <button
            className={`btn-base btn-primary py-5 text-lg ${listening ? "mic-pulse" : ""}`}
            onPointerDown={startListening}
            onPointerUp={stopListening}
            onPointerLeave={stopListening}
          >
            🎤 {listening ? "Listening…" : "Speak"}
          </button>
          <button
            className="btn-base btn-ghost py-5 text-lg"
            onClick={() => {
              speak("Yes Drop, Sirr!");
              addLog("DropX: Yes Drop, Sirr!");
              run("dropx", () => api.dropx());
            }}
          >
            Say DropX
          </button>
          <div
            ref={logRef}
            className="mt-1 h-48 overflow-y-auto rounded-md border p-3 font-mono text-[11px] leading-relaxed"
            style={{ background: "oklch(0.14 0.05 265 / 0.6)" }}
          >
            {log.length === 0 ? (
              <p className="text-muted-foreground">Log is empty. Tap a button to begin.</p>
            ) : (
              log.map((line, i) => (
                <p key={i}>
                  <span className="text-muted-foreground">[{line.time}]</span> {line.text}
                </p>
              ))
            )}
          </div>
        </Card>
        <div className="sm:col-span-2">
          <Card title="Connect your PC" subtitle="One-time setup, about 5 minutes.">
            <ol className="space-y-2 text-sm text-muted-foreground">
              <li>
                <span className="font-medium text-foreground">1.</span> Install{" "}
                <a
                  href="https://tailscale.com/download"
                  target="_blank"
                  rel="noreferrer"
                  className="underline decoration-dotted"
                >
                  Tailscale
                </a>{" "}
                (free) on your PC and phone — sign in with the same account.
              </li>
              <li>
                <span className="font-medium text-foreground">2.</span> Download the agent below and run{" "}
                <code className="rounded bg-background/60 px-1.5 py-0.5 font-mono text-xs">python agent.py</code>{" "}
                on your PC (get Python at python.org, tick “Add to PATH”).
              </li>
              <li>
                <span className="font-medium text-foreground">3.</span> On the PC run{" "}
                <code className="rounded bg-background/60 px-1.5 py-0.5 font-mono text-xs">tailscale serve --bg 8765</code>{" "}
                and copy the <span className="font-mono text-xs">https://…ts.net</span> address it prints.
              </li>
              <li>
                <span className="font-medium text-foreground">4.</span> Tap ⚙︎ at the top, paste that address and save —
                the dot in the header should turn green.
              </li>
            </ol>
            <a
              className="btn-base btn-primary inline-flex w-fit items-center gap-2"
              href="/agent.py"
              download="agent.py"
            >
              ⬇ Download agent.py
            </a>
          </Card>
        </div>
      </main>

      <p className="mx-auto max-w-3xl px-4 pb-8 text-center text-[11px] text-muted-foreground">
        Nothing runs on its own — every command needs a tap or your voice.
      </p>

      {askUrl ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center px-5"
          style={{ background: "oklch(0.09 0.04 265 / 0.72)", backdropFilter: "blur(8px)" }}
        >
          <div className="glass-card w-full max-w-sm p-6">
            <h2 className="text-lg font-semibold">PC API URL</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Enter your PC's address, e.g. http://100.101.102.103:8765
            </p>
            <input
              className="glass-field mt-4"
              value={urlDraft}
              autoFocus
              onChange={(e) => setUrlDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveUrl()}
            />
            <div className="mt-4 flex gap-2">
              <button className="btn-base btn-primary" onClick={saveUrl}>
                Save
              </button>
              {apiUrl ? (
                <button className="btn-base btn-ghost" onClick={() => setAskUrl(false)}>
                  Cancel
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

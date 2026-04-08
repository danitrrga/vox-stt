import { useState, useEffect, useMemo } from "react";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Settings from "./components/Settings";
import { STT_SERVER, MONO_FONT } from "./constants";

type AppState = "idle" | "recording" | "processing" | "hands-free" | "downloading";
type View = "main" | "settings";

interface DownloadStatus {
  downloading: boolean;
  progress: number;
  model: string;
  error: string | null;
  done: boolean;
  downloaded_bytes: number;
  total_bytes: number;
}

interface TranscriptionResult {
  raw: string;
  formatted: string;
  language: string;
  language_probability: number;
  used_ollama: boolean;
  duration_seconds: number;
}


function BrandedWaveform({ color, gradientFrom }: { color: string; gradientFrom: string }) {
  const bars = 11;
  const mid = Math.floor(bars / 2);
  return (
    <div className="flex items-center gap-[2px]" style={{ height: "40px" }}>
      {Array.from({ length: bars }).map((_, i) => {
        const distFromMid = Math.abs(i - mid) / mid;
        const maxH = 36 - distFromMid * 16;
        return (
          <div
            key={i}
            className="rounded-full"
            style={{
              width: "2px",
              height: `${maxH * 0.3}px`,
              background: `linear-gradient(to top, ${gradientFrom}, ${color})`,
              animation: `waveform ${0.35 + i * 0.06}s ease-in-out infinite`,
              animationDelay: `${i * 0.05}s`,
            }}
          />
        );
      })}
    </div>
  );
}

function BrailleSpinner({ color }: { color: string }) {
  const frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏";
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => (f + 1) % frames.length), 80);
    return () => clearInterval(id);
  }, []);
  return (
    <span
      style={{
        fontFamily: MONO_FONT,
        fontSize: "24px",
        color,
        display: "inline-block",
        width: "1.2em",
        textAlign: "center",
      }}
    >
      {frames[frame]}
    </span>
  );
}


function GearIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M19 12H5" />
      <path d="M12 19l-7-7 7-7" />
    </svg>
  );
}

function MinimizeIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 6h8" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 2l8 8M10 2l-8 8" />
    </svg>
  );
}

const VOX_ASCII = `██╗   ██╗ ██████╗ ██╗  ██╗
██║   ██║██╔═══██╗╚██╗██╔╝
██║   ██║██║   ██║ ╚███╔╝
╚██╗ ██╔╝██║   ██║ ██╔██╗
 ╚████╔╝ ╚██████╔╝██╔╝ ██╗
  ╚═══╝   ╚═════╝ ╚═╝  ╚═╝`;

const VOX_ASCII_STYLE: React.CSSProperties = {
  fontFamily: MONO_FONT,
  fontSize: "5.5px",
  lineHeight: "1.15",
  letterSpacing: "0.5px",
  margin: 0,
};

function stateColor(state: AppState): string {
  switch (state) {
    case "recording": return "var(--color-text-primary)";
    case "hands-free": return "var(--color-success)";
    case "processing": return "var(--color-accent)";
    default: return "var(--color-success)";
  }
}

function stateLabel(state: AppState): string {
  switch (state) {
    case "recording": return "● REC";
    case "hands-free": return "● HANDS-FREE";
    case "processing": return "··· PROC";
    default: return "READY";
  }
}

function generateAsciiPattern(rows: number, cols: number): string {
  const dense = ["█", "▓", "▒", "░", "∿", "─"];
  const mid = ["·", "∿", "·", "─", "·", " "];
  const sparse = [" ", " ", " ", "·", " ", " ", " ", " "];
  const centerR = rows / 2;
  const centerC = cols / 2;
  const maxDist = Math.sqrt(centerR * centerR + centerC * centerC);

  // Simple seeded random for determinism
  let seed = 42;
  const rand = () => {
    seed = (seed * 16807 + 0) % 2147483647;
    return (seed - 1) / 2147483646;
  };

  const lines: string[] = [];
  for (let r = 0; r < rows; r++) {
    let line = "";
    for (let c = 0; c < cols; c++) {
      const dist = Math.sqrt((r - centerR) ** 2 + (c - centerC) ** 2);
      const norm = dist / maxDist;
      // Wave rings — characters cluster at certain radii
      const wave = Math.sin(dist * 0.8) * 0.5 + 0.5;
      const rnd = rand();

      if (norm < 0.25 && wave > 0.6 && rnd > 0.4) {
        line += dense[Math.floor(rnd * dense.length)];
      } else if (norm < 0.55 && wave > 0.5 && rnd > 0.5) {
        line += mid[Math.floor(rnd * mid.length)];
      } else if (rnd > 0.85) {
        line += sparse[Math.floor(rnd * sparse.length)];
      } else {
        line += " ";
      }
    }
    lines.push(line);
  }
  return lines.join("\n");
}

function AsciiBackground() {
  const pattern = useMemo(() => generateAsciiPattern(40, 50), []);
  return (
    <pre
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 0,
        opacity: 0.04,
        color: "var(--color-text-muted)",
        fontSize: "10px",
        lineHeight: "14px",
        overflow: "hidden",
        pointerEvents: "none",
        fontFamily: MONO_FONT,
        margin: 0,
        padding: "8px",
      }}
    >
      {pattern}
    </pre>
  );
}

const ACTIVE_MODES = {
  recording: {
    color: "var(--color-text-primary)",
    bgTint: "rgba(250, 250, 250, 0.03)",
    waveColor: "rgba(250, 250, 250, 0.9)",
    waveFrom: "rgba(250, 250, 250, 0.2)",
    label: "listening",
    glow: true,
  },
  "hands-free": {
    color: "var(--color-success)",
    bgTint: "rgba(34, 197, 94, 0.04)",
    waveColor: "#86efac",
    waveFrom: "rgba(34, 197, 94, 0.3)",
    label: "hands-free",
    glow: false,
  },
} as const;

function ActiveRecordingView({ mode, partialText }: { mode: "recording" | "hands-free"; partialText: string }) {
  const cfg = ACTIVE_MODES[mode];
  return (
    <div
      key={mode}
      className="flex flex-col items-center gap-4"
      style={{ animation: "fade-in 0.25s ease" }}
    >
      <pre
        style={{
          ...VOX_ASCII_STYLE,
          color: cfg.color,
          borderRadius: "10px",
          padding: "10px 14px",
          background: cfg.bgTint,
          ...(cfg.glow ? { animation: "glow-recording 1.5s ease-in-out infinite" } : {}),
        }}
      >
        {VOX_ASCII}
      </pre>
      <BrandedWaveform color={cfg.waveColor} gradientFrom={cfg.waveFrom} />
      <span
        style={{
          fontFamily: MONO_FONT,
          fontSize: "10px",
          letterSpacing: "0.14em",
          color: cfg.color,
          textTransform: "uppercase",
        }}
      >
        ─── {cfg.label} ───
      </span>
      {partialText && (
        <p
          className="text-xs leading-relaxed text-center max-h-16 overflow-y-auto px-2"
          style={{
            color: "var(--color-text-muted)",
            fontFamily: MONO_FONT,
            fontSize: "11px",
            animation: "fade-in 0.2s ease",
          }}
        >
          {partialText}
        </p>
      )}
    </div>
  );
}

async function handleClose() {
  try {
    const resp = await fetch(`${STT_SERVER}/api/config`);
    const config = await resp.json();
    if (config.close_to_tray) {
      getCurrentWindow().hide();
    } else {
      getCurrentWindow().close();
    }
  } catch {
    getCurrentWindow().close();
  }
}

/** Format a hotkey string for display: "Super" → "⊞ Win", parts spaced with " + " */
export function formatHotkeyDisplay(hotkey: string): React.ReactNode {
  const parts = hotkey.split("+").map((p) => {
    const t = p.trim();
    if (t === "Super" || t === "Win" || t === "Meta") return "\u229E Win";
    if (t === "Dead" || t === "`") return "`";
    if (t === "\\") return "\\";
    return t;
  });
  return parts.map((part, i) => (
    <span key={i}>
      {i > 0 && <span style={{ color: "var(--color-text-muted)", margin: "0 2px" }}>+</span>}
      <kbd
        className="px-1.5 py-0.5 rounded text-xs font-mono"
        style={{
          background: "var(--color-surface-raised)",
          border: "1px solid var(--color-border)",
          color: "var(--color-text-primary)",
        }}
      >
        {part}
      </kbd>
    </span>
  ));
}

function App() {
  const [state, setState] = useState<AppState>("idle");
  const [partialText, setPartialText] = useState("");
  const [lastResult, setLastResult] = useState<TranscriptionResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("main");
  const [hotkey, setHotkey] = useState("Ctrl+Shift+Space");
  const [model, setModel] = useState("base");
  const [ollamaOn, setOllamaOn] = useState(true);
  const [langMode, setLangMode] = useState("auto");
  const [downloadStatus, setDownloadStatus] = useState<DownloadStatus | null>(null);

  const copyResultText = (andClear: boolean) => {
    if (!lastResult) return;
    const text = lastResult.formatted || lastResult.raw;
    navigator.clipboard.writeText(text).then(() => {
      if (andClear) {
        setLastResult(null);
      } else {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }
    });
  };

  // Fetch config
  const fetchConfig = () => {
    fetch(`${STT_SERVER}/api/config`)
      .then((r) => r.json())
      .then((c) => {
        if (c.hotkey) setHotkey(c.hotkey);
        if (c.whisper_model) setModel(c.whisper_model);
        if (c.ollama_enabled !== undefined) setOllamaOn(c.ollama_enabled);
        if (c.language_mode) setLangMode(c.language_mode);
      })
      .catch(() => {});
  };

  useEffect(fetchConfig, []);

  // Poll model download status — fast when downloading, slow otherwise to detect new downloads
  useEffect(() => {
    const interval = state === "downloading" ? 800 : 5000;
    const poll = setInterval(() => {
      fetch(`${STT_SERVER}/api/model/status`)
        .then((r) => r.json())
        .then((s: DownloadStatus) => {
          if (s.downloading) {
            setDownloadStatus(s);
            if (state !== "downloading") setState("downloading");
          } else if (state === "downloading") {
            // Done, error, or server restarted — exit downloading state
            setDownloadStatus(null);
            setState("idle");
            fetchConfig();
          }
        })
        .catch(() => {});
    }, interval);
    return () => clearInterval(poll);
  }, [state]);

  // Re-fetch when returning from settings
  useEffect(() => {
    if (view === "main") fetchConfig();
  }, [view]);

  useEffect(() => {
    const unlisten1 = listen<string>("vox-state", (event) => {
      setState(event.payload as AppState);
      if (event.payload === "recording" || event.payload === "hands-free") {
        setView("main");
        setPartialText("");
        setError(null);
      }
    });

    const unlisten2 = listen<TranscriptionResult>("vox-result", (event) => {
      setLastResult(event.payload);
      setPartialText("");
      setError(null);
    });

    const unlisten3 = listen<{ text: string }>("vox-partial", (event) => {
      if (event.payload.text) setPartialText(event.payload.text);
    });

    const unlisten4 = listen<string>("vox-error", (event) => {
      setError(event.payload);
      setTimeout(() => setError(null), 4000);
    });

    return () => {
      unlisten1.then((f) => f()).catch(() => {});
      unlisten2.then((f) => f()).catch(() => {});
      unlisten3.then((f) => f()).catch(() => {});
      unlisten4.then((f) => f()).catch(() => {});
    };
  }, []);

  return (
    <div
      className="h-screen flex flex-col overflow-hidden"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "12px",
        position: "relative",
      }}
    >
      <AsciiBackground />
      {/* Title bar */}
      <div
        className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid var(--color-border)", position: "relative", zIndex: 1 }}
        data-tauri-drag-region
      >
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: stateColor(state),
              animation:
                state === "recording" || state === "hands-free"
                  ? "pulse-recording 1.5s ease-in-out infinite"
                  : "none",
            }}
          />
          <span
            style={{
              fontFamily: MONO_FONT,
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "0.12em",
              color: "var(--color-text-muted)",
              textTransform: "uppercase",
            }}
          >
            {view === "settings" ? "Settings" : "VOX"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {view === "main" && (
            <span
              style={{
                fontFamily: MONO_FONT,
                fontSize: "9px",
                letterSpacing: "0.1em",
                color: stateColor(state),
                textTransform: "uppercase",
              }}
            >
              {stateLabel(state)}
            </span>
          )}
          <button onClick={() => setView(view === "main" ? "settings" : "main")} className="titlebar-btn">
            {view === "main" ? <GearIcon /> : <BackIcon />}
          </button>
          <button onClick={() => getCurrentWindow().minimize()} className="titlebar-btn">
            <MinimizeIcon />
          </button>
          <button
            onClick={handleClose}
            className="titlebar-btn"
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--color-recording)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--color-text-muted)")}
          >
            <CloseIcon />
          </button>
        </div>
      </div>

      {/* Content */}
      {view === "settings" ? (
        <Settings />
      ) : (
        <>
          {/* Main content */}
          <div className="flex-1 flex flex-col items-center justify-center px-6 gap-4" style={{ position: "relative", zIndex: 1 }}>
            {state === "idle" && error && !lastResult && (
              <div
                key="error"
                className="w-full rounded-lg overflow-hidden"
                style={{
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  borderLeft: "2px solid var(--color-recording)",
                  animation: "fade-in 0.2s ease",
                }}
              >
                <div
                  className="text-center py-1.5"
                  style={{
                    fontFamily: MONO_FONT,
                    fontSize: "9px",
                    letterSpacing: "0.14em",
                    color: "var(--color-recording)",
                    textTransform: "uppercase",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  ─── error ───
                </div>
                <div className="p-3">
                  <p
                    className="text-xs leading-relaxed"
                    style={{ color: "var(--color-text-secondary)", fontFamily: MONO_FONT, fontSize: "10px" }}
                  >
                    {error}
                  </p>
                </div>
              </div>
            )}

            {state === "idle" && !lastResult && !error && (
              <div
                key="idle-empty"
                className="text-center flex flex-col items-center"
                style={{ animation: "fade-in 0.25s ease" }}
              >
                <pre style={{ ...VOX_ASCII_STYLE, color: "var(--color-text-secondary)" }}>
                  {VOX_ASCII}
                </pre>
                <p
                  className="text-xs mt-4"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  Local speech-to-text that types for you.
                </p>
                <p
                  className="text-sm mt-3"
                  style={{ color: "var(--color-text-secondary)" }}
                >
                  Hold {formatHotkeyDisplay(hotkey)} to talk
                </p>
              </div>
            )}

            {(state === "recording" || state === "hands-free") && (
              <ActiveRecordingView mode={state} partialText={partialText} />
            )}

            {state === "downloading" && downloadStatus && (
              <div
                key="downloading"
                className="flex flex-col items-center gap-3"
                style={{ animation: "fade-in 0.25s ease" }}
              >
                <pre
                  style={{
                    fontFamily: MONO_FONT,
                    fontSize: "10px",
                    color: "var(--color-accent-hover)",
                    letterSpacing: "0.05em",
                    textAlign: "center",
                    lineHeight: "1.4",
                    margin: 0,
                  }}
                >
{(() => {
  const W = 32;
  const fmtBytes = (b: number) => {
    if (b >= 1e9) return (b / 1e9).toFixed(1) + " GB";
    if (b >= 1e6) return (b / 1e6).toFixed(0) + " MB";
    return (b / 1e3).toFixed(0) + " KB";
  };
  const line1 = `  Downloading ${downloadStatus.model} model`.padEnd(W);
  const bw = 20;
  const filled = Math.round(downloadStatus.progress * bw);
  const bar = "\u2588".repeat(filled) + "\u2591".repeat(bw - filled);
  const pct = Math.round(downloadStatus.progress * 100).toString().padStart(3);
  const line2 = `  ${bar} ${pct}%`.padEnd(W);
  const dl = downloadStatus.downloaded_bytes || 0;
  const tot = downloadStatus.total_bytes || 0;
  const sizeStr = tot > 0 ? `  ${fmtBytes(dl)} / ${fmtBytes(tot)}` : "";
  const line3 = sizeStr.padEnd(W);
  const top = `\u2554${"═".repeat(W)}\u2557`;
  const bot = `\u255A${"═".repeat(W)}\u255D`;
  const r = (s: string) => `\u2551${s}\u2551`;
  return tot > 0
    ? `${top}\n${r(line1)}\n${r(line2)}\n${r(line3)}\n${bot}`
    : `${top}\n${r(line1)}\n${r(line2)}\n${bot}`;
})()}
                </pre>
                {downloadStatus.error && (
                  <span style={{ color: "var(--color-danger)", fontSize: "10px", fontFamily: MONO_FONT }}>
                    Error: {downloadStatus.error}
                  </span>
                )}
              </div>
            )}

            {state === "processing" && (
              <div
                key="processing"
                className="flex flex-col items-center gap-4"
                style={{ animation: "fade-in 0.25s ease" }}
              >
                {/* Braille spinner */}
                <BrailleSpinner color="var(--color-accent)" />

                {/* Subtle processing bars */}
                <div className="flex items-center gap-[2px]" style={{ height: "16px" }}>
                  {Array.from({ length: 9 }).map((_, i) => (
                    <div
                      key={i}
                      className="rounded-full"
                      style={{
                        width: "2px",
                        height: "3px",
                        background: "linear-gradient(to top, rgba(99,102,241,0.3), #a5b4fc)",
                        animation: `waveform 0.6s ease-in-out infinite`,
                        animationDelay: `${i * 0.06}s`,
                      }}
                    />
                  ))}
                </div>

                {/* Monospace label */}
                <span
                  style={{
                    fontFamily: MONO_FONT,
                    fontSize: "10px",
                    letterSpacing: "0.14em",
                    color: "var(--color-accent-hover)",
                    textTransform: "uppercase",
                  }}
                >
                  ─── transcribing ───
                </span>
              </div>
            )}

            {state === "idle" && lastResult && (
              <div
                key="result"
                className="w-full rounded-lg overflow-hidden"
                style={{
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  borderLeft: copied ? "2px solid var(--color-accent)" : "2px solid var(--color-success)",
                  animation: "fade-in 0.2s ease",
                  transition: "border-color 0.2s ease",
                }}
              >
                {/* Branded header */}
                <div
                  className="text-center py-1.5"
                  style={{
                    fontFamily: MONO_FONT,
                    fontSize: "9px",
                    letterSpacing: "0.14em",
                    color: "var(--color-text-muted)",
                    textTransform: "uppercase",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  ─── result ───
                </div>

                {/* Transcribed text — click to copy */}
                <div
                  className="p-3 max-h-24 overflow-y-auto cursor-pointer transition-colors hover:bg-white/[0.06]"
                  onClick={() => copyResultText(false)}
                  title="Click to copy"
                >
                  <p
                    className="text-sm leading-relaxed"
                    style={{ color: "var(--color-text-primary)" }}
                  >
                    {lastResult.formatted || lastResult.raw}
                  </p>
                </div>

                {/* Branded metadata */}
                <div
                  className="flex items-center justify-between px-3 py-1.5"
                  style={{
                    borderTop: "1px solid var(--color-border)",
                    fontFamily: MONO_FONT,
                    fontSize: "9px",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                  }}
                >
                  <span style={{ color: "var(--color-text-muted)" }}>
                    {(lastResult.language || "??").toUpperCase()}
                    {" · "}
                    {lastResult.duration_seconds.toFixed(1)}s
                  </span>
                  <div className="flex items-center gap-3">
                    <span style={{ color: copied ? "var(--color-accent)" : "var(--color-success)" }}>
                      {copied ? "copied" : "injected"}
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); copyResultText(true); }}
                      className="transition-all hover:opacity-90"
                      style={{
                        color: "var(--color-text-muted)",
                        background: "var(--color-surface)",
                        border: "1px solid var(--color-border)",
                        borderRadius: "4px",
                        padding: "1px 6px",
                        fontSize: "8px",
                        fontFamily: MONO_FONT,
                        letterSpacing: "0.1em",
                        cursor: "pointer",
                      }}
                      title="Copy and dismiss"
                    >
                      CUT
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Bottom bar */}
          <div
            className="flex items-center justify-between px-4 py-2 shrink-0"
            style={{
              borderTop: "1px solid var(--color-border)",
              background: "var(--color-surface-raised)",
              position: "relative",
              zIndex: 1,
              fontFamily: MONO_FONT,
              fontSize: "9px",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            <div className="flex items-center gap-2">
              <div
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: "var(--color-success)" }}
              />
              <span style={{ color: "var(--color-text-muted)" }}>
                whisper:{model}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span style={{ color: "var(--color-text-muted)" }}>
                ollama: {ollamaOn ? "on" : "off"}
              </span>
              <span style={{ color: "var(--color-text-muted)" }}>
                {langMode === "auto" ? "auto" : "manual"}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default App;

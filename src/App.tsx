import { useState, useEffect } from "react";
import { listen } from "@tauri-apps/api/event";

type AppState = "idle" | "recording" | "processing";

interface TranscriptionResult {
  raw: string;
  formatted: string;
  language: string;
  language_probability: number;
  used_ollama: boolean;
  duration_seconds: number;
}

function MicIcon({ state }: { state: AppState }) {
  const color =
    state === "recording"
      ? "var(--color-recording)"
      : state === "processing"
        ? "var(--color-accent)"
        : "var(--color-text-secondary)";

  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </svg>
  );
}

function WaveformBars({ active }: { active: boolean }) {
  const bars = 5;
  return (
    <div className="flex items-center gap-[3px] h-6">
      {Array.from({ length: bars }).map((_, i) => (
        <div
          key={i}
          className="w-[3px] rounded-full transition-all duration-150"
          style={{
            height: active ? `${12 + Math.sin(i * 1.2) * 8}px` : "4px",
            backgroundColor: active
              ? "var(--color-recording)"
              : "var(--color-border)",
            animation: active
              ? `waveform ${0.4 + i * 0.1}s ease-in-out infinite`
              : "none",
            animationDelay: `${i * 0.08}s`,
          }}
        />
      ))}
    </div>
  );
}

function App() {
  const [state, setState] = useState<AppState>("idle");
  const [lastResult, setLastResult] = useState<TranscriptionResult | null>(null);

  useEffect(() => {
    const unlisten1 = listen<string>("vox-state", (event) => {
      setState(event.payload as AppState);
    });

    const unlisten2 = listen<TranscriptionResult>("vox-result", (event) => {
      setLastResult(event.payload);
    });

    return () => {
      unlisten1.then((f) => f());
      unlisten2.then((f) => f());
    };
  }, []);

  return (
    <div
      className="h-screen flex flex-col overflow-hidden"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "12px",
      }}
    >
      {/* Title bar */}
      <div
        className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: "1px solid var(--color-border)" }}
        data-tauri-drag-region
      >
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor:
                state === "recording"
                  ? "var(--color-recording)"
                  : state === "processing"
                    ? "var(--color-accent)"
                    : "var(--color-success)",
              animation:
                state === "recording"
                  ? "pulse-recording 1.5s ease-in-out infinite"
                  : "none",
            }}
          />
          <span
            className="text-xs font-medium tracking-wide uppercase"
            style={{ color: "var(--color-text-muted)" }}
          >
            Vox
          </span>
        </div>
        <div className="text-xs" style={{ color: "var(--color-text-muted)" }}>
          {state === "idle"
            ? "Ready"
            : state === "recording"
              ? "Listening..."
              : "Processing..."}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 gap-4">
        {state === "idle" && !lastResult && (
          <div className="text-center">
            <MicIcon state={state} />
            <p className="text-sm mt-3" style={{ color: "var(--color-text-secondary)" }}>
              Hold{" "}
              <kbd
                className="px-1.5 py-0.5 rounded text-xs font-mono"
                style={{
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  color: "var(--color-text-primary)",
                }}
              >
                Ctrl+Shift+Space
              </kbd>{" "}
              to talk
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--color-text-muted)" }}>
              Double-tap to toggle dictation mode
            </p>
          </div>
        )}

        {state === "recording" && (
          <div className="flex flex-col items-center gap-3">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center"
              style={{
                background: "rgba(239, 68, 68, 0.1)",
                border: "2px solid var(--color-recording)",
                animation: "pulse-recording 1.5s ease-in-out infinite",
              }}
            >
              <MicIcon state={state} />
            </div>
            <WaveformBars active={true} />
            <p className="text-sm" style={{ color: "var(--color-recording)" }}>
              Listening...
            </p>
          </div>
        )}

        {state === "processing" && (
          <div className="flex flex-col items-center gap-3">
            <div
              className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin"
              style={{
                borderColor: "var(--color-accent)",
                borderTopColor: "transparent",
              }}
            />
            <p className="text-sm" style={{ color: "var(--color-accent)" }}>
              Transcribing...
            </p>
          </div>
        )}

        {state === "idle" && lastResult && (
          <div
            className="w-full rounded-lg p-3 max-h-32 overflow-y-auto"
            style={{
              background: "var(--color-surface-raised)",
              border: "1px solid var(--color-border)",
            }}
          >
            <p className="text-sm leading-relaxed" style={{ color: "var(--color-text-primary)" }}>
              {lastResult.formatted || lastResult.raw}
            </p>
            <div className="flex items-center justify-between mt-2">
              <span
                className="text-xs uppercase tracking-wide"
                style={{ color: "var(--color-text-muted)" }}
              >
                {lastResult.language === "es"
                  ? "Español"
                  : lastResult.language === "en"
                    ? "English"
                    : lastResult.language}
                {" · "}
                {lastResult.duration_seconds.toFixed(1)}s
              </span>
              <span className="text-xs" style={{ color: "var(--color-success)" }}>
                Injected ✓
              </span>
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
        }}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: "var(--color-success)" }}
          />
          <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>
            whisper:base
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>
            {lastResult?.used_ollama ? "Ollama: ✓" : "Ollama: on"}
          </span>
          <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>
            Auto-lang
          </span>
        </div>
      </div>
    </div>
  );
}

export default App;

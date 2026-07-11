import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { Check, LoaderCircle, TerminalSquare } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { VersionView } from "../types";

export function TerminalPanel({
  projectId,
  onSaved,
  onError,
}: {
  projectId: string;
  onSaved: (version: VersionView) => void;
  onError: (message: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const [sessionId, setSessionId] = useState("");
  const [connecting, setConnecting] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!container.current || started.current) return;
    started.current = true;
    const terminal = new Terminal({
      cursorBlink: true,
      fontFamily: '"SFMono-Regular", Consolas, monospace',
      fontSize: 13,
      theme: { background: "#191724", foreground: "#f6f1ff", cursor: "#ffd45c" },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(container.current);
    fit.fit();
    let socket: WebSocket | undefined;
    let resizeObserver: ResizeObserver | undefined;

    api.openSandbox(projectId).then((session) => {
      setSessionId(session.session_id);
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}${session.websocket_path}`);
      socket.binaryType = "arraybuffer";
      socket.onopen = () => {
        setConnecting(false);
        fit.fit();
        socket?.send(JSON.stringify({ type: "resize", cols: terminal.cols, rows: terminal.rows }));
      };
      socket.onmessage = (event) => {
        const output = event.data instanceof ArrayBuffer
          ? new TextDecoder().decode(event.data)
          : String(event.data);
        terminal.write(output);
      };
      socket.onerror = () => onError("The Sandbox terminal connection failed");
      terminal.onData((data) => {
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "input", data }));
        }
      });
      resizeObserver = new ResizeObserver(() => {
        fit.fit();
        if (socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "resize", cols: terminal.cols, rows: terminal.rows }));
        }
      });
      if (container.current) resizeObserver.observe(container.current);
    }).catch((reason: Error) => {
      setConnecting(false);
      terminal.writeln(`\r\nSandbox unavailable: ${reason.message}`);
      onError(reason.message);
    });

    return () => {
      resizeObserver?.disconnect();
      socket?.close();
      terminal.dispose();
    };
  }, [onError, projectId]);

  const save = async () => {
    if (!sessionId || saving) return;
    setSaving(true);
    try {
      onSaved(await api.saveSandbox(projectId, sessionId));
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Could not save Vim changes");
    } finally {
      setSaving(false);
    }
  };

  return <div className="terminal-panel">
    <div className="terminal-heading">
      <div><TerminalSquare size={17} /><span><strong>Restricted Vim</strong><small>Project worktree · no login shell · no network</small></span></div>
      <button onClick={save} disabled={!sessionId || saving || connecting}>
        {saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} Save version
      </button>
    </div>
    <div className="terminal-mount" ref={container} />
  </div>;
}

import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { Check, LoaderCircle, Play, TerminalSquare } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { VersionView } from "../types";

export function TerminalPanel({
  projectId,
  language,
  onSaved,
  onError,
}: {
  projectId: string;
  language: "zh" | "en";
  onSaved: (version: VersionView) => void;
  onError: (message: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const terminal = useRef<Terminal | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const resizeObserver = useRef<ResizeObserver | null>(null);
  const sessionIdRef = useRef("");
  const saved = useRef(false);
  const abortOpen = useRef<AbortController | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => () => {
    abortOpen.current?.abort();
    resizeObserver.current?.disconnect();
    socket.current?.close();
    terminal.current?.dispose();
    if (sessionIdRef.current && !saved.current) {
      void api.closeSandbox(projectId, sessionIdRef.current).catch(() => undefined);
    }
  }, [projectId]);

  const open = async () => {
    if (connecting || sessionId || !container.current) return;
    setConnecting(true);
    onError("");
    const controller = new AbortController();
    abortOpen.current = controller;
    try {
      const session = await api.openSandbox(projectId, controller.signal);
      sessionIdRef.current = session.session_id;
      setSessionId(session.session_id);
      abortOpen.current = null;
      if (!container.current) {
        await api.closeSandbox(projectId, session.session_id);
        return;
      }

      const nextTerminal = new Terminal({
        cursorBlink: true,
        fontFamily: '"SFMono-Regular", Consolas, monospace',
        fontSize: 13,
        theme: { background: "#191724", foreground: "#f6f1ff", cursor: "#ffd45c" },
      });
      const fit = new FitAddon();
      nextTerminal.loadAddon(fit);
      nextTerminal.open(container.current);
      fit.fit();
      terminal.current = nextTerminal;

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const nextSocket = new WebSocket(
        `${protocol}//${window.location.host}${session.websocket_path}`,
      );
      nextSocket.binaryType = "arraybuffer";
      socket.current = nextSocket;
      nextSocket.onopen = () => {
        setConnecting(false);
        fit.fit();
        nextSocket.send(JSON.stringify({
          type: "resize",
          cols: nextTerminal.cols,
          rows: nextTerminal.rows,
        }));
      };
      nextSocket.onmessage = (event) => {
        const output = event.data instanceof ArrayBuffer
          ? new TextDecoder().decode(event.data)
          : String(event.data);
        nextTerminal.write(output);
      };
      nextSocket.onerror = () => {
        setConnecting(false);
        onError(copy(language, "The Sandbox terminal connection failed"));
      };
      nextTerminal.onData((data) => {
        if (nextSocket.readyState === WebSocket.OPEN) {
          nextSocket.send(JSON.stringify({ type: "input", data }));
        }
      });
      const nextObserver = new ResizeObserver(() => {
        fit.fit();
        if (nextSocket.readyState === WebSocket.OPEN) {
          nextSocket.send(JSON.stringify({
            type: "resize",
            cols: nextTerminal.cols,
            rows: nextTerminal.rows,
          }));
        }
      });
      nextObserver.observe(container.current);
      resizeObserver.current = nextObserver;
    } catch (reason) {
      setConnecting(false);
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      onError(reason instanceof Error ? reason.message : copy(language, "Could not open restricted Vim"));
    }
  };

  const save = async () => {
    if (!sessionId || saving) return;
    setSaving(true);
    try {
      const version = await api.saveSandbox(projectId, sessionId);
      saved.current = true;
      onSaved(version);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : copy(language, "Could not save Vim changes"));
    } finally {
      setSaving(false);
    }
  };

  return <div className="terminal-panel">
    <div className="terminal-heading">
      <div><TerminalSquare size={17} /><span><strong>{copy(language, "Restricted Vim")}</strong><small>{copy(language, "Project worktree · no login shell · no network")}</small></span></div>
      {sessionId ? (
        <button onClick={save} disabled={saving || connecting}>
          {saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} {copy(language, "Save version")}
        </button>
      ) : (
        <button onClick={open} disabled={connecting}>
          {connecting ? <LoaderCircle className="spin" size={15} /> : <Play size={15} />} {copy(language, "Open Vim")}
        </button>
      )}
    </div>
    <div className="terminal-mount" ref={container} />
  </div>;
}

function copy(language: "zh" | "en", text: string): string {
  if (language === "en") return text;
  return {
    "The Sandbox terminal connection failed": "Sandbox 终端连接失败",
    "Could not open restricted Vim": "无法打开受限 Vim",
    "Could not save Vim changes": "无法保存 Vim 修改",
    "Restricted Vim": "受限 Vim",
    "Project worktree · no login shell · no network": "Project worktree · 无登录 Shell · 无网络",
    "Save version": "保存版本",
    "Open Vim": "打开 Vim",
  }[text] ?? text;
}

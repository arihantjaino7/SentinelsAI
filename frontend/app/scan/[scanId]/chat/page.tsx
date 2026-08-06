"use client";

/* Security chatbot — ask questions about a completed scan.

   Conversation is DB-backed on the server, so it persists across refresh.
   With no GROQ_API_KEY the backend returns 503; we show a clear unavailable
   state instead of an error screen. */

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { fetchChatHistory, postChatMessage, type ChatMessage } from "@/lib/api";

function Message({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-sm px-4 py-3 ${
          isUser
            ? "glass bg-white/6 text-parchment"
            : "border border-rule text-parchment/90"
        }`}
      >
        <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted mb-1.5">
          {isUser ? "You" : "Sentinels AI"}
        </p>
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { scanId } = useParams<{ scanId: string }>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChatHistory(scanId).then(setMessages);
  }, [scanId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const q = input.trim();
    if (!q || sending) return;
    setInput("");
    setSending(true);
    setError(null);

    // Optimistically add the user message so it appears immediately.
    const optimistic: ChatMessage = { role: "user", content: q, created_at: new Date().toISOString() };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const reply = await postChatMessage(scanId, q);
      setMessages((prev) => [...prev, reply]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Chat unavailable.";
      if (msg.includes("GROQ_API_KEY") || msg.includes("503")) {
        setUnavailable(true);
        // Remove the optimistic message — we can't send without a key.
        setMessages((prev) => prev.slice(0, -1));
        setInput(q);
      } else {
        setError(msg);
        setMessages((prev) => prev.slice(0, -1));
        setInput(q);
      }
    } finally {
      setSending(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  if (unavailable) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 py-24">
        <div className="mx-auto max-w-md text-center">
          <p className="font-mono text-xs uppercase tracking-[0.35em] text-muted">
            Unavailable
          </p>
          <p className="mt-4 font-display text-2xl">
            Chat requires GROQ_API_KEY.
          </p>
          <p className="mt-4 font-mono text-xs text-muted">
            Set GROQ_API_KEY in backend/.env and restart the server.
          </p>
        </div>
      </div>
    );
  }

  return (
    <article className="mx-auto flex w-full max-w-3xl flex-col px-6 py-20" style={{ minHeight: "calc(100vh - 57px)" }}>
      <header className="mb-10">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-muted">
          Security assistant
        </p>
        <h1 className="mt-3 font-display text-3xl">Ask about this scan</h1>
        <p className="mt-2 font-mono text-xs text-muted">
          Ask about findings, priorities, or how to fix specific issues. History persists on refresh.
        </p>
      </header>

      {/* Message list */}
      <div className="flex-1 space-y-6 overflow-y-auto pb-6">
        {messages.length === 0 && (
          <div className="space-y-2">
            {[
              "What should I fix first?",
              "Is this site safe to deploy?",
              "What's the most serious problem?",
              "How do I fix the missing CSP?",
            ].map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => { setInput(prompt); }}
                className="glass block w-full px-4 py-3 text-left font-mono text-xs text-muted transition-colors hover:bg-white/8 hover:text-parchment"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => (
          <Message key={i} msg={msg} />
        ))}

        {sending && (
          <div className="flex justify-start">
            <p className="animate-pulse font-mono text-[10px] uppercase tracking-[0.25em] text-muted">
              Thinking…
            </p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {error && (
        <p className="mb-3 font-mono text-[10px] text-critical">{error}</p>
      )}

      {/* Input */}
      <div className="glass flex items-end gap-3 px-4 py-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask a question… (Enter to send, Shift+Enter for new line)"
          rows={2}
          disabled={sending}
          className="flex-1 resize-none bg-transparent font-mono text-xs text-parchment placeholder:text-muted focus:outline-none disabled:opacity-50"
        />
        <button
          type="button"
          onClick={send}
          disabled={sending || !input.trim()}
          className="shrink-0 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted transition-colors hover:text-parchment disabled:cursor-not-allowed disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </article>
  );
}

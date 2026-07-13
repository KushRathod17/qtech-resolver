import { useState, useRef, useMemo } from "react";

import { Avatar } from "../board/constants";

/**
 * Comment box with @mention autocomplete.
 *
 * The mentioned people are tracked as ids alongside the text rather than parsed
 * back out of it on the server: two people can share a display name, and
 * "@Sara" is ambiguous in a way an id never is.
 */
export default function CommentComposer({ users, onSubmit, posting }) {
  const [body, setBody] = useState("");
  const [mentioned, setMentioned] = useState([]); // [{id, full_name}]
  const [query, setQuery] = useState(null); // null = menu closed
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef(null);

  const matches = useMemo(() => {
    if (query === null) return [];
    const q = query.toLowerCase();
    return users.filter((u) => u.full_name.toLowerCase().includes(q)).slice(0, 5);
  }, [query, users]);

  function onChange(e) {
    const value = e.target.value;
    setBody(value);

    // Open the menu on an "@" that starts a word and hasn't been completed yet.
    const upToCaret = value.slice(0, e.target.selectionStart);
    const match = /(?:^|\s)@([\w]*)$/.exec(upToCaret);
    setQuery(match ? match[1] : null);
    setCursor(0);
  }

  function pick(user) {
    // Replace the partial "@fra" with the full "@Full Name ".
    const caret = inputRef.current.selectionStart;
    const before = body.slice(0, caret).replace(/(?:^|\s)@[\w]*$/, (m) =>
      m.startsWith(" ") ? ` @${user.full_name} ` : `@${user.full_name} `
    );
    setBody(before + body.slice(caret));
    setMentioned((prev) => (prev.some((m) => m.id === user.id) ? prev : [...prev, user]));
    setQuery(null);
    inputRef.current?.focus();
  }

  function onKeyDown(e) {
    if (query !== null && matches.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((c) => Math.min(c + 1, matches.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) => Math.max(c - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        pick(matches[cursor]);
        return;
      }
      if (e.key === "Escape") {
        setQuery(null);
        return;
      }
    }
    if (e.key === "Enter") {
      e.preventDefault();
      submit();
    }
  }

  async function submit() {
    const text = body.trim();
    if (!text) return;
    // Only count people still actually named in the text — deleting the "@Sara"
    // you typed shouldn't silently keep watching her into the ticket.
    const stillMentioned = mentioned
      .filter((m) => text.includes(`@${m.full_name}`))
      .map((m) => m.id);

    await onSubmit(text, stillMentioned);
    setBody("");
    setMentioned([]);
    setQuery(null);
  }

  return (
    <div className="composer">
      {query !== null && matches.length > 0 && (
        <ul className="mention-menu">
          {matches.map((u, i) => (
            <li key={u.id}>
              <button
                type="button"
                className={`mention-option ${i === cursor ? "active" : ""}`}
                onMouseMove={() => setCursor(i)}
                onClick={() => pick(u)}
              >
                <Avatar user={u} size={20} />
                <span>{u.full_name}</span>
                <span className="mention-role">{u.role}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="comment-input-row">
        <input
          ref={inputRef}
          value={body}
          onChange={onChange}
          onKeyDown={onKeyDown}
          placeholder="Add a comment… use @ to mention someone"
          aria-label="Add a comment"
        />
        <button
          type="button"
          className="btn-secondary"
          onClick={submit}
          disabled={posting || !body.trim()}
        >
          {posting ? "Posting…" : "Post"}
        </button>
      </div>

      {mentioned.length > 0 && (
        <p className="field-hint">
          {mentioned.map((m) => m.full_name).join(", ")} will be added as watcher
          {mentioned.length === 1 ? "" : "s"}.
        </p>
      )}
    </div>
  );
}

/** Renders @Name in a comment body as a highlighted chip. */
export function CommentBody({ text, users }) {
  const names = users.map((u) => u.full_name).sort((a, b) => b.length - a.length);
  if (!names.length) return <p className="comment-body">{text}</p>;

  // Longest names first, so "@Sara Iqbal" wins over a hypothetical "@Sara".
  const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const parts = text.split(new RegExp(`(@(?:${escaped.join("|")}))`, "g"));

  return (
    <p className="comment-body">
      {parts.map((part, i) =>
        part.startsWith("@") && names.includes(part.slice(1)) ? (
          <span key={i} className="mention-chip">{part}</span>
        ) : (
          part
        )
      )}
    </p>
  );
}

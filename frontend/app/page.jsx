"use client";

import { useEffect, useMemo, useState } from "react";
import { isSupabaseConfigured, supabase } from "../lib/supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function HomePage() {
  const [voices, setVoices] = useState([]);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [voiceId, setVoiceId] = useState("en-US-AriaNeural");
  const [project, setProject] = useState(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [session, setSession] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState("");

  useEffect(() => {
    if (!supabase) return undefined;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => setSession(nextSession));
    return () => listener.subscription.unsubscribe();
  }, []);

  async function signIn(event) {
    event.preventDefault();
    setAuthError("");
    if (!supabase) {
      setAuthError("Supabase is not configured for this deployment.");
      return;
    }
    setSigningIn(true);
    const { error: loginError } = await supabase.auth.signInWithPassword({ email, password });
    if (loginError) setAuthError(loginError.message);
    setSigningIn(false);
  }

  async function apiFetch(path, options = {}) {
    const token = session?.access_token;
    const headers = { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    return fetch(`${API_URL}${path}`, { ...options, headers });
  }

  useEffect(() => {
    fetch(`${API_URL}/v1/voices`).then((response) => response.json()).then(setVoices).catch(() => setError("Voice list is unavailable. Start the local API and try again."));
  }, []);

  useEffect(() => {
    if (!project || ["ready", "failed"].includes(project.status)) return undefined;
    const poll = window.setInterval(async () => {
      const response = await apiFetch(`/v1/projects/${project.id}`);
      if (response.ok) setProject(await response.json());
    }, 2000);
    return () => window.clearInterval(poll);
  }, [project]);

  useEffect(() => {
    if (!project || project.status !== "ready" || !session) return undefined;
    setDownloadUrl("");
    apiFetch(`/v1/projects/${project.id}/download`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("Audio download is unavailable."))))
      .then((data) => setDownloadUrl(data.url))
      .catch((requestError) => setError(requestError.message));
    return undefined;
  }, [project, session]);

  const estimate = useMemo(() => {
    if (!text.length) return "About 0 minutes";
    return `About ${Math.max(1, Math.ceil(text.length / 850))} minute${text.length > 850 ? "s" : ""}`;
  }, [text]);

  async function createProject(event) {
    event.preventDefault();
    setError("");
    setCreating(true);
    try {
      if (!session) throw new Error("Sign in before creating audio.");
      const response = await apiFetch("/v1/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: title || "Untitled recording", text, voice_id: voiceId, speech_rate: "normal" }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "The project could not be created.");
      setProject(data);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="shell">
      {!session && <form className="card auth-card" onSubmit={signIn}><div className="section-label"><span>SIGN IN</span><span>PRIVATE PREVIEW</span></div>{!isSupabaseConfigured && <p className="error" role="alert">Supabase is not configured for this deployment.</p>}<label htmlFor="email">Email</label><input id="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /><label htmlFor="password">Password</label><input id="password" type="password" required value={password} onChange={(event) => setPassword(event.target.value)} />{authError && <p className="error" role="alert">{authError}</p>}<button className="button" type="submit" disabled={signingIn || !isSupabaseConfigured}>{signingIn ? "Signing in…" : "Sign in"}</button></form>}
      <header className="masthead"><p className="eyebrow">SIMPLE MP3 CREATOR / LOCAL PREVIEW</p><span className="status-dot">● API-first audio</span></header>
      <section className="hero"><div><p className="kicker">Your words, in a voice worth keeping.</p><h1>Make listening out of reading.</h1><p className="lede">Paste a passage, choose a voice, and create a clean MP3 with honest processing states and metadata ready to keep.</p></div><div className="hero-note"><span>01</span><p>Audio only.<br />No video. No clutter.</p></div></section>
      <section className="workspace" id="create" aria-hidden={!session}>
        <form className="card form-card" onSubmit={createProject}>
          <div className="section-label"><span>CREATE</span><span>{text.length.toLocaleString()} / 10,000 characters</span></div>
          <label htmlFor="title">Project title</label><input id="title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="A title for this recording" />
          <label htmlFor="text">Narration text</label><textarea id="text" required minLength={1} value={text} onChange={(event) => setText(event.target.value)} placeholder="Paste an article, note, or passage here…" rows={11} />
          <div className="form-row"><div><label htmlFor="voice">Voice</label><select id="voice" value={voiceId} onChange={(event) => setVoiceId(event.target.value)}>{(voices.length ? voices : [{ id: voiceId, label: "Loading voices…" }]).map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}</select></div><div className="estimate"><span>ESTIMATE</span><strong>{estimate}</strong></div></div>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="button" type="submit" disabled={creating || !text.trim()}>{creating ? "Starting…" : "Generate audio"}</button>
        </form>
        <aside className="card result-card" aria-live="polite"><div className="section-label"><span>PROJECT STATUS</span><span>{project ? project.status.toUpperCase() : "IDLE"}</span></div>{!project && <div className="empty-state"><span className="wave">∿</span><p>Your finished audio will appear here.</p><small>Keep this tab open during the local preview.</small></div>}{project && <div className="result-content"><h2>{project.title}</h2><p className="stage">{project.stage === "ready" ? "Ready to listen." : project.stage === "failed" ? "Generation failed." : "Preparing your audio…"}</p>{project.status === "ready" && <><div className="metrics"><span>{project.duration_ms ? `${Math.round(project.duration_ms / 1000)} sec` : "—"}</span><span>{project.output_bitrate ? `${Math.round(project.output_bitrate / 1000)} kbps` : "—"}</span></div>{downloadUrl ? <><audio controls src={downloadUrl} /><a className="download-link" href={downloadUrl}>Download MP3 ↗</a></> : <p className="stage">Preparing a private download link…</p>}</>}{project.status === "failed" && <p className="error">{project.error_code || "GENERATION_FAILED"}</p>}</div>}</aside>
      </section>
      <footer><span>Private by design.</span><span>Managed preview · private MP3 output</span></footer>
    </main>
  );
}

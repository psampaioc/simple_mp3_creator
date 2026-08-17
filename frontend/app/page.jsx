"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { isSupabaseConfigured, supabase } from "../lib/supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const ACTIVE_GENERATION_STATUSES = ["queued", "extracting", "generating", "tagging", "uploading"];

export default function HomePage() {
  const [voices, setVoices] = useState([]);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [inputMode, setInputMode] = useState("paste");
  const [sourceFile, setSourceFile] = useState(null);
  const [fileError, setFileError] = useState("");
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [voiceId, setVoiceId] = useState("en-US-AriaNeural");
  const [project, setProject] = useState(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [session, setSession] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [authMode, setAuthMode] = useState("sign-in");
  const [signingIn, setSigningIn] = useState(false);
  const [authOpen, setAuthOpen] = useState(true);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [downloadFilename, setDownloadFilename] = useState("audio.mp3");
  const [downloading, setDownloading] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const audioRef = useRef(null);
  const emailInputRef = useRef(null);

  useEffect(() => {
    if (!supabase) return undefined;
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      if (data.session) setAuthOpen(false);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      if (nextSession) setAuthOpen(false);
    });
    return () => listener.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) return undefined;
    let cancelled = false;
    apiFetch("/v1/projects")
      .then(async (response) => {
        if (!response.ok) throw new Error("Project status temporarily unavailable.");
        return response.json();
      })
      .then((projects) => {
        if (cancelled || !Array.isArray(projects)) return;
        const existing = projects.find((item) => ACTIVE_GENERATION_STATUSES.includes(item.status) || item.status === "review");
        if (existing) {
          setProject(existing);
          if (existing.status === "review" && typeof existing.source_text === "string") setReviewText(existing.source_text);
        }
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [session]);

  function openAuth(mode) {
    setAuthMode(mode);
    setAuthError("");
    setAuthMessage("");
    setAuthOpen(true);
  }

  async function submitAuth(event) {
    event.preventDefault();
    setAuthError("");
    setAuthMessage("");
    if (!supabase) {
      setAuthError("Supabase is not configured for this deployment.");
      return;
    }
    setSigningIn(true);
    const result = authMode === "sign-up"
      ? await supabase.auth.signUp({ email, password })
      : await supabase.auth.signInWithPassword({ email, password });
    if (result.error) setAuthError(result.error.message);
    else if (authMode === "sign-up" && !result.data.session) setAuthMessage("Account created. Check your email to confirm it, then sign in.");
    setSigningIn(false);
  }

  async function apiFetch(path, options = {}) {
    if (!API_URL) throw new Error("Service temporarily unavailable. Please try again shortly.");
    const token = session?.access_token;
    const headers = { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    return fetch(`${API_URL}${path}`, { ...options, headers });
  }

  useEffect(() => {
    if (!API_URL) {
      setError("Voice list temporarily unavailable. Please try again shortly.");
      return undefined;
    }
    fetch(`${API_URL}/v1/voices`).then((response) => response.ok ? response.json() : Promise.reject(new Error("Voice list unavailable"))).then(setVoices).catch(() => setError("Voice list temporarily unavailable. Please try again shortly."));
    return undefined;
  }, []);

  useEffect(() => {
    if (!project || ["ready", "review", "failed"].includes(project.status)) return undefined;
    const poll = window.setInterval(async () => {
      const response = await apiFetch(`/v1/projects/${project.id}`);
      if (response.ok) setProject(await response.json());
    }, 2000);
    return () => window.clearInterval(poll);
  }, [project]);

  useEffect(() => {
    if (project?.status === "review" && typeof project.source_text === "string") setReviewText(project.source_text);
  }, [project?.id, project?.status, project?.source_text]);

  useEffect(() => {
    if (!project || project.status !== "ready" || !session) return undefined;
    setDownloadUrl("");
    apiFetch(`/v1/projects/${project.id}/download`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("Audio download is unavailable."))))
      .then((data) => {
        setDownloadUrl(data.url);
        setDownloadFilename(data.filename || "audio.mp3");
      })
      .catch((requestError) => setError(requestError.message));
    return undefined;
  }, [project, session]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = playbackRate;
  }, [playbackRate, downloadUrl]);

  const estimate = useMemo(() => {
    const length = project?.status === "review" ? reviewText.length : text.length;
    if (!length) return "About 0 minutes";
    return `About ${Math.max(1, Math.ceil(length / 850))} minute${length > 850 ? "s" : ""}`;
  }, [project, reviewText, text]);

  function selectSourceFile(event) {
    const file = event.target.files?.[0] || null;
    setFileError("");
    setUploadStatus("");
    setUploadProgress(0);
    setSourceFile(null);
    if (!file) return;
    const suffix = `.${file.name.split(".").pop()?.toLowerCase()}`;
    if (![".txt", ".pdf", ".docx"].includes(suffix)) {
      setFileError("Choose a .txt, .pdf, or .docx file.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setFileError("Documents must be 5 MB or smaller.");
      return;
    }
    setSourceFile(file);
  }

  async function confirmExtractedText() {
    setError("");
    setCreating(true);
    try {
      const response = await apiFetch(`/v1/projects/${project.id}/source-text`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: reviewText }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "The extracted text could not be saved.");
      setProject(data);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCreating(false);
    }
  }

  async function downloadAudio() {
    if (!downloadUrl || downloading) return;
    setError("");
    setDownloading(true);
    try {
      const response = await fetch(downloadUrl);
      if (!response.ok) throw new Error("The MP3 download is unavailable. Please try again.");
      const blobUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = downloadFilename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setDownloading(false);
    }
  }

  async function createProject(event) {
    event.preventDefault();
    setError("");
    if (!session) {
      setAuthError("Sign in to create audio.");
      setAuthOpen(true);
      return;
    }
    if (project?.status === "review") {
      await confirmExtractedText();
      return;
    }
    if (inputMode === "upload" && !sourceFile) {
      setFileError("Choose a document first.");
      return;
    }
    setCreating(true);
    try {
      let source = {};
      if (inputMode === "upload") {
        setUploadStatus("Requesting secure upload…");
        setUploadProgress(10);
        const sourceResponse = await apiFetch("/v1/source-files", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: sourceFile.name, content_type: sourceFile.type || "application/octet-stream", size_bytes: sourceFile.size }) });
        const sourceData = await sourceResponse.json();
        if (!sourceResponse.ok) throw new Error(sourceData.detail || "The document upload could not be started.");
        setUploadStatus("Uploading document…");
        setUploadProgress(60);
        const { error: uploadError } = await supabase.storage.from("project-assets").uploadToSignedUrl(sourceData.path, sourceData.token, sourceFile, { contentType: sourceData.content_type, upsert: false });
        if (uploadError) throw new Error(uploadError.message || "The document upload failed.");
        setUploadProgress(100);
        source = { source_type: sourceData.source_type, source_storage_path: sourceData.path, source_filename: sourceFile.name, source_content_type: sourceData.content_type, source_size_bytes: sourceFile.size };
        setUploadStatus("Document uploaded. Extracting text…");
      }
      const response = await apiFetch("/v1/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: title || (sourceFile?.name?.replace(/\.[^.]+$/, "") || "Untitled recording"), ...(inputMode === "paste" ? { text } : source), voice_id: voiceId, speech_rate: "normal" }) });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 409 && data.detail?.code === "GENERATION_IN_PROGRESS" && data.detail.project) {
          setProject(data.detail.project);
          setError("");
          return;
        }
        throw new Error(typeof data.detail === "string" ? data.detail : "The project could not be created.");
      }
      setProject(data);
      setReviewText(data.source_text || "");
      setUploadStatus("");
      setUploadProgress(0);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCreating(false);
    }
  }

  const generationActive = Boolean(project && ACTIVE_GENERATION_STATUSES.includes(project.status));
  const userInitial = session?.user?.email?.slice(0, 1).toUpperCase() || "?";

  useEffect(() => {
    if (!authOpen) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setAuthOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    window.requestAnimationFrame(() => emailInputRef.current?.focus());
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [authOpen]);

  return (
    <main className="shell">
      {!session && authOpen && <div className="auth-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setAuthOpen(false); }}><form className="card auth-card" onSubmit={submitAuth} role="dialog" aria-modal="true" aria-labelledby="auth-title"><div className="auth-heading"><div><p className="eyebrow">PRIVATE PREVIEW</p><h2 id="auth-title">{authMode === "sign-up" ? "Create an account." : "Welcome back."}</h2></div><button className="icon-button" type="button" aria-label="Close sign in" onClick={() => setAuthOpen(false)}>×</button></div><p className="auth-intro">{authMode === "sign-up" ? "Create a private account for your MP3s." : "Sign in to turn your words into a private MP3."}</p>{!isSupabaseConfigured && <p className="error" role="alert">Supabase is not configured for this deployment.</p>}<label htmlFor="email">Email</label><input ref={emailInputRef} id="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /><label htmlFor="password">Password</label><input id="password" type="password" required minLength={6} value={password} onChange={(event) => setPassword(event.target.value)} />{authError && <p className="error" role="alert">{authError}</p>}{authMessage && <p className="auth-message" role="status">{authMessage}</p>}<button className="button auth-submit" type="submit" disabled={signingIn || !isSupabaseConfigured}>{signingIn ? "Working…" : authMode === "sign-up" ? "Sign up" : "Sign in"}</button><button className="auth-switch" type="button" onClick={() => openAuth(authMode === "sign-up" ? "sign-in" : "sign-up")}>{authMode === "sign-up" ? "Already have an account? Sign in" : "Need an account? Sign up"}</button><p className="auth-footnote">Private by design · audio only</p></form></div>}
      <div className="page-content" aria-hidden={!session && authOpen}>
        <header className="masthead"><p className="eyebrow">SIMPLE MP3 CREATOR / MANAGED PREVIEW</p><div className="masthead-actions"><span className="status-dot">● API-first audio</span><details className="account-menu"><summary className="account-trigger">{session ? userInitial : "Sign up"}</summary><div className="account-popover">{session ? <><span className="account-email">{session.user?.email}</span><button type="button" onClick={() => supabase?.auth.signOut()}>Sign out</button></> : <><button type="button" onClick={() => openAuth("sign-in")}>Sign in</button><button type="button" onClick={() => openAuth("sign-up")}>Sign up</button></>}</div></details></div></header>
        <section className="hero"><div><p className="kicker">Your words, in a voice worth keeping.</p><h1>Make listening out of reading.</h1><p className="lede">Paste a passage, choose a voice, and create a clean MP3 with honest processing states and metadata ready to keep.</p></div><div className="hero-note"><span>01</span><p>Audio only.<br />No video. No clutter.</p></div></section>
        <section className="workspace" id="create">
        <form className="card form-card" onSubmit={createProject}>
          <div className="section-label"><span>CREATE</span><span>{(project?.status === "review" ? reviewText : text).length.toLocaleString()} / 10,000 characters</span></div>
          <label htmlFor="title">Project title</label><input id="title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="A title for this recording" />
          {!project || project.status !== "review" ? <><div className="input-mode" role="group" aria-label="Source type"><button className={inputMode === "paste" ? "mode-button active" : "mode-button"} type="button" onClick={() => { setInputMode("paste"); setFileError(""); }}>Paste text</button><button className={inputMode === "upload" ? "mode-button active" : "mode-button"} type="button" onClick={() => { setInputMode("upload"); setFileError(""); }}>Upload document</button></div>{inputMode === "paste" ? <><label htmlFor="text">Narration text</label><textarea id="text" required minLength={1} value={text} onChange={(event) => setText(event.target.value)} placeholder="Paste an article, note, or passage here…" rows={11} /></> : <><label htmlFor="source-file">Document</label><input id="source-file" type="file" accept=".txt,.pdf,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={selectSourceFile} />{sourceFile && <p className="file-meta">{sourceFile.name} · {(sourceFile.size / 1024 / 1024).toFixed(2)} MB</p>}{fileError && <p className="error" role="alert">{fileError}</p>}{uploadStatus && <><p className="stage" role="status">{uploadStatus}</p><progress className="upload-progress" value={uploadProgress} max="100" /></>}</>}</> : <><label htmlFor="review-text">Review extracted text</label><textarea id="review-text" required minLength={1} value={reviewText} onChange={(event) => setReviewText(event.target.value)} rows={11} /><p className="stage">Check the extraction before generating audio.</p></>}
          <div className="form-row"><div><label htmlFor="voice">Voice</label><select id="voice" value={voiceId} onChange={(event) => setVoiceId(event.target.value)}>{(voices.length ? voices : [{ id: voiceId, label: "Loading voices…" }]).map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}</select></div><div className="estimate"><span>ESTIMATE</span><strong>{estimate}</strong></div></div>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="button" type="submit" disabled={creating || generationActive || (project?.status === "review" ? !reviewText.trim() : inputMode === "paste" ? !text.trim() : !sourceFile)}>{generationActive ? "Generating…" : creating ? (project?.status === "review" ? "Starting…" : "Uploading…") : "Generate audio"}</button>
        </form>
        <aside className="card result-card" aria-live="polite"><div className="section-label"><span>PROJECT STATUS</span><span>{project ? project.status.toUpperCase() : "IDLE"}</span></div>{!project && <div className="empty-state"><span className="wave">∿</span><p>Your finished audio will appear here.</p><small>Keep this tab open during the local preview.</small></div>}{project && <div className="result-content"><h2>{project.title}</h2><p className="stage">{project.stage === "ready" ? "Ready to listen." : project.stage === "failed" ? "Generation failed." : "Preparing your audio…"}</p>{project.status === "ready" && <><div className="metrics"><span>{project.duration_ms ? `${Math.round(project.duration_ms / 1000)} sec` : "—"}</span><span>{project.output_bitrate ? `${Math.round(project.output_bitrate / 1000)} kbps` : "—"}</span></div>{downloadUrl ? <><audio ref={audioRef} controls src={downloadUrl} /><div className="audio-actions"><label htmlFor="playback-rate">Speed</label><select id="playback-rate" value={playbackRate} onChange={(event) => setPlaybackRate(Number(event.target.value))}><option value="0.75">0.75×</option><option value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select><button className="download-button" type="button" onClick={downloadAudio} disabled={downloading}>{downloading ? "Downloading…" : "Download MP3 ↓"}</button></div></> : <p className="stage">Preparing a private audio link…</p>}</>}{project.status === "failed" && <p className="error">{project.error_code || "GENERATION_FAILED"}</p>}</div>}</aside>
        </section>
        <footer><span>Private by design.</span><span>Managed preview · private MP3 output</span></footer>
      </div>
    </main>
  );
}

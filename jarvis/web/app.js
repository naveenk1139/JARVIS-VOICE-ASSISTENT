/* J.A.R.V.I.S browser front door.
 *
 * Speech in  : Web Speech API (SpeechRecognition)
 * Speech out : Web Speech API (speechSynthesis)
 * Everything else goes through POST /api/command, so the same engine serves the
 * browser, the desktop console and the CLI.
 */
(() => {
  "use strict";

  const els = {
    reactor: document.getElementById("reactor"),
    status: document.getElementById("status-line"),
    transcript: document.getElementById("transcript"),
    mic: document.getElementById("mic-btn"),
    form: document.getElementById("text-form"),
    input: document.getElementById("text-input"),
    speakToggle: document.getElementById("speak-toggle"),
    personaToggle: document.getElementById("persona-toggle"),
    resetBtn: document.getElementById("reset-btn"),
    suggestions: document.getElementById("suggestions"),
    hudTime: document.getElementById("hud-time"),
    hudSkills: document.getElementById("hud-skills"),
    hudBrain: document.getElementById("hud-brain"),
    hudSession: document.getElementById("hud-session"),
    hudWeather: document.getElementById("hud-weather"),
    hudNotes: document.getElementById("hud-notes"),
    hint: document.getElementById("stt-hint"),
  };

  const state = {
    sessionId: localStorage.getItem("jarvis.session") || `web-${Math.random().toString(36).slice(2, 10)}`,
    busy: false,
    listening: false,
    persona: "jarvis",
    voice: null,
    seenReminders: new Set(),
  };
  localStorage.setItem("jarvis.session", state.sessionId);
  els.hudSession.textContent = state.sessionId;

  const api = {
    async get(path) {
      const response = await fetch(path, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`${path} -> ${response.status}`);
      return response.json();
    },
    async post(path, body) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`${path} -> ${response.status}`);
      return response.json();
    },
  };

  /* ------------------------------------------------------------ UI helpers */
  function setReactor(mode, label) {
    els.reactor.className = `reactor ${mode || ""}`.trim();
    if (label) els.status.textContent = label;
  }

  function bubble(role, text, { skill, kind, url, items } = {}) {
    const node = document.createElement("div");
    node.className = `bubble ${role}${kind === "error" ? " error" : ""}`;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = `<span>${role === "user" ? "You" : "JARVIS"}</span>`;
    if (skill && role !== "user") {
      const chip = document.createElement("span");
      chip.className = "skill-chip";
      chip.textContent = skill;
      meta.appendChild(chip);
    }
    node.appendChild(meta);

    const body = document.createElement("div");
    body.textContent = text;
    node.appendChild(body);

    if (items && items.length) {
      const list = document.createElement("ul");
      items.forEach((item) => {
        const li = document.createElement("li");
        if (typeof item === "string") {
          li.textContent = item;
        } else {
          const label = document.createElement("span");
          label.textContent = item.title || item.text || "";
          li.appendChild(label);
          if (item.url) {
            const link = document.createElement("a");
            link.href = item.url;
            link.target = "_blank";
            link.rel = "noreferrer";
            link.className = "open-link";
            link.textContent = "Read";
            li.appendChild(document.createTextNode(" "));
            li.appendChild(link);
          }
        }
        list.appendChild(li);
      });
      node.appendChild(list);
    } else if (url) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.className = "open-link";
      link.textContent = "Open in a new tab";
      node.appendChild(link);
    }

    els.transcript.appendChild(node);
    els.transcript.scrollTop = els.transcript.scrollHeight;
    return node;
  }

  /* ---------------------------------------------------------------- speech */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognizer = null;

  if (SpeechRecognition) {
    recognizer = new SpeechRecognition();
    recognizer.lang = "en-IN";
    recognizer.interimResults = true;
    recognizer.continuous = false;

    recognizer.onstart = () => {
      state.listening = true;
      els.mic.classList.add("active");
      setReactor("listening", "Listening…");
    };
    recognizer.onerror = (event) => {
      state.listening = false;
      els.mic.classList.remove("active");
      const messages = {
        "not-allowed": "Microphone permission was blocked — use the text box, or allow the microphone.",
        "no-speech": "I did not hear anything. Try again.",
        network: "Speech recognition needs a network connection in this browser.",
        aborted: "",
      };
      const message = messages[event.error] ?? `Speech recognition error: ${event.error}`;
      setReactor("error", "Speech unavailable");
      if (message) els.hint.textContent = message;
      if (event.error === "not-allowed") els.mic.disabled = true;
    };
    recognizer.onend = () => {
      state.listening = false;
      els.mic.classList.remove("active");
      if (!state.busy) setReactor("", "Idle — hold the mic or type a command");
    };
    recognizer.onresult = (event) => {
      const result = event.results[event.results.length - 1];
      if (!result.isFinal) {
        setReactor("listening", `“${result[0].transcript.trim()}…”`);
        return;
      }
      const transcript = result[0].transcript.trim();
      if (transcript) send(transcript);
    };
  } else {
    els.mic.disabled = true;
    els.hint.textContent = "This browser has no SpeechRecognition API (try Chrome or Edge) — typing works everywhere.";
  }

  function speak(text) {
    if (!els.speakToggle.checked || !window.speechSynthesis || !text) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    if (state.voice) utterance.voice = state.voice;
    utterance.rate = 1.02;
    utterance.pitch = state.persona === "friday" ? 1.25 : 0.92;
    utterance.onstart = () => setReactor("speaking", "Speaking…");
    utterance.onend = () => setReactor("", "Idle — hold the mic or type a command");
    window.speechSynthesis.speak(utterance);
  }

  function pickVoice(persona) {
    const voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    if (!voices.length) return;
    const english = voices.filter((voice) => voice.lang && voice.lang.toLowerCase().startsWith("en"));
    const pool = english.length ? english : voices;
    const female = /(female|zira|susan|samantha|karen|tessa|google uk english female|google us english)/i;
    const male = /(male|david|daniel|alex|fred|rishi|google uk english male)/i;
    const wanted = persona === "friday" ? female : male;
    const unwanted = persona === "friday" ? male : female;
    state.voice =
      pool.find((voice) => wanted.test(voice.name) && !unwanted.test(voice.name)) ||
      pool.find((voice) => wanted.test(voice.name)) ||
      pool[0];
  }

  if (window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = () => pickVoice(state.persona);
    pickVoice(state.persona);
  }

  /* --------------------------------------------------------------- commands */
  async function send(text) {
    if (state.busy || !text.trim()) return;
    state.busy = true;
    els.input.value = "";
    bubble("user", text);
    setReactor("thinking", "Thinking…");

    try {
      const payload = await api.post("/api/command", { text, session_id: state.sessionId });
      render(payload);
    } catch (error) {
      bubble("jarvis", `I could not reach my engine (${error.message}). Is the server still running?`, { kind: "error" });
      setReactor("error", "Connection problem");
    } finally {
      state.busy = false;
      refreshNotes();
    }
  }

  function render(payload) {
    const data = payload.data || {};
    let items = null;
    if (Array.isArray(data.headlines) && data.headlines.length) items = data.headlines;
    else if (Array.isArray(data.notes) && data.notes.length) items = data.notes.map((note) => note.text);

    bubble("jarvis", payload.text, {
      skill: payload.skill,
      kind: payload.kind,
      url: payload.url,
      items,
    });

    if (data.whatsapp || payload.url) { /* links stay clickable, never auto-open */ }
    if (data.persona) applyPersona(data.persona, { announce: false });
    if (payload.kind === "exit") {
      setReactor("", "Standing by");
      els.hint.textContent = "Session ended — press the mic when you need me again.";
    } else {
      setReactor("", "Idle — hold the mic or type a command");
    }
    speak(payload.text);
    if (payload.kind === "exit") window.speechSynthesis && window.speechSynthesis.cancel();
  }

  function applyPersona(persona, { announce = true } = {}) {
    state.persona = persona;
    els.personaToggle.checked = persona === "friday";
    pickVoice(persona);
    if (announce) speak(`Switching to the ${persona.toUpperCase()} voice.`);
  }

  /* ------------------------------------------------------------------- HUD */
  function tickClock() {
    const now = new Date();
    els.hudTime.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  async function refreshHealth() {
    try {
      const data = await api.get("/api/health");
      const assistant = data.assistant;
      els.hudSkills.textContent = assistant.skills;
      els.hudBrain.textContent = assistant.brain === "none" ? "rules only" : assistant.brain;
      setReactor("", "Idle — hold the mic or type a command");
      if (assistant.persona) applyPersona(assistant.persona, { announce: false });
    } catch {
      setReactor("error", "Engine offline");
      els.hudBrain.textContent = "offline";
    }
  }

  async function refreshSuggestions() {
    try {
      const data = await api.get("/api/skills");
      els.suggestions.innerHTML = "";
      (data.suggestions || []).forEach((text) => {
        const chip = document.createElement("button");
        chip.className = "chip";
        chip.type = "button";
        chip.textContent = text;
        chip.addEventListener("click", () => send(text));
        els.suggestions.appendChild(chip);
      });
    } catch {
      els.suggestions.innerHTML = '<p class="muted">Suggestions unavailable.</p>';
    }
  }

  async function refreshWeather() {
    try {
      const data = await api.get("/api/weather");
      if (data.error) throw new Error(data.error);
      els.hudWeather.innerHTML = `
        <p class="temp">${Math.round(data.temperature)}${data.unit_symbol}</p>
        <p class="desc">${data.description}</p>
        <p class="muted">${data.place} · humidity ${data.humidity}% · wind ${Math.round(data.wind_speed)} ${data.unit_symbol === "°C" ? "km/h" : "mph"}</p>`;
    } catch {
      els.hudWeather.innerHTML = '<p class="muted">Weather unavailable right now.</p>';
    }
  }

  async function refreshNotes() {
    try {
      const data = await api.get("/api/notes");
      const items = [...(data.open || [])];
      els.hudNotes.innerHTML = "";
      if (!items.length) {
        els.hudNotes.innerHTML = '<li class="muted">Nothing stored yet.</li>';
      }
      items.slice(0, 6).forEach((note) => {
        const li = document.createElement("li");
        li.textContent = note.text;
        if (note.due_at) {
          li.classList.add("due");
          li.textContent += ` · due ${new Date(note.due_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
        }
        els.hudNotes.appendChild(li);
      });
      Object.values(data.memories || {}).slice(0, 3).forEach((value) => {
        const li = document.createElement("li");
        li.textContent = `🧠 ${value}`;
        els.hudNotes.appendChild(li);
      });
    } catch {
      /* the HUD is optional; never block the console on it */
    }
  }

  async function pollReminders() {
    try {
      const data = await api.get("/api/reminders/due");
      (data.due || []).forEach((note) => {
        if (state.seenReminders.has(note.id)) return;
        state.seenReminders.add(note.id);
        bubble("jarvis", `Reminder: ${note.text}`, { skill: "reminder" });
        speak(`Reminder. ${note.text}`);
      });
    } catch {
      /* offline is fine */
    }
  }

  /* ---------------------------------------------------------------- events */
  function beginListen() {
    if (!recognizer || state.listening || state.busy) return;
    try {
      recognizer.start();
    } catch {
      /* already started */
    }
  }

  function endListen() {
    if (!recognizer || !state.listening) return;
    recognizer.stop();
  }

  els.mic.addEventListener("pointerdown", (event) => { event.preventDefault(); beginListen(); });
  els.mic.addEventListener("pointerup", endListen);
  els.mic.addEventListener("pointerleave", endListen);

  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    send(els.input.value);
  });

  document.addEventListener("keydown", (event) => {
    const typing = document.activeElement === els.input;
    if (event.code === "Space" && !typing && !event.repeat) {
      event.preventDefault();
      beginListen();
    }
  });
  document.addEventListener("keyup", (event) => {
    if (event.code === "Space" && document.activeElement !== els.input) endListen();
  });

  els.resetBtn.addEventListener("click", async () => {
    try {
      await api.post("/api/reset", { session_id: state.sessionId });
    } catch { /* ignore */ }
    els.transcript.innerHTML = "";
    bubble("jarvis", "Conversation cleared. How can I help?", { skill: "system" });
  });

  els.personaToggle.addEventListener("change", async (event) => {
    const wanted = event.target.checked ? "friday" : "jarvis";
    state.persona = wanted;
    pickVoice(wanted);
    await send(`switch to ${wanted}`);
  });

  /* ------------------------------------------------------------------ boot */
  bubble(
    "jarvis",
    "At your service. Hold the microphone button (or the space bar) and speak, or type below. " +
      "Try “what is the weather”, “tell me the news” or “add buy milk to my to-do list”.",
    { skill: "boot" }
  );
  tickClock();
  setInterval(tickClock, 15000);
  refreshHealth();
  refreshSuggestions();
  refreshWeather();
  refreshNotes();
  pollReminders();
  setInterval(refreshWeather, 10 * 60 * 1000);
  setInterval(refreshNotes, 30000);
  setInterval(pollReminders, 30000);
})();

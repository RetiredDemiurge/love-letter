const CARD_META = {
  guard: { name: "Guard", needsTarget: true, needsGuess: true, hint: "Guess a card in opponent hand (except Guard)." },
  priest: { name: "Priest", needsTarget: true, hint: "Privately view one opponent hand." },
  baron: { name: "Baron", needsTarget: true, hint: "Compare hands; lower value is eliminated." },
  handmaid: { name: "Handmaid", hint: "You are protected until your next turn." },
  prince: { name: "Prince", needsTarget: true, canSelf: true, hint: "Target discards hand and draws replacement." },
  king: { name: "King", needsTarget: true, hint: "Swap hands with an opponent." },
  countess: { name: "Countess", hint: "Must be played with King or Prince." },
  princess: { name: "Princess", hint: "If discarded, you are eliminated." },
};

const DECK = [
  ...Array(5).fill("guard"),
  ...Array(2).fill("priest"),
  ...Array(2).fill("baron"),
  ...Array(2).fill("handmaid"),
  ...Array(2).fill("prince"),
  "king",
  "countess",
  "princess",
];

const STORAGE_KEY = "love_letter_multiplayer_session";
const cardPath = (id) => `../assets/cards/${id}.png`;

const handEl = document.querySelector("#hand");
const logEl = document.querySelector("#log");
const messagesEl = document.querySelector("#messages");
const galleryEl = document.querySelector("#gallery");
const playersEl = document.querySelector("#players");
const statusEl = document.querySelector("#status");
const tableStatusEl = document.querySelector("#table-status");

const deckCountEl = document.querySelector("#deck-count");
const burnedCountEl = document.querySelector("#burned-count");
const faceUpEl = document.querySelector("#face-up-cards");

const btnStart = document.querySelector("#btn-start");
const btnHide = document.querySelector("#btn-hide");
const btnNextRound = document.querySelector("#btn-next-round");
const btnCreateTable = document.querySelector("#btn-create-table");
const btnJoinTable = document.querySelector("#btn-join-table");
const btnLeaveTable = document.querySelector("#btn-leave-table");
const btnCopyCode = document.querySelector("#btn-copy-code");
const btnCopyLink = document.querySelector("#btn-copy-link");

const nameInput = document.querySelector("#name-input");
const joinCodeInput = document.querySelector("#join-code-input");
const invitePanel = document.querySelector("#invite-panel");
const inviteCodeInput = document.querySelector("#invite-code");
const seatSelect = document.querySelector("#seat-select");
const guessSelect = document.querySelector("#guess-select");
const cardPreviewEl = document.querySelector("#card-preview");
const cardPreviewImageEl = document.querySelector("#card-preview-image");
const cardPreviewNameEl = document.querySelector("#card-preview-name");
const cardPreviewHintEl = document.querySelector("#card-preview-hint");
const actionTrayEl = document.querySelector("#action-tray");
const actionSummaryEl = document.querySelector("#action-summary");
const targetPickerEl = document.querySelector("#target-picker");
const btnPlayContext = document.querySelector("#btn-play-context");
const btnCancelSelect = document.querySelector("#btn-cancel-select");

const discardZone = document.querySelector("#discard-zone");

let state = null;
let selectedIndex = null;
let selectedTarget = null;
let hidden = false;
let busy = false;
let fetchSeq = 0;
let localMessages = [];
let stateSignature = "";
let previewCardId = null;

let gameId = null;
let seatToken = null;
let playerId = null;

function addMessage(message) {
  localMessages = [message, ...localMessages].slice(0, 20);
  renderMessages();
}

function setBusy(value) {
  busy = value;
  updateControls();
}

function setStatus(message) {
  statusEl.textContent = message;
}

function setTableStatus(message) {
  tableStatusEl.textContent = message;
}

function persistSession() {
  if (!gameId || !seatToken) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ gameId, seatToken }));
}

function restoreSession() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return;
  }
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed.gameId === "string" && typeof parsed.seatToken === "string") {
      gameId = parsed.gameId;
      seatToken = parsed.seatToken;
      setTableStatus("Reconnected to existing table.");
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function authHeaders(includeJson = false) {
  const headers = {};
  if (includeJson) {
    headers["Content-Type"] = "application/json";
  }
  if (seatToken) {
    headers["X-Seat-Token"] = seatToken;
  }
  return headers;
}

async function readError(response, fallback) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string" && payload.detail) {
      return payload.detail;
    }
  } catch {
    // Ignore invalid JSON from server-side errors.
  }
  return fallback;
}

function normalizeJoinCode(value) {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6);
}

function getInviteLink(code) {
  const url = new URL(window.location.href);
  url.searchParams.set("code", code);
  return url.toString();
}

async function copyText(value, successMessage) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value);
      addMessage(successMessage);
      return;
    }
  } catch {
    // Fall back to execCommand below.
  }
  const temp = document.createElement("textarea");
  temp.value = value;
  document.body.appendChild(temp);
  temp.select();
  document.execCommand("copy");
  document.body.removeChild(temp);
  addMessage(successMessage);
}

function updateControls() {
  btnCreateTable.disabled = busy;
  btnJoinTable.disabled = busy;
  btnLeaveTable.disabled = busy || !gameId;
  btnCopyCode.disabled = busy || !state?.join_code || playerId !== 0;
  btnCopyLink.disabled = busy || !state?.join_code || playerId !== 0;
  btnHide.disabled = busy;
  btnPlayContext.disabled = true;

  if (!state || playerId === null) {
    btnStart.disabled = true;
    btnNextRound.disabled = true;
    return;
  }

  const me = state.players.find((player) => player.id === playerId);
  const isMyTurn = state.current_player_id === playerId;
  const handCount = me?.hand_count ?? 0;
  const waiting = Boolean(state.waiting_for_opponent);
  const selectedCardId = getSelectedCardId();
  const selectedMeta = selectedCardId ? CARD_META[selectedCardId] : null;
  const targetOptions = selectedCardId ? getTargetOptions(selectedCardId) : [];
  const selectableTargetIds = targetOptions.filter((item) => item.selectable).map((item) => item.player.id);
  const targetRequired = Boolean(selectedMeta?.needsTarget);
  const missingTarget = targetRequired && selectableTargetIds.length > 0 && !selectableTargetIds.includes(selectedTarget);

  btnStart.disabled = busy || waiting || state.game_over || state.round_over || !isMyTurn || handCount !== 1;
  btnPlayContext.disabled =
    busy ||
    waiting ||
    state.game_over ||
    state.round_over ||
    !isMyTurn ||
    handCount !== 2 ||
    !selectedCardId ||
    missingTarget;
  btnNextRound.disabled = busy || waiting || state.game_over || !state.round_over;
}

function getTargetOptions(cardId) {
  if (!state || playerId === null) return [];
  if (!CARD_META[cardId]?.needsTarget) return [];

  const options = [];
  for (const player of state.players) {
    let selectable = true;
    let reason = "Available target";
    if (player.eliminated) {
      selectable = false;
      reason = "Player is eliminated";
    } else if (cardId === "prince") {
      if (player.id !== playerId && player.protected) {
        selectable = false;
        reason = "Protected by Handmaid";
      } else if (player.id === playerId) {
        reason = "Self target is allowed";
      }
    } else {
      if (player.id === playerId) {
        selectable = false;
        reason = "You cannot target yourself";
      } else if (player.protected) {
        selectable = false;
        reason = "Protected by Handmaid";
      }
    }
    options.push({ player, selectable, reason });
  }
  return options;
}

function createCard(cardId, index) {
  const div = document.createElement("div");
  div.className = "card";
  div.draggable = true;
  if (hidden) {
    div.classList.add("hidden");
  }
  if (selectedIndex === index) {
    div.classList.add("selected");
  }

  const img = document.createElement("img");
  img.src = cardPath(cardId);
  img.alt = CARD_META[cardId]?.name ?? cardId;
  div.appendChild(img);

  div.addEventListener("click", () => {
    selectedIndex = selectedIndex === index ? null : index;
    if (selectedIndex === null) {
      selectedTarget = null;
    }
    render();
  });

  div.addEventListener("mouseenter", () => {
    previewCardId = cardId;
    renderCardPreview();
  });

  div.addEventListener("mouseleave", () => {
    previewCardId = null;
    renderCardPreview();
  });

  div.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", String(index));
  });

  return div;
}

function getMyHand() {
  return state?.players.find((player) => player.id === playerId)?.hand ?? [];
}

function getSelectedCardId() {
  const hand = getMyHand();
  if (selectedIndex === null) return null;
  return hand[selectedIndex] ?? null;
}

function renderHand() {
  handEl.innerHTML = "";
  const hand = getMyHand();
  hand.forEach((cardId, index) => {
    handEl.appendChild(createCard(cardId, index));
  });
}

function renderPlayers() {
  playersEl.innerHTML = "";
  if (!state) {
    return;
  }
  state.players.forEach((player) => {
    const card = document.createElement("div");
    card.className = "player";
    if (player.id === state.current_player_id) {
      card.classList.add("active");
    }
    if (player.id === selectedTarget) {
      card.classList.add("selected");
    }
    card.innerHTML = `
      <h3>${player.name}</h3>
      <div class="meta"><span>Tokens</span><span>${player.tokens}</span></div>
      <div class="meta"><span>Hand</span><span>${player.hand_count}</span></div>
      <div class="meta"><span>Discard</span><span>${player.discard.length}</span></div>
      <div class="status">${player.eliminated ? "Eliminated" : player.protected ? "Protected" : ""}</div>
    `;
    const miniDiscard = document.createElement("div");
    miniDiscard.className = "mini-discard";
    player.discard.slice(-3).reverse().forEach((cardId) => {
      const mini = document.createElement("div");
      mini.className = "card";
      const img = document.createElement("img");
      img.src = cardPath(cardId);
      img.alt = CARD_META[cardId]?.name ?? cardId;
      mini.appendChild(img);
      miniDiscard.appendChild(mini);
    });
    card.appendChild(miniDiscard);
    playersEl.appendChild(card);
  });
}

function renderPiles() {
  if (!state) {
    deckCountEl.textContent = "0";
    burnedCountEl.textContent = "0";
    faceUpEl.innerHTML = "";
    return;
  }
  deckCountEl.textContent = state.deck_count;
  burnedCountEl.textContent = state.burned_count;
  faceUpEl.innerHTML = "";
  state.face_up.forEach((cardId) => {
    const card = document.createElement("div");
    card.className = "card";
    const img = document.createElement("img");
    img.src = cardPath(cardId);
    img.alt = CARD_META[cardId]?.name ?? cardId;
    card.appendChild(img);
    faceUpEl.appendChild(card);
  });
}

function renderGallery() {
  galleryEl.innerHTML = "";
  DECK.forEach((cardId, index) => {
    const wrapper = document.createElement("div");
    wrapper.className = "card";
    const img = document.createElement("img");
    img.src = cardPath(cardId);
    img.alt = CARD_META[cardId]?.name ?? cardId;
    wrapper.appendChild(img);
    wrapper.title = `Card ${index + 1}`;
    galleryEl.appendChild(wrapper);
  });
}

function renderSelectors() {
  seatSelect.innerHTML = "";
  if (!state || playerId === null) {
    const option = document.createElement("option");
    option.textContent = "Not connected";
    option.value = "";
    seatSelect.appendChild(option);
  } else {
    state.players.forEach((player) => {
      const option = document.createElement("option");
      option.value = String(player.id);
      option.textContent = player.name;
      option.selected = player.id === playerId;
      seatSelect.appendChild(option);
    });
  }

  guessSelect.innerHTML = "";
  Object.keys(CARD_META).forEach((id) => {
    if (id === "guard") return;
    const option = document.createElement("option");
    option.value = id;
    option.textContent = CARD_META[id].name;
    guessSelect.appendChild(option);
  });
}

function renderLog() {
  logEl.innerHTML = "";
  const publicEntries =
    state?.public_log ??
    (state?.events ?? []).map((event) => `${event.kind}: ${JSON.stringify(event.data)}`);
  [...publicEntries].reverse().forEach((entry) => {
    const li = document.createElement("li");
    li.textContent = entry;
    logEl.appendChild(li);
  });
}

function renderMessages() {
  messagesEl.innerHTML = "";
  const privateEntries = [...(state?.private_log ?? [])].reverse();
  const allEntries = [...localMessages, ...privateEntries];
  allEntries.forEach((entry) => {
    const li = document.createElement("li");
    li.textContent = entry;
    messagesEl.appendChild(li);
  });
}

function renderTableStatus() {
  if (!state || !gameId) {
    setTableStatus("Create a table or join with a code.");
    return;
  }
  const me = state.players.find((player) => player.id === playerId);
  const parts = [
    `Table: ${gameId}`,
    `Join Code: ${state.join_code ?? "N/A"}`,
    `You: ${me?.name ?? "Unknown"}`,
  ];
  if (state.waiting_for_opponent) {
    parts.push("Waiting for second player.");
  }
  setTableStatus(parts.join(" | "));
}

function renderInvitePanel() {
  if (!state || playerId !== 0 || !state.join_code) {
    invitePanel.hidden = true;
    inviteCodeInput.value = "";
    return;
  }
  invitePanel.hidden = false;
  inviteCodeInput.value = state.join_code;
}

function renderCardPreview() {
  const selectedCardId = getSelectedCardId();
  const cardId = previewCardId ?? selectedCardId;
  if (!cardId || hidden) {
    cardPreviewEl.hidden = true;
    return;
  }
  cardPreviewEl.hidden = false;
  cardPreviewImageEl.src = cardPath(cardId);
  cardPreviewNameEl.textContent = CARD_META[cardId]?.name ?? cardId;
  cardPreviewHintEl.textContent = CARD_META[cardId]?.hint ?? "";
}

function renderActionTray() {
  const selectedCardId = getSelectedCardId();
  if (!state || !selectedCardId) {
    actionTrayEl.hidden = true;
    targetPickerEl.hidden = true;
    return;
  }

  const meta = CARD_META[selectedCardId] ?? {};
  actionTrayEl.hidden = false;
  actionSummaryEl.textContent = `Selected: ${meta.name}. ${meta.hint ?? ""}`;
  btnPlayContext.textContent = `Play ${meta.name}`;

  if (!meta.needsTarget) {
    targetPickerEl.hidden = true;
    return;
  }

  const options = getTargetOptions(selectedCardId);
  const selectableTargetIds = options.filter((item) => item.selectable).map((item) => item.player.id);
  if (selectedTarget !== null && !selectableTargetIds.includes(selectedTarget)) {
    selectedTarget = null;
  }

  targetPickerEl.hidden = false;
  targetPickerEl.innerHTML = "";
  options.forEach(({ player, selectable, reason }) => {
    const option = document.createElement("button");
    option.type = "button";
    option.className = "target-option";
    if (selectedTarget === player.id) {
      option.classList.add("selected");
    }
    option.disabled = !selectable;
    option.innerHTML = `<span class="name">${player.name}</span><span class="reason">${reason}</span>`;
    option.addEventListener("click", () => {
      selectedTarget = player.id;
      render();
    });
    targetPickerEl.appendChild(option);
  });

  if (selectableTargetIds.length === 0) {
    const note = document.createElement("p");
    note.className = "preview-hint";
    note.textContent = "No valid targets now. You can still play this card.";
    targetPickerEl.appendChild(note);
  }
}

function render() {
  renderSelectors();
  renderHand();
  renderCardPreview();
  renderActionTray();
  renderPlayers();
  renderPiles();
  renderLog();
  renderMessages();
  renderTableStatus();
  renderInvitePanel();

  if (!state) {
    setStatus("Create or join a table.");
  } else if (state.waiting_for_opponent) {
    setStatus("Waiting for Player 2.");
  } else if (state.game_over) {
    setStatus("Game Over");
  } else if (state.round_over) {
    setStatus("Round Over");
  } else {
    setStatus("In Play");
  }
  updateControls();
}

async function fetchState() {
  if (!gameId || !seatToken) {
    state = null;
    stateSignature = "";
    playerId = null;
    render();
    return;
  }
  const requestId = fetchSeq + 1;
  fetchSeq = requestId;
  const response = await fetch(`/api/multi/state?game_id=${encodeURIComponent(gameId)}`, {
    headers: authHeaders(false),
  });
  if (!response.ok) {
    const detail = await readError(response, "Failed to fetch state.");
    addMessage(detail);
    if (response.status === 401 || response.status === 404) {
      gameId = null;
      seatToken = null;
      persistSession();
      state = null;
      playerId = null;
      setTableStatus("Session expired. Create or join again.");
      render();
    }
    return;
  }
  const nextState = await response.json();
  if (requestId !== fetchSeq) {
    return;
  }
  const nextSignature = JSON.stringify(nextState);
  if (nextSignature === stateSignature) {
    return;
  }
  state = nextState;
  stateSignature = nextSignature;
  playerId = state.viewer_id;
  render();
}

async function createTable() {
  const name = nameInput.value.trim() || "Player 1";
  setBusy(true);
  try {
    const response = await fetch("/api/multi/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) {
      const detail = await readError(response, "Create table failed.");
      addMessage(detail);
      setTableStatus(`Create failed: ${detail}`);
      return;
    }
    const payload = await response.json();
    gameId = payload.game_id;
    seatToken = payload.seat_token;
    state = payload.state;
    stateSignature = JSON.stringify(state);
    playerId = state.viewer_id;
    selectedIndex = null;
    selectedTarget = null;
    previewCardId = null;
    joinCodeInput.value = payload.join_code;
    persistSession();
    setTableStatus(`Created table ${gameId}. Share join code ${payload.join_code}.`);
    render();
  } finally {
    setBusy(false);
  }
}

async function joinTable() {
  const joinCode = normalizeJoinCode(joinCodeInput.value);
  joinCodeInput.value = joinCode;
  if (!joinCode) {
    addMessage("Enter a join code.");
    setTableStatus("Join failed: enter a 6-character code from host.");
    return;
  }
  if (joinCode.length !== 6) {
    addMessage("Join code must be 6 characters.");
    setTableStatus("Join failed: code must be 6 characters.");
    return;
  }
  const name = nameInput.value.trim() || "Player 2";
  setBusy(true);
  try {
    const response = await fetch("/api/multi/join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ join_code: joinCode, name }),
    });
    if (!response.ok) {
      const detail = await readError(response, "Join table failed.");
      addMessage(detail);
      setTableStatus(`Join failed: ${detail}`);
      return;
    }
    const payload = await response.json();
    gameId = payload.game_id;
    seatToken = payload.seat_token;
    state = payload.state;
    stateSignature = JSON.stringify(state);
    playerId = state.viewer_id;
    selectedIndex = null;
    selectedTarget = null;
    previewCardId = null;
    persistSession();
    setTableStatus(`Joined table ${gameId} with code ${payload.join_code}.`);
    render();
  } finally {
    setBusy(false);
  }
}

function leaveTable() {
  gameId = null;
  seatToken = null;
  state = null;
  stateSignature = "";
  playerId = null;
  selectedIndex = null;
  selectedTarget = null;
  previewCardId = null;
  localMessages = [];
  persistSession();
  setTableStatus("Disconnected from table.");
  render();
}

async function startTurn() {
  if (busy || !gameId) {
    return;
  }
  setBusy(true);
  try {
    const response = await fetch("/api/multi/start", {
      method: "POST",
      headers: authHeaders(true),
      body: JSON.stringify({ game_id: gameId }),
    });
    if (!response.ok) {
      addMessage(await readError(response, "Start turn failed."));
      return;
    }
    state = await response.json();
    stateSignature = JSON.stringify(state);
    playerId = state.viewer_id;
    render();
  } finally {
    setBusy(false);
  }
}

async function playSelected() {
  if (busy || !gameId) {
    return;
  }
  const hand = getMyHand();
  if (selectedIndex === null || !hand[selectedIndex]) {
    addMessage("Select a card first.");
    return;
  }
  const cardId = hand[selectedIndex];
  const meta = CARD_META[cardId] ?? {};
  const targetOptions = getTargetOptions(cardId);
  const selectableTargetIds = targetOptions.filter((item) => item.selectable).map((item) => item.player.id);
  const target = selectedTarget;
  if (meta.needsTarget && selectableTargetIds.length > 0 && (target === null || !selectableTargetIds.includes(target))) {
    addMessage("Select a target.");
    return;
  }
  const payload = {
    game_id: gameId,
    card: cardId,
    target_id: meta.needsTarget ? target : null,
    guess: meta.needsGuess ? guessSelect.value : null,
  };

  setBusy(true);
  try {
    const response = await fetch("/api/multi/play", {
      method: "POST",
      headers: authHeaders(true),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      addMessage(await readError(response, "Play failed."));
      return;
    }
    state = await response.json();
    stateSignature = JSON.stringify(state);
    playerId = state.viewer_id;
    selectedIndex = null;
    selectedTarget = null;
    previewCardId = null;
    render();
  } finally {
    setBusy(false);
  }
}

async function nextRound() {
  if (busy || !gameId) {
    return;
  }
  setBusy(true);
  try {
    const response = await fetch("/api/multi/next_round", {
      method: "POST",
      headers: authHeaders(true),
      body: JSON.stringify({ game_id: gameId }),
    });
    if (!response.ok) {
      addMessage(await readError(response, "Next round failed."));
      return;
    }
    state = await response.json();
    stateSignature = JSON.stringify(state);
    playerId = state.viewer_id;
    render();
  } finally {
    setBusy(false);
  }
}

btnStart.addEventListener("click", startTurn);
btnPlayContext.addEventListener("click", playSelected);
btnNextRound.addEventListener("click", nextRound);
btnCreateTable.addEventListener("click", createTable);
btnJoinTable.addEventListener("click", joinTable);
btnLeaveTable.addEventListener("click", leaveTable);
btnCopyCode.addEventListener("click", () => {
  if (!state?.join_code) return;
  copyText(state.join_code, "Join code copied.");
});
btnCopyLink.addEventListener("click", () => {
  if (!state?.join_code) return;
  copyText(getInviteLink(state.join_code), "Invite link copied.");
});

btnHide.addEventListener("click", () => {
  hidden = !hidden;
  btnHide.textContent = hidden ? "Show Hand" : "Hide Hand";
  render();
});
btnCancelSelect.addEventListener("click", () => {
  selectedIndex = null;
  selectedTarget = null;
  previewCardId = null;
  render();
});

joinCodeInput.addEventListener("input", () => {
  joinCodeInput.value = normalizeJoinCode(joinCodeInput.value);
});
joinCodeInput.addEventListener("focus", () => {
  joinCodeInput.select();
});
inviteCodeInput.addEventListener("focus", () => {
  inviteCodeInput.select();
});

discardZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  discardZone.classList.add("dragover");
});

discardZone.addEventListener("drop", (event) => {
  event.preventDefault();
  discardZone.classList.remove("dragover");
  const index = Number(event.dataTransfer.getData("text/plain"));
  if (!Number.isNaN(index)) {
    selectedIndex = index;
    playSelected();
  }
});

discardZone.addEventListener("dragleave", () => {
  discardZone.classList.remove("dragover");
});

renderGallery();
const codeFromUrl = new URLSearchParams(window.location.search).get("code");
if (codeFromUrl) {
  joinCodeInput.value = normalizeJoinCode(codeFromUrl);
}
restoreSession();
render();
if (gameId && seatToken) {
  fetchState();
}

setInterval(() => {
  if (!busy && gameId && seatToken) {
    fetchState();
  }
}, 1200);

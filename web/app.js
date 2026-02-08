const CARD_META = {
  guard: { name: "Guard", needsTarget: true, needsGuess: true },
  priest: { name: "Priest", needsTarget: true },
  baron: { name: "Baron", needsTarget: true },
  handmaid: { name: "Handmaid" },
  prince: { name: "Prince", needsTarget: true, canSelf: true },
  king: { name: "King", needsTarget: true },
  countess: { name: "Countess" },
  princess: { name: "Princess" },
};

const UNIQUE_CARDS = Object.keys(CARD_META).map((id) => ({ id, name: CARD_META[id].name }));
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

const cardPath = (id) => `../assets/cards/${id}.png`;

const handEl = document.querySelector("#hand");
const logEl = document.querySelector("#log");
const messagesEl = document.querySelector("#messages");
const galleryEl = document.querySelector("#gallery");
const playersEl = document.querySelector("#players");
const statusEl = document.querySelector("#status");

const deckCountEl = document.querySelector("#deck-count");
const burnedCountEl = document.querySelector("#burned-count");
const faceUpEl = document.querySelector("#face-up-cards");

const btnStart = document.querySelector("#btn-start");
const btnPlay = document.querySelector("#btn-play");
const btnHide = document.querySelector("#btn-hide");
const btnNextRound = document.querySelector("#btn-next-round");

const playerSelect = document.querySelector("#player-select");
const targetSelect = document.querySelector("#target-select");
const guessSelect = document.querySelector("#guess-select");

const discardZone = document.querySelector("#discard-zone");

let state = null;
let selectedIndex = null;
let selectedTarget = null;
let hidden = false;
let playerId = 0;
let busy = false;
let fetchSeq = 0;
let localMessages = [];

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

function updateControls() {
  if (!state) return;
  const me = state.players.find((player) => player.id === playerId);
  const isMyTurn = state.current_player_id === playerId;

  const handCount = me?.hand_count ?? 0;
  btnStart.disabled = busy || state.game_over || state.round_over || !isMyTurn || handCount !== 1;
  btnPlay.disabled = busy || state.game_over || state.round_over || !isMyTurn || handCount !== 2;
  btnNextRound.disabled = busy || state.game_over || !state.round_over;
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
    render();
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

function getValidTargets(cardId) {
  if (!state) return [];
  const valid = [];
  for (const player of state.players) {
    if (player.eliminated) continue;
    if (cardId === "guard" || cardId === "priest" || cardId === "baron" || cardId === "king") {
      if (player.id === playerId) continue;
      if (player.protected) continue;
      valid.push(player);
      continue;
    }
    if (cardId === "prince") {
      if (player.id === playerId) {
        valid.push(player);
        continue;
      }
      if (player.protected) continue;
      valid.push(player);
    }
  }
  return valid;
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
    card.addEventListener("click", () => {
      selectedTarget = player.id;
      targetSelect.value = String(player.id);
      renderPlayers();
    });
    playersEl.appendChild(card);
  });
}

function renderPiles() {
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
  playerSelect.innerHTML = "";
  state.players.forEach((player) => {
    const option = document.createElement("option");
    option.value = player.id;
    option.textContent = player.name;
    if (player.id === playerId) {
      option.selected = true;
    }
    playerSelect.appendChild(option);
  });

  targetSelect.innerHTML = "";
  const noneOption = document.createElement("option");
  noneOption.value = "";
  noneOption.textContent = "None";
  targetSelect.appendChild(noneOption);
  const selectedCardId = getSelectedCardId();
  const targets = selectedCardId ? getValidTargets(selectedCardId) : state.players;
  targets.forEach((player) => {
    const option = document.createElement("option");
    option.value = player.id;
    option.textContent = player.name;
    if (player.id === selectedTarget) {
      option.selected = true;
    }
    targetSelect.appendChild(option);
  });

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
    state.public_log ??
    (state.events ?? []).map((event) => `${event.kind}: ${JSON.stringify(event.data)}`);
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

function render() {
  if (!state) return;
  if (selectedIndex !== null && !getSelectedCardId()) {
    selectedIndex = null;
  }
  renderSelectors();
  renderPlayers();
  renderHand();
  renderPiles();
  renderLog();
  renderMessages();
  setStatus(state.game_over ? "Game Over" : state.round_over ? "Round Over" : "In Play");
  updateControls();
}

async function fetchState() {
  const requestId = fetchSeq + 1;
  fetchSeq = requestId;
  const response = await fetch(`/api/state?player_id=${playerId}`);
  if (!response.ok) {
    addMessage("Server not available. Start the FastAPI server.");
    return;
  }
  const nextState = await response.json();
  if (requestId !== fetchSeq) {
    return;
  }
  state = nextState;
  if (!state.players.find((player) => player.id === playerId)) {
    playerId = state.players[0]?.id ?? 0;
  }
  render();
}

async function startTurn() {
  if (busy) {
    return;
  }
  setBusy(true);
  try {
    const response = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: playerId }),
    });
    if (!response.ok) {
      const error = await response.json();
      addMessage(error.detail || "Start turn failed.");
      return;
    }
    state = await response.json();
    render();
  } finally {
    setBusy(false);
  }
}

async function playSelected() {
  if (busy) {
    return;
  }
  const hand = getMyHand();
  if (selectedIndex === null || !hand[selectedIndex]) {
    addMessage("Select a card first.");
    return;
  }
  const cardId = hand[selectedIndex];
  const meta = CARD_META[cardId] ?? {};
  const targets = getValidTargets(cardId);
  const target = targetSelect.value ? Number(targetSelect.value) : null;
  if (meta.needsTarget && targets.length > 0 && target === null) {
    addMessage("Select a target.");
    return;
  }
  const payload = {
    player_id: playerId,
    card: cardId,
    target_id: meta.needsTarget ? target : null,
    guess: meta.needsGuess ? guessSelect.value : null,
  };
  setBusy(true);
  try {
    const response = await fetch("/api/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json();
      addMessage(error.detail || "Play failed.");
      return;
    }
    state = await response.json();
    selectedIndex = null;
    render();
  } finally {
    setBusy(false);
  }
}

async function nextRound() {
  if (busy) {
    return;
  }
  setBusy(true);
  try {
    const response = await fetch("/api/next_round", { method: "POST" });
    if (!response.ok) {
      const error = await response.json();
      addMessage(error.detail || "Next round failed.");
      return;
    }
    state = await response.json();
    render();
  } finally {
    setBusy(false);
  }
}

btnStart.addEventListener("click", startTurn);
btnPlay.addEventListener("click", playSelected);
btnNextRound.addEventListener("click", nextRound);
btnHide.addEventListener("click", () => {
  hidden = !hidden;
  btnHide.textContent = hidden ? "Show Hand" : "Hide Hand";
  render();
});

playerSelect.addEventListener("change", () => {
  playerId = Number(playerSelect.value);
  selectedIndex = null;
  selectedTarget = null;
  fetchState();
});

targetSelect.addEventListener("change", () => {
  selectedTarget = targetSelect.value ? Number(targetSelect.value) : null;
  renderPlayers();
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
fetchState();

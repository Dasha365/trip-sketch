const API_BASE_URL = "http://10.93.26.16:8000";
const tripForm = document.getElementById("trip-form");
const generateButton = document.getElementById("generate-button");
const refreshHistoryButton = document.getElementById("refresh-history-button");
const messageBox = document.getElementById("message-box");
const historyStatus = document.getElementById("history-status");
const tripHistory = document.getElementById("trip-history");
const tripDetailContent = document.getElementById("trip-detail-content");

let selectedTripId = null;
let isGenerating = false;
let isRegenerating = false;

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function showMessage(message, type) {
    messageBox.textContent = message;
    messageBox.className = `message-box ${type}`;
}

function hideMessage() {
    messageBox.textContent = "";
    messageBox.className = "message-box hidden";
}

function formatCreatedAt(value) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return date.toLocaleString();
}

function setButtonsDisabled(disabled) {
    generateButton.disabled = disabled;

    const regenerateButton = document.getElementById("regenerate-button");
    if (regenerateButton) {
        regenerateButton.disabled = disabled;
    }
}

function renderHistory(trips) {
    if (!Array.isArray(trips) || trips.length === 0) {
        tripHistory.innerHTML = "";
        historyStatus.textContent = "No saved trips yet.";
        return;
    }

    historyStatus.textContent = `${trips.length} saved trip${trips.length === 1 ? "" : "s"}.`;

    tripHistory.innerHTML = trips
        .map(
            (trip) => `
                <button
                    type="button"
                    class="history-item ${trip.id === selectedTripId ? "active" : ""}"
                    data-trip-id="${trip.id}"
                >
                    <h3>${escapeHtml(trip.title)}</h3>
                    <p><strong>Destination:</strong> ${escapeHtml(trip.destination)}</p>
                    <p><strong>Created:</strong> ${escapeHtml(formatCreatedAt(trip.created_at))}</p>
                </button>
            `
        )
        .join("");

    const historyButtons = tripHistory.querySelectorAll("[data-trip-id]");

    historyButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const tripId = Number(button.dataset.tripId);
            loadTripDetail(tripId);
        });
    });
}

function renderTripDetail(trip) {
    selectedTripId = trip.id;

    const daysHtml = Array.isArray(trip.days)
        ? trip.days
              .map(
                  (day) => `
                      <article class="day-card">
                          <h3>Day ${escapeHtml(day.day)}</h3>
                          <p>${escapeHtml(day.plan).replace(/\n/g, "<br>")}</p>
                      </article>
                  `
              )
              .join("")
        : "";

    tripDetailContent.innerHTML = `
        <div class="detail-header">
            <div>
                <h2>${escapeHtml(trip.title)}</h2>
                <p>${escapeHtml(trip.summary)}</p>
            </div>
            <button id="regenerate-button" type="button" class="primary-button">
                Regenerate Trip
            </button>
        </div>

        <div class="detail-meta">
            <div class="meta-pill">${escapeHtml(trip.destination)}</div>
            <div class="meta-pill">${escapeHtml(trip.number_of_days)} day${trip.number_of_days === 1 ? "" : "s"}</div>
            <div class="meta-pill">${escapeHtml(trip.budget)}</div>
            <div class="meta-pill">${escapeHtml(trip.interests)}</div>
            <div class="meta-pill">${escapeHtml(trip.travel_style)}</div>
            <div class="meta-pill">${escapeHtml(formatCreatedAt(trip.created_at))}</div>
        </div>

        <section>
            <h3>Daily Plan</h3>
            ${daysHtml || "<p>No day plan could be loaded for this trip.</p>"}
        </section>

        <section class="notes-box">
            <h3>Notes</h3>
            <p>${escapeHtml(trip.notes).replace(/\n/g, "<br>")}</p>
        </section>
    `;

    const regenerateButton = document.getElementById("regenerate-button");
    regenerateButton.disabled = isGenerating || isRegenerating;
    regenerateButton.addEventListener("click", () => {
        regenerateTrip(trip.id);
    });
}

function renderDetailLoading(message) {
    tripDetailContent.innerHTML = `
        <div class="empty-state">
            <h2>Trip Details</h2>
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}

function renderDetailError(message) {
    tripDetailContent.innerHTML = `
        <div class="empty-state">
            <h2>Trip Details</h2>
            <p class="error-text">${escapeHtml(message)}</p>
        </div>
    `;
}

async function parseResponse(response) {
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        const errorMessage = data.detail || "The request could not be completed.";
        throw new Error(errorMessage);
    }

    return data;
}

async function fetchTripHistory() {
    historyStatus.textContent = "Loading trip history...";

    const response = await fetch(`${API_BASE_URL}/trips`);
    const trips = await parseResponse(response);
    renderHistory(trips);

    return trips;
}

async function loadTripDetail(tripId) {
    renderDetailLoading("Loading trip details...");

    try {
        const response = await fetch(`${API_BASE_URL}/trips/${tripId}`);
        const trip = await parseResponse(response);
        renderTripDetail(trip);
        await refreshHistory();
    } catch (error) {
        renderDetailError(error.message || "Could not load this trip.");
        showMessage(error.message || "Could not load this trip.", "error");
    }
}

async function refreshHistory() {
    try {
        return await fetchTripHistory();
    } catch (error) {
        tripHistory.innerHTML = "";
        historyStatus.textContent = "Could not load trip history.";
        showMessage(error.message || "Could not load trip history.", "error");
        return [];
    }
}

async function generateTrip(event) {
    event.preventDefault();

    hideMessage();
    isGenerating = true;
    setButtonsDisabled(true);
    renderDetailLoading("Generating your trip plan...");

    const formData = new FormData(tripForm);
    const tripData = {
        destination: formData.get("destination"),
        number_of_days: Number(formData.get("number_of_days")),
        budget: formData.get("budget"),
        interests: formData.get("interests"),
        travel_style: formData.get("travel_style"),
    };

    try {
        const response = await fetch(`${API_BASE_URL}/generate-trip`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(tripData),
        });

        await parseResponse(response);
        showMessage("Trip generated and saved successfully.", "success");

        const trips = await refreshHistory();
        if (trips.length > 0) {
            await loadTripDetail(trips[0].id);
        }
    } catch (error) {
        renderDetailError(error.message || "Could not generate the trip.");
        showMessage(error.message || "Could not generate the trip.", "error");
    } finally {
        isGenerating = false;
        setButtonsDisabled(false);
    }
}

async function regenerateTrip(tripId) {
    hideMessage();
    isRegenerating = true;
    setButtonsDisabled(true);
    renderDetailLoading("Regenerating this trip...");

    try {
        const response = await fetch(`${API_BASE_URL}/trips/${tripId}/regenerate`, {
            method: "POST",
        });

        await parseResponse(response);
        showMessage("A new trip version was generated and saved.", "success");

        const trips = await refreshHistory();
        if (trips.length > 0) {
            await loadTripDetail(trips[0].id);
        }
    } catch (error) {
        renderDetailError(error.message || "Could not regenerate the trip.");
        showMessage(error.message || "Could not regenerate the trip.", "error");
    } finally {
        isRegenerating = false;
        setButtonsDisabled(false);
    }
}

tripForm.addEventListener("submit", generateTrip);
refreshHistoryButton.addEventListener("click", async () => {
    hideMessage();
    await refreshHistory();
});

refreshHistory();

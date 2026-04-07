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

function createMetaPill(label, value) {
    return `
        <div class="meta-pill">
            <span class="meta-pill-label">${escapeHtml(label)}</span>
            <span>${escapeHtml(value)}</span>
        </div>
    `;
}

function splitPlanIntoSegments(plan) {
    const text = String(plan ?? "").trim();

    if (!text) {
        return [];
    }

    const normalizedText = text.replace(/\r\n/g, "\n");
    const sectionPattern = /(Morning|Afternoon|Evening)\s*:\s*/gi;
    const matches = [...normalizedText.matchAll(sectionPattern)];

    if (matches.length === 0) {
        return [];
    }

    const sections = matches
        .map((match, index) => {
            const label = match[1];
            const contentStart = match.index + match[0].length;
            const contentEnd = index + 1 < matches.length ? matches[index + 1].index : normalizedText.length;
            const content = normalizedText.slice(contentStart, contentEnd).trim();

            if (!content) {
                return null;
            }

            return {
                label: label.charAt(0).toUpperCase() + label.slice(1).toLowerCase(),
                content,
            };
        })
        .filter(Boolean);

    const uniqueLabels = new Set(sections.map((section) => section.label));
    const hasStructuredSections = sections.length > 0 && uniqueLabels.size === sections.length;

    return hasStructuredSections ? sections : [];
}

function renderDayCards(days) {
    if (!Array.isArray(days) || days.length === 0) {
        return `
            <div class="empty-state">
                <div class="empty-illustration">
                    <span class="empty-illustration-core">TS</span>
                </div>
                <h3>No daily plan yet</h3>
                <p>This trip was saved without a detailed itinerary, so there are no day cards to show right now.</p>
            </div>
        `;
    }

    return `
        <div class="timeline">
            ${days
                .map((day) => {
                    const sections = splitPlanIntoSegments(day.plan);
                    const sectionMarkup = sections
                        .map(
                            (section) => `
                                <div class="plan-block">
                                    <strong>${escapeHtml(section.label)}</strong>
                                    <p>${escapeHtml(section.content).replace(/\n/g, "<br>")}</p>
                                </div>
                            `
                        )
                        .join("");

                    const fallbackMarkup = !sectionMarkup
                        ? `
                            <div class="plan-block">
                                <strong>Day Plan</strong>
                                <p>${escapeHtml(day.plan || "No details available.").replace(/\n/g, "<br>")}</p>
                            </div>
                        `
                        : sectionMarkup;

                    return `
                        <article class="day-card">
                            <div class="day-card-header">
                                <div class="day-badge">Day ${escapeHtml(day.day)}</div>
                                <div>
                                    <h3 class="day-card-title">Day ${escapeHtml(day.day)}</h3>
                                    <p class="day-card-subtitle">A structured view of the itinerary for this day.</p>
                                </div>
                            </div>
                            <div class="day-sections">
                                ${fallbackMarkup}
                            </div>
                        </article>
                    `;
                })
                .join("")}
        </div>
    `;
}

function renderHistory(trips) {
    if (!Array.isArray(trips) || trips.length === 0) {
        tripHistory.innerHTML = `
            <div class="empty-state">
                <div class="empty-illustration">
                    <span class="empty-illustration-core">TS</span>
                </div>
                <h3>No saved trips yet</h3>
                <p>Your generated itineraries will appear here so you can revisit and compare every version.</p>
            </div>
        `;
        historyStatus.textContent = "History is empty for now.";
        return;
    }

    historyStatus.textContent = `${trips.length} saved trip${trips.length === 1 ? "" : "s"} ready to revisit.`;

    tripHistory.innerHTML = trips
        .map(
            (trip, index) => `
                <button
                    type="button"
                    class="history-item ${trip.id === selectedTripId ? "active" : ""}"
                    data-trip-id="${trip.id}"
                >
                    <div class="history-item-header">
                        <div>
                            <h3>${escapeHtml(trip.title)}</h3>
                            <p class="history-destination">${escapeHtml(trip.destination)}</p>
                        </div>
                        <span class="history-chip">${index === 0 ? "Latest" : "Saved"}</span>
                    </div>
                    <p class="history-created">Created ${escapeHtml(formatCreatedAt(trip.created_at))}</p>
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

    const detailMeta = [
        createMetaPill("Destination", trip.destination),
        createMetaPill("Duration", `${trip.number_of_days} day${trip.number_of_days === 1 ? "" : "s"}`),
        createMetaPill("Budget", trip.budget),
        createMetaPill("Interests", trip.interests),
        createMetaPill("Style", trip.travel_style),
    ].join("");

    const notesText = escapeHtml(trip.notes || "No additional notes were saved for this itinerary.").replace(/\n/g, "<br>");

    tripDetailContent.innerHTML = `
        <div class="detail-shell">
            <section class="detail-hero">
                <div class="detail-headline">
                    <div>
                        <span class="detail-kicker">Saved Itinerary</span>
                        <h3 class="detail-title">${escapeHtml(trip.title)}</h3>
                        <p class="detail-summary">${escapeHtml(trip.summary || "No summary was provided for this trip.")}</p>
                    </div>
                    <div class="detail-timestamp">${escapeHtml(formatCreatedAt(trip.created_at))}</div>
                </div>

                <div class="detail-meta">
                    ${detailMeta}
                </div>
            </section>

            <section>
                <h3 class="detail-section-title">
                    <span class="section-symbol">*</span>
                    Daily Plan
                </h3>
                ${renderDayCards(trip.days)}
            </section>

            <section class="notes-box">
                <h3>Notes</h3>
                <p>${notesText}</p>
            </section>

            <section class="regeneration-box">
                <h3>Refine This Trip</h3>
                <p>Leave optional instructions to generate a fresh saved version without overwriting the current itinerary.</p>
                <textarea
                    id="regeneration-instruction"
                    rows="5"
                    placeholder="Make it cheaper&#10;Add more rest time&#10;Focus more on local food&#10;Replace tourist spots with quieter places"
                ></textarea>
                <div class="regeneration-actions">
                    <span class="regeneration-tip">Short prompts work well: budget changes, pacing, food focus, or quieter alternatives.</span>
                    <button id="regenerate-button" type="button" class="primary-button">
                        Regenerate Trip
                    </button>
                </div>
            </section>
        </div>
    `;

    const regenerateButton = document.getElementById("regenerate-button");
    regenerateButton.disabled = isGenerating || isRegenerating;
    regenerateButton.addEventListener("click", () => {
        regenerateTrip(trip.id);
    });
}

function renderDetailLoading(message) {
    tripDetailContent.innerHTML = `
        <div class="detail-loading">
            <div class="loading-card">
                <div class="shimmer shimmer-line short"></div>
                <div class="shimmer shimmer-hero"></div>
                <div class="shimmer shimmer-line long"></div>
                <div class="shimmer shimmer-line medium"></div>
                <div class="shimmer shimmer-line long"></div>
                <p>${escapeHtml(message)}</p>
            </div>
        </div>
    `;
}

function renderDetailError(message) {
    tripDetailContent.innerHTML = `
        <div class="empty-state">
            <div class="empty-illustration">
                <span class="empty-illustration-core">TS</span>
            </div>
            <h3>Unable to load this trip</h3>
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
        tripHistory.innerHTML = `
            <div class="empty-state">
                <div class="empty-illustration">
                    <span class="empty-illustration-core">TS</span>
                </div>
                <h3>History is unavailable</h3>
                <p>We could not load the saved trips right now. Try refreshing again in a moment.</p>
            </div>
        `;
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
        additional_preferences: formData.get("additional_preferences")?.trim() || null,
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

    const regenerationInstructionField = document.getElementById("regeneration-instruction");
    const regenerationInstruction = regenerationInstructionField
        ? regenerationInstructionField.value.trim()
        : "";

    try {
        const response = await fetch(`${API_BASE_URL}/trips/${tripId}/regenerate`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                regeneration_instruction: regenerationInstruction || null,
            }),
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

const tripForm = document.getElementById("trip-form");
const resultSection = document.getElementById("result");
const resultContent = document.getElementById("result-content");
const API_BASE_URL = "http://10.93.26.16:8000";

function renderTripPlan(trip) {
    const daysHtml = trip.days
        .map(
            (day) => `
                <div class="day-card">
                    <h3>Day ${day.day}</h3>
                    <p>${day.plan}</p>
                </div>
            `
        )
        .join("");

    resultContent.innerHTML = `
        <h3>${trip.title}</h3>
        <p>${trip.summary}</p>
        <div>${daysHtml}</div>
        <h3>Notes</h3>
        <p>${trip.notes}</p>
    `;

    resultSection.classList.remove("hidden");
}

function renderError(message) {
    resultContent.innerHTML = `<p class="error">${message}</p>`;
    resultSection.classList.remove("hidden");
}

tripForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    resultContent.innerHTML = "<p>Generating your trip plan...</p>";
    resultSection.classList.remove("hidden");

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

        const data = await response.json();

        if (!response.ok) {
            const errorMessage = data.detail || "Something went wrong while generating the trip.";
            throw new Error(errorMessage);
        }

        renderTripPlan(data);
    } catch (error) {
        renderError(error.message || "Could not connect to the backend.");
    }
});

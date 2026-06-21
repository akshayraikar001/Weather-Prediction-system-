const liveCitySelect = document.getElementById("live-city");
const manualCitySelect = document.getElementById("city");
const form = document.getElementById("prediction-form");
const result = document.getElementById("result");
const observationDateInput = document.getElementById("observation_date");
const detailsPanel = document.getElementById("details-panel");
const toggleDetailsButton = document.getElementById("toggle-details");
const predictLiveButton = document.getElementById("predict-live");
const liveStats = document.getElementById("live-stats");
const liveCityTitle = document.getElementById("live-city-title");
const forecastCards = document.getElementById("forecast-cards");
const detailOverview = document.getElementById("detail-overview");
const detailFormView = document.getElementById("detail-form-view");
const openManualInlineButton = document.getElementById("open-manual-inline");
const closeManualButton = document.getElementById("close-manual");
const overviewCity = document.getElementById("overview-city");
const overviewDate = document.getElementById("overview-date");
const overviewInputs = document.getElementById("overview-inputs");

let supportedCities = [];
let currentCity = "Pune";
let currentSnapshot = null;
let map = null;
let heatLayer = null;
let cityMarker = null;

function weatherLabelFromCode(code) {
  const mapping = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    80: "Rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
  };
  return mapping[code] || "Changing conditions";
}

function weatherGlyphFromCode(code) {
  if (code === 0) return "Sun";
  if ([1, 2].includes(code)) return "Cloud-Sun";
  if (code === 3) return "Cloud";
  if ([45, 48].includes(code)) return "Mist";
  if ([51, 53, 55].includes(code)) return "Drizzle";
  if ([61, 63, 65, 80].includes(code)) return "Rain";
  if ([71, 73, 75].includes(code)) return "Snow";
  if ([95, 96, 99].includes(code)) return "Storm";
  return "Sky";
}

function setManualMode(isOpen) {
  detailOverview.classList.toggle("hidden", isOpen);
  detailFormView.classList.toggle("hidden", !isOpen);
  detailsPanel.classList.toggle("manual-open", isOpen);
  toggleDetailsButton.textContent = isOpen ? "Hide Detailed Prediction" : "Detailed Prediction";
}

function fillCitySelect(selectElement) {
  selectElement.innerHTML = "";
  supportedCities.forEach((city) => {
    const option = document.createElement("option");
    option.value = city;
    option.textContent = city;
    selectElement.appendChild(option);
  });
}

function colorForTemperature(value) {
  if (value >= 35) return "#d94801";
  if (value >= 30) return "#f16913";
  if (value >= 25) return "#fd8d3c";
  if (value >= 20) return "#feb24c";
  if (value >= 15) return "#fed976";
  return "#c7e9f1";
}

function radiusForTemperature(value) {
  return Math.max(12000, value * 650);
}

function renderMap(snapshot) {
  const center = [snapshot.latitude, snapshot.longitude];

  if (!map) {
    map = L.map("map", {
      zoomControl: false,
      scrollWheelZoom: false,
    }).setView(center, 10);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    L.control.zoom({ position: "bottomright" }).addTo(map);
  } else {
    map.setView(center, 10);
  }

  if (heatLayer) {
    heatLayer.remove();
  }

  if (cityMarker) {
    cityMarker.remove();
  }

  heatLayer = L.layerGroup(
    snapshot.heat_points.map((point) =>
      L.circle([point.latitude, point.longitude], {
        radius: radiusForTemperature(point.temperature_celsius),
        color: "transparent",
        fillColor: colorForTemperature(point.temperature_celsius),
        fillOpacity: 0.24,
      }).bindTooltip(`${point.temperature_celsius.toFixed(1)} C`)
    )
  ).addTo(map);

  cityMarker = L.marker(center)
    .addTo(map)
    .bindPopup(
      `<strong>${snapshot.city}</strong><br>${snapshot.state}<br>${snapshot.current.temperature_celsius.toFixed(1)} C right now`
    )
    .openPopup();
}

function renderStats(snapshot) {
  const current = snapshot.current;
  const today = snapshot.today_summary;

  liveCityTitle.textContent = `${snapshot.city}, ${snapshot.state}`;
  liveStats.innerHTML = `
    <article class="stat-card stat-main">
      <p class="stat-kicker">Current temperature</p>
      <h3>${current.temperature_celsius.toFixed(1)} C</h3>
      <p>${weatherLabelFromCode(current.weather_code)}</p>
    </article>
    <article class="stat-card">
      <p class="stat-kicker">Humidity</p>
      <h3>${current.humidity.toFixed(0)}%</h3>
      <p>Pressure ${current.pressure_mb.toFixed(0)} mb</p>
    </article>
    <article class="stat-card">
      <p class="stat-kicker">Wind and cloud</p>
      <h3>${current.wind_speed_kph.toFixed(1)} kph</h3>
      <p>Cloud cover ${current.cloud_cover.toFixed(0)}%</p>
    </article>
    <article class="stat-card">
      <p class="stat-kicker">Today outlook</p>
      <h3>${today.precipitation_probability_max.toFixed(0)}%</h3>
      <p>${today.temperature_min_celsius.toFixed(1)} C to ${today.temperature_max_celsius.toFixed(1)} C</p>
    </article>
  `;
}

function renderForecast(snapshot) {
  forecastCards.innerHTML = snapshot.daily_forecast
    .map((day, index) => {
      const label = index === 0 ? "Today" : index === 1 ? "Tomorrow" : "Day 3";
      return `
        <article class="forecast-card">
          <p class="forecast-label">${label}</p>
          <div class="forecast-emoji">${weatherGlyphFromCode(day.weather_code)}</div>
          <h3>${weatherLabelFromCode(day.weather_code)}</h3>
          <p>${day.temperature_min_celsius.toFixed(1)} C to ${day.temperature_max_celsius.toFixed(1)} C</p>
          <p>Rain chance ${day.precipitation_probability_max.toFixed(0)}%</p>
          <p>Expected rain ${day.rain_sum_mm.toFixed(1)} mm</p>
        </article>
      `;
    })
    .join("");
}

function renderOverview(snapshot) {
  overviewCity.textContent = `${snapshot.city}, ${snapshot.state}`;
  overviewDate.textContent = `Observed on ${snapshot.observation_date}`;
  overviewInputs.innerHTML = [
    `Temp ${snapshot.current.temperature_celsius.toFixed(1)} C`,
    `Humidity ${snapshot.current.humidity.toFixed(0)}%`,
    `Pressure ${snapshot.current.pressure_mb.toFixed(0)} mb`,
    `Wind ${snapshot.current.wind_speed_kph.toFixed(1)} kph`,
    `Cloud ${snapshot.current.cloud_cover.toFixed(0)}%`,
    snapshot.current.rain_today ? "Rain today: Yes" : "Rain today: No",
  ]
    .map((item) => `<span class="input-pill">${item}</span>`)
    .join("");
}

function fillManualForm(snapshot) {
  currentSnapshot = snapshot;
  manualCitySelect.value = snapshot.city;
  observationDateInput.value = snapshot.observation_date;
  form.elements.temperature_celsius.value = snapshot.current.temperature_celsius.toFixed(1);
  form.elements.humidity.value = snapshot.current.humidity.toFixed(0);
  form.elements.pressure_mb.value = snapshot.current.pressure_mb.toFixed(1);
  form.elements.wind_speed_kph.value = snapshot.current.wind_speed_kph.toFixed(1);
  form.elements.cloud_cover.value = snapshot.current.cloud_cover.toFixed(0);
  form.elements.rain_today.value = String(snapshot.current.rain_today);
}

function renderPrediction(title, data, cityName) {
  result.classList.remove("hidden");
  result.innerHTML = `
    <h2>${title}</h2>
    <p>${cityName} on ${data.observation_date}</p>
    <p>Rain tomorrow: <strong>${data.rain_tomorrow}</strong></p>
    <p>Rain probability: <strong>${(data.rain_probability * 100).toFixed(1)}%</strong></p>
    <span class="pill">Confidence: ${(data.confidence_score * 100).toFixed(1)}%</span>
  `;
}

async function loadSnapshot(city) {
  result.classList.add("hidden");
  const response = await fetch(`/live/city/${encodeURIComponent(city)}`);
  if (!response.ok) {
    throw new Error("Unable to load live weather");
  }

  const snapshot = await response.json();
  currentCity = snapshot.city;
  currentSnapshot = snapshot;
  liveCitySelect.value = snapshot.city;
  manualCitySelect.value = snapshot.city;
  renderMap(snapshot);
  renderStats(snapshot);
  renderForecast(snapshot);
  renderOverview(snapshot);
  fillManualForm(snapshot);
}

async function loadMeta() {
  const response = await fetch("/meta");
  const data = await response.json();

  supportedCities = data.supported_cities;
  fillCitySelect(liveCitySelect);
  fillCitySelect(manualCitySelect);
  currentCity = data.default_city || "Pune";
  await loadSnapshot(currentCity);
}

function toPayload(formData) {
  return {
    city: formData.get("city"),
    observation_date: formData.get("observation_date") || null,
    temperature_celsius: Number(formData.get("temperature_celsius")),
    humidity: Number(formData.get("humidity")),
    pressure_mb: Number(formData.get("pressure_mb")),
    wind_speed_kph: Number(formData.get("wind_speed_kph")),
    cloud_cover: Number(formData.get("cloud_cover")),
    rain_today: Number(formData.get("rain_today")),
  };
}

liveCitySelect.addEventListener("change", async (event) => {
  await loadSnapshot(event.target.value);
});

manualCitySelect.addEventListener("change", async (event) => {
  liveCitySelect.value = event.target.value;
  await loadSnapshot(event.target.value);
});

predictLiveButton.addEventListener("click", async () => {
  const response = await fetch("/predict-live", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ city: currentCity }),
  });

  if (!response.ok) {
    result.classList.remove("hidden");
    result.innerHTML = "<h2>Prediction failed</h2><p>The live API could not provide prediction inputs just now.</p>";
    return;
  }

  const data = await response.json();
  renderPrediction("Tomorrow Prediction from Live API Data", data, currentCity);
});

toggleDetailsButton.addEventListener("click", () => {
  const nextState = detailFormView.classList.contains("hidden");
  setManualMode(nextState);
  detailsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
});

openManualInlineButton.addEventListener("click", () => {
  setManualMode(true);
  detailsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
});

closeManualButton.addEventListener("click", () => {
  setManualMode(false);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = toPayload(new FormData(form));

  const response = await fetch("/predict", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    result.classList.remove("hidden");
    result.innerHTML = "<h2>Prediction failed</h2><p>Please review your detailed inputs and try again.</p>";
    return;
  }

  const data = await response.json();
  renderPrediction("Tomorrow Prediction from Manual Inputs", data, payload.city);
});

loadMeta().catch(() => {
  result.classList.remove("hidden");
  result.innerHTML = "<h2>Live data unavailable</h2><p>The free weather API could not be reached just now. You can still use the detailed prediction form.</p>";
  setManualMode(true);
});

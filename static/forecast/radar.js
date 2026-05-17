(function () {
  const mapElement = document.querySelector("#radarMap");
  if (!mapElement) return;

  const toolbar = document.querySelector("#radarToolbar");
  const timeLabel = document.querySelector("#radarTime");
  const playButton = document.querySelector("#radarPlay");
  const previousButton = document.querySelector("#radarPrev");
  const nextButton = document.querySelector("#radarNext");
  const lat = Number(mapElement.dataset.lat);
  const lon = Number(mapElement.dataset.lon);
  const city = mapElement.dataset.city;
  const temp = mapElement.dataset.temp;
  const condition = mapElement.dataset.condition;

  let map;
  let frames = [];
  let frameIndex = 0;
  let radarLayer = null;
  let timer = null;

  function showFallback(message) {
    mapElement.classList.add("fallback-visible");
    const loading = mapElement.querySelector(".radar-loading");
    if (loading) {
      loading.innerHTML = `<strong>${message}</strong><span>Showing local fallback radar map.</span>`;
    }
  }

  function updateFrame(index) {
    if (!map || !frames.length) return;
    frameIndex = (index + frames.length) % frames.length;
    const frame = frames[frameIndex];
    const tileUrl = `${frame.host}${frame.path}/512/{z}/{x}/{y}/2/1_1.png`;

    if (radarLayer) {
      map.removeLayer(radarLayer);
    }

    radarLayer = L.tileLayer(tileUrl, {
      opacity: 0.72,
      tileSize: 512,
      zoomOffset: -1,
      maxZoom: 10,
      attribution: 'Radar by <a href="https://www.rainviewer.com/" target="_blank" rel="noreferrer">RainViewer</a>',
    }).addTo(map);

    const time = new Date(frame.time * 1000);
    timeLabel.textContent = `Radar frame: ${time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  }

  function togglePlay() {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
      playButton.textContent = "Play";
      return;
    }

    playButton.textContent = "Pause";
    timer = window.setInterval(() => updateFrame(frameIndex + 1), 900);
  }

  async function initRadar() {
    if (!window.L) {
      showFallback("Interactive radar library could not load.");
      return;
    }

    map = L.map(mapElement, {
      zoomControl: true,
      scrollWheelZoom: true,
    }).setView([lat, lon], 6);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    L.marker([lat, lon])
      .addTo(map)
      .bindPopup(`<strong>${city}</strong><br>${temp}&deg;C · ${condition}`)
      .openPopup();

    try {
      const response = await fetch("https://api.rainviewer.com/public/weather-maps.json", { cache: "no-store" });
      if (!response.ok) throw new Error("Radar response failed");
      const data = await response.json();
      const past = data.radar?.past || [];
      const nowcast = data.radar?.nowcast || [];
      frames = [...past, ...nowcast].map((frame) => ({ ...frame, host: data.host }));
      if (!frames.length) throw new Error("No radar frames available");

      mapElement.classList.add("radar-ready");
      toolbar.hidden = false;
      updateFrame(frames.length - 1);
    } catch (error) {
      showFallback("Live radar tiles are unavailable right now.");
    }
  }

  previousButton?.addEventListener("click", () => updateFrame(frameIndex - 1));
  nextButton?.addEventListener("click", () => updateFrame(frameIndex + 1));
  playButton?.addEventListener("click", togglePlay);

  initRadar();
})();

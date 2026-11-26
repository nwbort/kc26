// Edit this file to personalise the tracker. Supporters can't change these;
// they can only tweak their own view (stored in their browser).
window.KEPLER_CONFIG = {
  runnerName: "Nick",            // shown in the header
  bib: "",                        // e.g. "123" once allocated
  raceDate: "2026-12-05",         // Saturday, Te Anau
  startTime: "06:00",             // NZ local, 24h. 2025 gun was 6:00am
  goalFinish: "7:00",             // h:mm, the pre-race plan (3:21 marathon ≈ 15th pct of road marathoners → 15th pct of 2025 Kepler finishers)
  band: [10, 75],                 // percentile band of 2025 finishers used as comparables
  gender: "all",                  // "all" | "M" | "F"
  trackingUrl: "https://www.sportsplits.com/races/freshchoice-kepler-challenge-2026/events/1/",
  dataUrl: "data/results-2025.json",
  storeKey: "kepler26-v1",          // browser storage for supporters' entries

  // Checkpoint names by km. Distances come from the timing data; names are
  // best-guess mapping to the Kepler Track, check against the race guide.
  checkpointNames: {
    "5": "Brod Bay",
    "13.8": "Luxmore Hut",
    "19": "Forest Burn Shelter",
    "23.6": "Hanging Valley Shelter",
    "28.4": "Iris Burn Hut",
    "36.1": "Rocky Point",
    "44.6": "Moturau Hut",
    "50.6": "Rainbow Reach",
    "60": "Finish",
  },
};

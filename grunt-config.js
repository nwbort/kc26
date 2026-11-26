// Luxmore Grunt (event 2). Edit this file to personalise the tracker.
// Supporters can't change these; they can only tweak their own view
// (stored in their browser).
window.KEPLER_CONFIG = {
  runnerName: "Nicole",           // shown in the header
  bib: "",                        // e.g. "612" once allocated
  raceDate: "2026-12-05",         // Saturday, Te Anau (same day as the Kepler)
  startTime: "06:00",             // NZ local, 24h. PROVISIONAL: set from the 2025 Grunt results
  goalFinish: "3:30",             // PROVISIONAL: median 2025 Grunt woman (4:45 marathon ≈ median woman)
  band: [10, 75],                 // percentile band of 2025 finishers used as comparables
  gender: "all",                  // "all" | "M" | "F"
  trackingUrl: "https://www.sportsplits.com/races/freshchoice-kepler-challenge-2026/events/2/",
  dataUrl: "data/grunt-2025.json",
  storeKey: "grunt26-v1",

  // Checkpoint names by km, from the timing data.
  checkpointNames: {
    "60": "Finish",
  },
};

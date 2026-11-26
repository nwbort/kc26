// Luxmore Grunt (event 2). Edit this file to personalise the tracker.
// Supporters can't change these; they can only tweak their own view
// (stored in their browser).
window.KEPLER_CONFIG = {
  runnerName: "Nicole",           // shown in the header
  bib: "",                        // e.g. "612" once allocated
  raceDate: "2026-12-05",         // Saturday, Te Anau (same day as the Kepler)
  startTime: "07:00",             // NZ local, 24h. 2025 gun was 7:00am (everyone timed from the gun)
  goalFinish: "3:45",             // h:mm. 4:45 marathon ≈ median woman road marathoner → median 2025 Grunt woman (3:44)
  band: [10, 75],                 // percentile band of 2025 finishers used as comparables
  gender: "all",                  // "all" | "M" | "F"
  trackingUrl: "https://www.sportsplits.com/races/freshchoice-kepler-challenge-2026/events/2/",
  dataUrl: "data/grunt-2025.json",
  storeKey: "grunt26-v1",

  // Checkpoint names by km. Distances come from the timing data; the course
  // goes up to Luxmore Hut and back down past Brod Bay.
  checkpointNames: {
    "5": "Brod Bay",
    "13.8": "Luxmore Hut",
    "22": "Brod Bay (return)",
    "27": "Finish",
  },
};

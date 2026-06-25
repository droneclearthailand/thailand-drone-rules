// ============================================================
// THAILAND DRONE RULES — DATA FILE
// Edit this file to update the dashboard. Push to GitHub → Vercel auto-deploys.
// ============================================================

const LAST_VERIFIED = "2026-06-25";

const STATUS = [
  { state: "warn", label: "Border province bans", value: "ACTIVE" },
  { state: "ok",   label: "CAAT UAS Portal",       value: "OPERATIONAL" },
  { state: "ok",   label: "NBTC Registration",     value: "OPEN" },
  { state: "warn", label: "Pre-arrival registration", value: "NOT POSSIBLE" },
];

const FIGURES = [
  { rule: "Altitude limit",        value: "90 m / 300 ft" },
  { rule: "Min. airport distance", value: "9 km" },
  { rule: "Insurance minimum",     value: "THB 1,000,000" },
  { rule: "NBTC fee (approx.)",    value: "~THB 200" },
  { rule: "CAAT exam questions",   value: "40" },
  { rule: "Exam pass score",       value: "75%" },
  { rule: "Exam retake wait",      value: "24 hours" },
  { rule: "Camera = registration", value: "ANY weight" },
];

// Border-ban provinces (approx. centroids for map shading)
const BORDER_BANS = [
  { name: "Sa Kaeo",          lat: 13.81, lng: 102.07 },
  { name: "Surin",            lat: 14.88, lng: 103.49 },
  { name: "Buriram",          lat: 14.99, lng: 103.10 },
  { name: "Sisaket",          lat: 15.12, lng: 104.32 },
  { name: "Ubon Ratchathani", lat: 15.24, lng: 104.85 },
  { name: "Trat",             lat: 12.24, lng: 102.51 },
  { name: "Chanthaburi",      lat: 12.61, lng: 102.10 },
];

// Major airports (9km no-fly radius drawn programmatically)
const AIRPORTS = [
  { name: "Suvarnabhumi (BKK)",     lat: 13.690, lng: 100.750 },
  { name: "Don Mueang (DMK)",       lat: 13.913, lng: 100.607 },
  { name: "Phuket (HKT)",           lat: 8.113,  lng: 98.317 },
  { name: "Chiang Mai (CNX)",       lat: 18.767, lng: 98.963 },
  { name: "Koh Samui (USM)",        lat: 9.548,  lng: 100.062 },
  { name: "Krabi (KBV)",            lat: 8.099,  lng: 98.986 },
  { name: "Hua Hin (HHQ)",          lat: 12.636, lng: 99.951 },
  { name: "U-Tapao / Pattaya (UTP)",lat: 12.680, lng: 101.005 },
  { name: "Chiang Rai (CEI)",       lat: 19.952, lng: 99.883 },
  { name: "Udon Thani (UTH)",       lat: 17.386, lng: 102.788 },
];

const CHANGELOG = [
  { date: "2026-06-24", text: "Border bans remain active in Sa Kaeo, Surin, Buriram, Sisaket, Ubon Ratchathani, Trat, and Chanthaburi. No end date announced." },
  { date: "2025-01-15", text: "Pre-arrival registration no longer possible. Thai SIM and passport arrival stamp now required to register on the CAAT UAS Portal." },
  { date: "2025-01-15", text: "CAAT portal updated — OTP verification now required via a Thai mobile number." },
];

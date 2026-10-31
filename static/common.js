// Shared helpers for all pages (uses face-api.js loaded from a CDN).
const MODEL_URL = "https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.13/model/";
// Offline use: download the model files into static/models/ and use: "/models/"

let useSsd = false;      // stronger (but bigger) detector, loaded quietly in the background
let ssdTried = false;

async function ensureSsd() {
  if (ssdTried) return;
  ssdTried = true;
  try { await faceapi.nets.ssdMobilenetv1.loadFromUri(MODEL_URL); useSsd = true; }
  catch (e) { console.warn("SSD model not loaded, using tiny detector", e); }
}

async function loadModels(setStatus) {
  setStatus("Loading face models…", "info");
  // Only the small models are needed to start, so the page is ready quickly.
  await Promise.all([
    faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
    faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
    faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
  ]);
  setTimeout(ensureSsd, 2000);   // load the stronger detector later, without making anyone wait
}

async function startCamera(video) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("Camera not available. On a phone you must open this page over HTTPS.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
    audio: false,
  });
  video.srcObject = stream;
  await video.play();
}

const detectorOptions = () =>
  useSsd
    ? new faceapi.SsdMobilenetv1Options({ minConfidence: 0.35 })
    : new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.4 });

let lastFaceCount = 0;

const runDetect = (video, opts) =>
  faceapi.detectAllFaces(video, opts).withFaceLandmarks().withFaceDescriptors();

// Returns one face (with landmarks + descriptor) or null.
// strict=true  -> null unless exactly one face is visible (used when enrolling).
// strict=false -> if several faces are visible, use the biggest/closest one (used for check-in).
let missCount = 0;

async function detectOne(video, strict = false) {
  // 1) fast detector first, so a clear face is found almost instantly
  let all = await runDetect(video, new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.4 }));
  // 2) if nothing, try the slower, more sensitive detectors (always when enrolling,
  //    only every 3rd miss during check-in so an empty camera stays light on the computer)
  if (all.length === 0) {
    missCount++;
    if (strict || missCount % 3 === 0) {
      await ensureSsd();
      if (useSsd) all = await runDetect(video, new faceapi.SsdMobilenetv1Options({ minConfidence: 0.35 }));
      if (all.length === 0) all = await runDetect(video, new faceapi.TinyFaceDetectorOptions({ inputSize: 608, scoreThreshold: 0.25 }));
    }
  }
  lastFaceCount = all.length;
  if (all.length === 0) return null;
  if (all.length === 1) return all[0];
  if (strict) return null;
  const size = (f) => f.detection.box.width * f.detection.box.height;
  return all.reduce((best, f) => (size(f) > size(best) ? f : best));
}

// Tells the person what is actually wrong.
function faceHint() {
  return lastFaceCount > 1
    ? `More than one face is visible (${lastFaceCount} seen). Only one person in front of the camera, please.`
    : "No face found (0 seen). Look straight at the camera (not down), keep your face centered, wipe the camera lens, and use good light in front of you.";
}

// Eye aspect ratio: small value => eye closed.
function eyeAR(eye) {
  const d = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  return (d(eye[1], eye[5]) + d(eye[2], eye[4])) / (2 * d(eye[0], eye[3]));
}
function avgEAR(landmarks) {
  return (eyeAR(landmarks.getLeftEye()) + eyeAR(landmarks.getRightEye())) / 2;
}

function makeStatus(el) {
  return (msg, kind = "info") => {
    el.textContent = msg;
    el.className = "status " + kind;
  };
}

function adminHeaders() {
  return {
    "Content-Type": "application/json",
    "X-Admin-User": localStorage.getItem("adminUser") || "",
    "X-Admin-Password": localStorage.getItem("adminPw") || "",
  };
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

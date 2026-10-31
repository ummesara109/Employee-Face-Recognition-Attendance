# Face Check-in (prototype)

Employees show their face to a phone or laptop camera and are checked in automatically (blink check is optional: set REQUIRE_BLINK = true in static/index.html).

## How it works
- The browser (face-api.js) detects the face, checks for a **blink** (basic liveness) and converts the face into a 128-number embedding.
- Only the embedding is sent to the Flask server. **No photos are stored.**
- The server matches it against enrolled employees (SQLite) and records one check-in per employee per day.

## Run it
```bash
python -m venv venv
# Windows: venv\Scripts\activate     Mac/Linux: source venv/bin/activate
pip install -r requirements.txt

# Windows (PowerShell):  $env:ADMIN_USERNAME="yourID"; $env:ADMIN_PASSWORD="yourSecret"
# Mac/Linux:             export ADMIN_USERNAME=yourID ADMIN_PASSWORD=yourSecret
python app.py
```
Open http://localhost:5000 on the laptop (camera works on localhost without HTTPS).

### Use it from a phone
Phones only allow camera access over HTTPS. Run:
```bash
python app.py --https
```
Then on the phone (same Wi-Fi) open `https://<your-laptop-ip>:5000` and accept the self-signed certificate warning.

## Pages
| Page | Purpose |
|---|---|
| `/` | Check-in: camera on, show face, done |
| `/enroll.html` | Admin enrolls an employee (5 face samples) |
| `/admin.html` | Attendance by date, employee list, delete, CSV export |

Default admin login is ID `admin` / password `admin123`. **Change both** with the `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables.

## Settings
- `MATCH_THRESHOLD` (default `0.55`): lower = stricter. Raise to ~0.6 if genuine people are rejected, lower to ~0.5 if wrong people match.
- `PORT` (default `5000`).

## Internet needed
face-api.js and its model files load from the jsDelivr CDN. For fully offline use, download the `@vladmandic/face-api` package, copy its `dist/face-api.js` and `model/` folder into `static/`, and update the script tag and `MODEL_URL` in `static/common.js`.

## Glasses
Employees who wear glasses should enroll once with and once without them (tick "Add more samples" on the Enroll page). Blink detection adapts to each person, but avoid strong glare on the lenses.

## Limitations (important for real use)
- Blink liveness runs in the browser, so it stops casual photo attempts but not a determined attacker (video replay, modified client). For production use server-side/active liveness or a vetted commercial service.
- Face data is sensitive biometric data. Get employee consent, protect `attendance.db`, serve over HTTPS, and review India's DPDP Act requirements before real deployment.
- Add proper admin login (not a shared password) for production.

## Hosting for daily use
See `DEPLOY.md` for putting the app online on PythonAnywhere so employees can check in from their own phones.

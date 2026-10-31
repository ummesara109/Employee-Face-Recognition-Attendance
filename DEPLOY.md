# Put the app online (PythonAnywhere, free)

Result: employees open one permanent https link on their own phone or laptop,
show their face, and are checked in. No certificate warning, no laptop needed.

1. Create a free account at https://www.pythonanywhere.com (the "Beginner" plan). Remember your username.
2. **Files** tab: create a folder `face-checkin` and upload these into it, keeping the same structure:
   `app.py`, `requirements.txt`, and the whole `static` folder (index.html, enroll.html, admin.html, common.js, style.css).
   (Do NOT upload `attendance.db` or `venv`.)
3. **Web** tab -> **Add a new web app** -> *Manual configuration* -> pick Python 3.10 or newer.
4. On the Web tab, open the **WSGI configuration file** link and replace everything with:
   ```python
   import os, sys
   path = "/home/YOURUSERNAME/face-checkin"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["ADMIN_USERNAME"] = "choose-your-admin-id"
   os.environ["ADMIN_PASSWORD"] = "choose-a-strong-password"
   from app import app as application
   ```
   (replace YOURUSERNAME and choose your own admin ID and password), then Save.
5. If the Web tab or error log says "No module named flask/numpy", open a **Bash console** and run:
   `pip install --user flask numpy`
6. On the Web tab click the green **Reload** button.
7. Your app is now at `https://YOURUSERNAME.pythonanywhere.com`
   - Enroll employees at `/enroll.html` (admin ID and password from step 4).
   - Employees open the main link daily. On a phone they can use the browser menu -> **Add to Home screen** for a one-tap icon.

Notes
- The database `attendance.db` is created inside `face-checkin` and persists. Back it up now and then (download it from the Files tab).
- Free accounts may need a periodic "keep my app running" renewal; check your PythonAnywhere dashboard.
- Anyone who has the link can reach the check-in page. In `static/index.html` set `const REQUIRE_BLINK = true;` so a photo of a colleague cannot be used.

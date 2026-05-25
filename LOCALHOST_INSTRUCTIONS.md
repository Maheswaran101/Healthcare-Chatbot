# Running HealthAI on Localhost

Since the Flask backend server (`server.py`) already serves your entire frontend statically at `http://localhost:5000/`, you do not need Live Server or external proxies! Running the Flask server runs the whole project perfectly.

Here are the 4 easy ways to automatically or manually run the project on `localhost` every time you open it:

---

### 1. ⚡ Automate on VS Code Folder Open (Recommended)
We have added a custom task in `.vscode/tasks.json` that will prompt you to **"Allow running tasks on folder open"**.
- If you click **Allow**, every time you open this project folder in VS Code, the Flask server will boot up automatically in the integrated terminal!
- You can then simply open [http://localhost:5000/](http://localhost:5000/) in your browser.

---

### 2. 🟢 One-Click Double-Click Launcher (`run_local.bat`)
We created a double-clickable batch script `run_local.bat` at the root of the project.
- **How to use:** Just double-click `run_local.bat`.
- It will automatically open your default browser to [http://localhost:5000/](http://localhost:5000/) and launch the backend server in a terminal window.

---

### 3. 🐞 VS Code "Run and Debug" (F5)
We set up a launch configuration in `.vscode/launch.json`.
- Press **F5** or go to the **Run and Debug** panel in VS Code and click **Launch HealthAI (Flask + Browser)**.
- This will boot the Flask app and automatically launch a browser window straight to [http://localhost:5000/](http://localhost:5000/).

---

### 4. 💻 Command Line Standard
If you prefer running commands, you can now use:
```powershell
npm run dev
# or
npm start
# or
python server.py
```
And go to [http://localhost:5000/](http://localhost:5000/) (Flask default port).


### Dataset, AI chat, and QuickSight

- **S3 data for chat (same as QuickSight):** Add **`patients.env`** next to `server.py` (copy from `patients.env.example`). Set **`AWS_PROFILE`** (same SSO profile that can open QuickSight) and either **`PATIENTS_S3_URI=s3://bucket/path/to/file.json`** (your upload link) or **`PATIENTS_BUCKET`** + **`PATIENTS_PREFIX`**. Run `aws sso login --profile ...`, restart Flask, then open `/api/dataset-info?refresh=1` — `data_source` should be **`s3_uri`** or **`s3`**, not `fallback_error`. `quicksight.env` is also read for **`AWS_PROFILE`** if you did not set it in `patients.env`.

- **AI Agent tab:** Answers use **your dataset only** (same calculations as charts). Numbers are no longer replaced by the Bedrock model. Optional: set `CHAT_USE_BEDROCK=1` before `python server.py` to append an optional model note (still grounded tables).
- **QuickSight tab:** Uses `quicksight.env` — dashboard ID must match the one in **QuickSight → Dashboards** (UUID in the URL). Configure embedding domains and SSO as described in the project `quicksight.env.example`.

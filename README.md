# ML-Project

## FaceFolio Backend (FastAPI)

This repository contains the FaceFolio backend which detects faces in uploaded photos, computes embeddings (facenet-pytorch), lets you label unknown faces, persists known face encodings to `face_encodings.pickle`, and copies the original photo into per-person folders under `sorted_photos/`.

### Requirements

- Python 3.8+
- Install dependencies in `FaceFolio/backend/requirements.txt` (recommended in a virtualenv).

Example (from repo root):

```bash
cd FaceFolio/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> Note: The repo previously included a `venv/` directory; it's recommended to add `FaceFolio/backend/venv/` to `.gitignore` instead of committing it.

### Run the backend

Start the FastAPI server with uvicorn (development):

```bash
cd FaceFolio/backend
uvicorn main:app --reload --port 8000
```

The API will be available at: http://127.0.0.1:8000

Static cropped face images are served under `/temp_crops/` (mounted in the app).

### API endpoints

1) POST /api/process-photo

- Accepts multipart file upload (`file` field).
- Saves the uploaded photo to `temp_uploads/`, detects faces, returns:
  - `temp_photo_path` — path to the saved uploaded image
  - `identified_people` — list of names matched from `face_encodings.pickle`
  - `unidentified_faces` — array of `{temp_id, image_url}` to allow labeling



2) POST /api/finalize-and-sort

- Body (JSON):
  - `temp_photo_path` (string): the `temp_photo_path` from `/process-photo`
  - `identified_people` (array of strings): existing names detected
  - `new_labels` (array of {temp_id, name}): label unknown faces





What finalize does:
- Appends any new face encodings to `face_encodings.pickle` with the provided names.
- Copies the original uploaded photo into `sorted_photos/<name>/` for each name present in the photo.
- Cleans up the `temp_uploads/` photo and removes the labeled crops from `temp_crops/`.

### Labeling workflow (manual)

1. Upload a photo to `/api/process-photo`.
2. The API returns `unidentified_faces` with temporary crop URLs under `/temp_crops/`.
3. You can label them by either:
   - Renaming files in `FaceFolio/backend/temp_crops/` as `<name>.jpg` (I used this approach during testing), or
   - Providing a JSON mapping of `temp_id` → `name` to `/api/finalize-and-sort` as `new_labels`.
4. Call `/api/finalize-and-sort` to persist the encodings and copy the original photo into each person's folder.



Keep `.gitkeep` if present, or use `-f` to remove everything.

### Notes & tips

- The backend uses `facenet-pytorch` (MTCNN + InceptionResnetV1) and stores 512-d embeddings in the pickle.
- Matching uses cosine distance (threshold tuned in code). Deduplication within a single upload falls back to IoU if embeddings are not decisive.
- For production or sharing, don't commit virtual environments (add `FaceFolio/backend/venv/` to `.gitignore`).
- If you want the React frontend restored, I can recreate it and wire it to the API.


# FaceFolio — Simple README (friendly + step-by-step)

This file explains, in plain language, how the FaceFolio backend works, how to run it on your machine, and how to push the README changes to GitHub. It focuses on the working flow: upload a photo, detect faces, label unknown faces, and copy the photo into per-person folders.

KEEP IT SIMPLE — What this project does
- You upload a photo.
- The server finds faces and tries to match them to people it already knows.
- For faces it doesn't recognize, it gives you small face-crop images so you can type names.
- When you confirm names, the server remembers those faces and copies the original photo into `sorted_photos/<name>/` for each person in the image.

WHERE THINGS LIVE (folders)
- `temp_uploads/` — temporary location for the original uploaded images
- `temp_crops/` — crops of detected faces (served at `/temp_crops/<uuid>.jpg`) used for labeling
- `sorted_photos/<name>/` — final folders where copies of the original photo are stored per person
- `face_encodings.pickle` — the small database that stores known face embeddings and names (created when you label a face)

QUICK STEPS TO RUN LOCALLY (Windows PowerShell)
1) Open PowerShell and go to the backend folder:

```powershell
cd C:\Users\Anikete\Documents\projects\ML-Project\FaceFolio\backend
```

2) Create a virtual environment (use Python 3.11 if you have it):

```powershell
py -3.11 -m venv .\venv
```

3) Activate the venv (PowerShell):

```powershell
.\venv\Scripts\Activate.ps1
# If activation is blocked, you may need to allow scripts: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

4) Install requirements:

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

5) Start the server:

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

6) Open the UI in your browser:

http://127.0.0.1:8000/

ENDPOINTS (easy examples)
- POST /api/process-photo — Upload a photo to scan for faces.
  - Example (curl):
    curl -F "file=@C:/full/path/to/photo.jpg" http://127.0.0.1:8000/api/process-photo
  - What the server returns (example):
    {
      "temp_photo_path":"temp_uploads/photo.jpg",
      "identified_people":["alice"],
      "unidentified_faces":[{"temp_id":"uuid","image_url":"/temp_crops/uuid.jpg"}]
    }

- POST /api/finalize-and-sort — Tell the server the names for unknown faces and copy the photo into each person's folder.
  - Payload (JSON):
    {
      "temp_photo_path":"temp_uploads/photo.jpg",
      "identified_people":["alice"],
      "new_labels":[{"temp_id":"uuid","name":"charlie"}]
    }
  - Example (curl):
    curl -H "Content-Type: application/json" -d @payload.json http://127.0.0.1:8000/api/finalize-and-sort

- GET /api/known-people — returns the list of names the system already learned.
  - Example: http://127.0.0.1:8000/api/known-people

- GET /api/sorted-folders — returns person -> [image URLs] for `sorted_photos/`.
  - Example: http://127.0.0.1:8000/api/sorted-folders

SIMPLE WORKFLOW (example)
1. Upload `group.jpg` with `/api/process-photo`.
2. Server returns: identified_people: ["alice"], unidentified_faces: [t1, t2].
3. You label t1 -> "charlie" and t2 -> "david" and call `/api/finalize-and-sort` with that data.
4. Server appends charlie/david encodings to `face_encodings.pickle` and copies `group.jpg` into:
   - `sorted_photos/alice/group.jpg`
   - `sorted_photos/charlie/group.jpg`
   - `sorted_photos/david/group.jpg`

IMPORTANT NOTES
- If you restart the server before finalizing, the temporary embeddings cache is lost. Label faces before restarting.
- Names are used as folder names. Avoid slashes or weird characters in names (I can add sanitization if you want).
- Matching is not perfect; change the threshold in `main.py` if you need stricter/looser matching.



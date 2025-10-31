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

Example upload using curl:

```bash
curl -F "file=@/path/to/photo.jpg" http://127.0.0.1:8000/api/process-photo
```

The response (example):

```json
{
  "temp_photo_path": "temp_uploads/photo.jpg",
  "identified_people": ["alice","bob"],
  "unidentified_faces": [
    {"temp_id":"<uuid>", "image_url":"/temp_crops/<uuid>.jpg"}
  ]
}
```

2) POST /api/finalize-and-sort

- Body (JSON):
  - `temp_photo_path` (string): the `temp_photo_path` from `/process-photo`
  - `identified_people` (array of strings): existing names detected
  - `new_labels` (array of {temp_id, name}): label unknown faces

Example finalize payload (auto-label known names only):

```bash
printf '%s\n' '{"temp_photo_path":"temp_uploads/photo.jpg","identified_people":["alice"],"new_labels":[]}' > /tmp/finalize.json
curl -H "Content-Type: application/json" -d @/tmp/finalize.json http://127.0.0.1:8000/api/finalize-and-sort
```

Example finalize payload with new labels:

```bash
printf '%s\n' '{"temp_photo_path":"temp_uploads/photo.jpg","identified_people":[],"new_labels":[{"temp_id":"<uuid>","name":"charlie"}]}' > /tmp/finalize.json
curl -H "Content-Type: application/json" -d @/tmp/finalize.json http://127.0.0.1:8000/api/finalize-and-sort
```

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

### Cleanup commands

To clear runtime artifacts (safe to run when server is stopped or you don't need the data):

```bash
cd FaceFolio/backend
rm -rf temp_uploads/* temp_crops/* sorted_photos/* face_encodings.pickle
```

Keep `.gitkeep` if present, or use `-f` to remove everything.

### Notes & tips

- The backend uses `facenet-pytorch` (MTCNN + InceptionResnetV1) and stores 512-d embeddings in the pickle.
- Matching uses cosine distance (threshold tuned in code). Deduplication within a single upload falls back to IoU if embeddings are not decisive.
- For production or sharing, don't commit virtual environments (add `FaceFolio/backend/venv/` to `.gitignore`).
- If you want the React frontend restored, I can recreate it and wire it to the API.

### Quick checks I used during development

- Run a detection test locally:

```bash
curl -F "file=@FaceFolio/backend/IMG_20250716_133142335_HDR~2.jpg" http://127.0.0.1:8000/api/process-photo | python3 -m json.tool
```

- Finalize using identified people only (no new labels):

```bash
printf '%s\n' '{"temp_photo_path":"temp_uploads/WhatsApp Image 2025-10-27 at 8.18.13 PM.jpeg","identified_people":["kaushal","yash"],"new_labels":[]}' > /tmp/finalize.json
curl -H "Content-Type: application/json" -d @/tmp/finalize.json http://127.0.0.1:8000/api/finalize-and-sort | python3 -m json.tool
```

### Next steps (optional)

- Add `.gitignore` to exclude `venv/` and other generated files (I can add and push this change).
- Recreate a simple UI for labeling (React) if you prefer interactive labeling instead of manual file renames.

If you want, I can commit this README change and push it to `origin/main` now.
# ML-Project
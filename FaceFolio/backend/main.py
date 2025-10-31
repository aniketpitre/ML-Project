import os
import shutil
import pickle
import uuid
import uvicorn
import numpy as np
import torch
from facenet_pytorch import MTCNN, InceptionResnetV1
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
from PIL import Image

# --- Configuration & Setup ---
TEMP_UPLOAD_DIR = "temp_uploads"
TEMP_CROP_DIR = "temp_crops"
SORTED_PHOTOS_DIR = "sorted_photos"
ENCODINGS_FILE = "face_encodings.pickle"

# Create required directories
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_CROP_DIR, exist_ok=True)
os.makedirs(SORTED_PHOTOS_DIR, exist_ok=True)

# Global in-memory cache for temporary face encodings
# Key: temp_face_id (uuid), Value: face_encoding (list of floats)
temp_face_encoding_cache = {}

# --- Initialize facenet-pytorch models (server-side)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# MTCNN: detect faces and produce aligned face tensors
mtcnn = MTCNN(keep_all=True, device=device)
# InceptionResnetV1: produces 512-d embeddings
resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)

# --- Helper Functions ---

def load_known_faces():
    """Loads known face encodings and names from the pickle file."""
    known_encodings = []
    known_names = []
    if os.path.exists(ENCODINGS_FILE):
        try:
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
                known_encodings = data.get("encodings", [])
                known_names = data.get("names", [])
        except Exception:
            # If pickle exists but is corrupted, ignore and start fresh
            known_encodings = []
            known_names = []
    return known_encodings, known_names


def save_known_faces(known_encodings, known_names):
    """Saves the updated face encodings and names to the pickle file."""
    # Ensure encodings are JSON-friendly lists (not numpy arrays)
    encs = [np.asarray(e).tolist() for e in known_encodings]
    data = {"encodings": encs, "names": known_names}
    with open(ENCODINGS_FILE, "wb") as f:
        pickle.dump(data, f)


def cosine_distance(a, b):
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 1.0
    return 1.0 - (np.dot(a, b) / denom)


def box_iou(boxA, boxB):
    """Compute IoU between two boxes [x1,y1,x2,y2]."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interW = max(0, xB - xA)
    interH = max(0, yB - yA)
    interArea = interW * interH
    boxAArea = max(0, boxA[2] - boxA[0]) * max(0, boxA[3] - boxA[1])
    boxBArea = max(0, boxB[2] - boxB[0]) * max(0, boxB[3] - boxB[1])
    denom = float(boxAArea + boxBArea - interArea)
    if denom <= 0:
        return 0.0
    return interArea / denom


def find_best_match(known_encodings, encoding, threshold=0.6):
    """Find best match index using cosine distance. Returns index or None.

    threshold: max allowed cosine distance (smaller = more similar). You may tune this.
    """
    if not known_encodings:
        return None
    distances = [cosine_distance(k, encoding) for k in known_encodings]
    best_idx = int(np.argmin(distances))
    if distances[best_idx] <= threshold:
        return best_idx
    return None

# --- FastAPI App ---
app = FastAPI(title="FaceFolio API")

# Allow CORS for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the cropped face images as static files
app.mount(f"/{TEMP_CROP_DIR}", StaticFiles(directory=TEMP_CROP_DIR), name="crops")

# Serve a minimal frontend (single-page app) from the static/ directory at the root.
# This allows visiting http://<host>:<port>/ to load the UI while keeping API routes
# Mount the frontend static assets under /static to avoid catching API routes.
app.mount("/static", StaticFiles(directory="static"), name="static_files")

from fastapi.responses import FileResponse


@app.get("/", include_in_schema=False)
def serve_ui():
    """Serve the single-page UI index."""
    return FileResponse(os.path.join("static", "index.html"))


# --- API Models ---
class NewLabel(BaseModel):
    temp_id: str
    name: str

class FinalizeSortRequest(BaseModel):
    temp_photo_path: str
    identified_people: List[str]
    new_labels: List[NewLabel]

# --- API Endpoints ---

@app.post("/api/process-photo")
async def process_photo(file: UploadFile = File(...)):
    """
    1. Receives an uploaded photo.
    2. Scans for all faces.
    3. Compares faces to the known_faces "database".
    4. Returns a list of identified people and a list of unidentified faces to be labeled.
    """
    # 1. Save uploaded file temporarily
    temp_photo_path = os.path.join(TEMP_UPLOAD_DIR, file.filename)
    try:
        with open(temp_photo_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    # 2. Load the "brain"
    known_encodings, known_names = load_known_faces()

    # 3. Load the uploaded image and find faces using MTCNN
    try:
        pil_image = Image.open(temp_photo_path).convert('RGB')

        # Detect bounding boxes (x1, y1, x2, y2)
        boxes, probs = mtcnn.detect(pil_image)

        # Get aligned face tensors (preprocessed) from MTCNN
        faces_tensors = mtcnn(pil_image)  # returns None or tensor (n,3,160,160)
        if faces_tensors is None:
            faces_tensors = []
    except Exception as e:
        # Cleanup and error
        if os.path.exists(temp_photo_path):
            os.remove(temp_photo_path)
        raise HTTPException(status_code=400, detail=f"Failed to process image: {e}")

    identified_people = set()
    unidentified_faces = []

    # Keep lists for deduplication within a single request
    seen_encodings = []  # list of numpy arrays
    seen_boxes = []

    # 4. Compare each found face to the "brain"
    # boxes may be None if no faces found
    if boxes is None or len(boxes) == 0:
        # No faces found; return empty lists
        return {
            "temp_photo_path": temp_photo_path,
            "identified_people": [],
            "unidentified_faces": []
        }

    # Ensure faces_tensors is a batched tensor
    if isinstance(faces_tensors, torch.Tensor):
        faces_batch = faces_tensors.to(device)
        with torch.no_grad():
            embeddings = resnet(faces_batch).cpu().numpy()
    else:
        embeddings = []

    width, height = pil_image.size

    for idx, box in enumerate(boxes):
        # box: [x1, y1, x2, y2]
        x1, y1, x2, y2 = [int(max(0, b)) for b in box]
        x2 = min(width, x2)
        y2 = min(height, y2)
        x1 = max(0, x1)
        y1 = max(0, y1)

        encoding = embeddings[idx] if len(embeddings) > idx else None
        name = None

        # --- Deduplication: skip if this face is essentially the same as one already seen
        is_duplicate = False
        # If we have an embedding, compare to other embeddings seen in this photo
        if encoding is not None and seen_encodings:
            for se in seen_encodings:
                try:
                    if cosine_distance(se, encoding) < 0.08:  # very close -> duplicate
                        is_duplicate = True
                        break
                except Exception:
                    continue

        # If no embedding or not decisive, fall back to IoU with seen boxes
        if not is_duplicate and seen_boxes:
            for sb in seen_boxes:
                if box_iou(sb, [x1, y1, x2, y2]) > 0.6:
                    is_duplicate = True
                    break

        if is_duplicate:
            # Skip this detection as it's likely a duplicate of a previously processed face in the same photo
            continue

        if encoding is not None and known_encodings:
            match_idx = find_best_match(known_encodings, encoding)
            if match_idx is not None:
                name = known_names[match_idx]
                identified_people.add(name)

        if name is None:
            # New unidentified face
            temp_id = str(uuid.uuid4())
            # Add padding around the detected box to avoid tight crops (helps partial detections)
            pad_frac = 0.25  # 25% padding on each side
            bw = x2 - x1
            bh = y2 - y1
            px = int(bw * pad_frac)
            py = int(bh * pad_frac)
            cx1 = max(0, x1 - px)
            cy1 = max(0, y1 - py)
            cx2 = min(width, x2 + px)
            cy2 = min(height, y2 + py)
            face_image = pil_image.crop((cx1, cy1, cx2, cy2))
            crop_filename = f"{temp_id}.jpg"
            crop_path = os.path.join(TEMP_CROP_DIR, crop_filename)
            face_image.save(crop_path)

            # Store encoding as list for later persistence
            if encoding is not None:
                temp_face_encoding_cache[temp_id] = np.asarray(encoding).tolist()
                # record for dedupe
                seen_encodings.append(np.asarray(encoding))
            else:
                temp_face_encoding_cache[temp_id] = None

            # record box for IoU-based dedupe
            seen_boxes.append([x1, y1, x2, y2])

            unidentified_faces.append({
                "temp_id": temp_id,
                "image_url": f"/{TEMP_CROP_DIR}/{crop_filename}"
            })

    return {
        "temp_photo_path": temp_photo_path,
        "identified_people": list(identified_people),
        "unidentified_faces": unidentified_faces
    }


@app.post("/api/finalize-and-sort")
async def finalize_and_sort(request: FinalizeSortRequest):
    """
    1. Receives the labels for the new faces.
    2. Updates the "brain" (pickle file) with these new people.
    3. Sorts the original photo into folders for ALL people (old and new).
    4. Cleans up temporary files.
    """
    # 1. Load the "brain"
    known_encodings, known_names = load_known_faces()

    all_names_in_photo = set(request.identified_people)

    # 2. Learn the new faces
    for label in request.new_labels:
        if not label.name:
            continue  # Skip if user left the name blank

        all_names_in_photo.add(label.name)

        # Check if we still have the encoding in our cache
        if label.temp_id in temp_face_encoding_cache and temp_face_encoding_cache[label.temp_id] is not None:
            # Add to our "brain" (store as list for pickle portability)
            known_encodings.append(list(temp_face_encoding_cache[label.temp_id]))
            known_names.append(label.name)

            # Remove from cache
            del temp_face_encoding_cache[label.temp_id]

    # 3. Save the updated "brain"
    save_known_faces(known_encodings, known_names)

    # 4. Sort the photo into folders
    if not os.path.exists(request.temp_photo_path):
        raise HTTPException(status_code=404, detail="Original photo not found. It may have been processed already.")

    for name in all_names_in_photo:
        person_folder = os.path.join(SORTED_PHOTOS_DIR, name)
        os.makedirs(person_folder, exist_ok=True)
        shutil.copy(request.temp_photo_path, person_folder)

    # 5. Clean up
    # Delete the main temp photo
    try:
        os.remove(request.temp_photo_path)
    except Exception:
        pass

    # Clean up any leftover crops from this request
    for label in request.new_labels:
        crop_path = os.path.join(TEMP_CROP_DIR, f"{label.temp_id}.jpg")
        if os.path.exists(crop_path):
            try:
                os.remove(crop_path)
            except Exception:
                pass

    return {"message": f"Photo sorted successfully for {', '.join(all_names_in_photo)}"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

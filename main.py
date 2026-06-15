import face_recognition
import cv2
import os
import glob
import numpy as np
import threading
import requests
import base64
import uuid
import sqlite3
import time
from datetime import datetime

# --- 1. CONFIGURATION ---
N8N_WEBHOOK_URL = "https://n8n.srv1335246.hstgr.cloud/webhook/1rotary-attendance"

CAMERAS = {
    "Camera-1 (Main Entry)": "rtsp://admin:%40Dmin1234@192.168.1.53:554/cam/realmonitor?channel=1&subtype=0",
}

# --- NEW: COOLDOWN TIMER ---
# How many seconds to wait before logging the SAME person again (300 seconds = 5 minutes)
COOLDOWN_SECONDS = 300 
recent_detections = {} 

EMPLOYEES_DIR = r'C:\Users\user\Desktop\FaceRecProject\employees'
DB_PATH = os.path.join(EMPLOYEES_DIR, 'employees.db')
images_path = os.path.join(EMPLOYEES_DIR, '*.jpg')

# Global variables to hold active profiles
known_face_encodings = []
known_face_data = []

# Cache to prevent lag
encoding_cache = {} 
data_cache = {}

# THE TRAFFIC LIGHT (Prevents the silent crash)
dlib_lock = threading.Lock()

# --- 2. Thread for CCTV Stream ---
class CCTVStream:
    def __init__(self, src):
        self.stream = cv2.VideoCapture(src)
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False

    def start(self):
        threading.Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            (self.grabbed, self.frame) = self.stream.read()

    def read(self):
        return self.grabbed, self.frame

    def stop(self):
        self.stopped = True

# --- 3. Webhook Dispatcher ---
def send_to_n8n(person_data, frame_crop, camera_name):
    try:
        _, buffer = cv2.imencode('.jpg', frame_crop)
        b64_image = base64.b64encode(buffer).decode('utf-8')
        b64_string = f"data:image/jpeg;base64,{b64_image}"

        current_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        exact_person_id = person_data.get("person_id", "Unknown")
        exact_name = person_data.get("name", "Unknown")
        exact_role = person_data.get("role", "Unknown")
        dynamic_score = round(float(person_data.get("score", 0.0)), 4)

        payload = {
            "id": str(uuid.uuid4()),
            "person_id": exact_person_id,
            "name": exact_name, 
            "role": exact_role, 
            "camera": camera_name,
            "time": current_time,
            "face_image": b64_string,
            "score": dynamic_score, 
            "registered_photo": True,
            "ai_commentary": f"Biometric Check-in verified via {camera_name} with {int(dynamic_score * 100)}% confidence.",
            "ai_risk_score": round(1.0 - dynamic_score, 4),
            "createdAt": current_time,
            "updatedAt": current_time
        }

        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"\n[+] Webhook success: {exact_name} ({int(dynamic_score * 100)}%) logged at {camera_name}")
        else:
            print(f"\n[-] Webhook failed with status: {response.status_code}")
            
    except Exception as e:
        print(f"\n[!] Error sending webhook: {e}")

# --- 4. Profile Loading Function ---
def load_profiles(quiet=False):
    global known_face_encodings, known_face_data, encoding_cache, data_cache
    
    found_images = glob.glob(images_path)
    if not quiet:
        print(f"Loading {len(found_images)} employee profiles...")

    temp_encodings = []
    temp_data = []

    for img_path in found_images:
        if img_path in encoding_cache:
            temp_encodings.append(encoding_cache[img_path])
            temp_data.append(data_cache[img_path])
            continue
            
        try:
            img_bgr = cv2.imread(img_path)
            if img_bgr is None: continue
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            
            with dlib_lock:
                encodings = face_recognition.face_encodings(img_rgb)
            
            if len(encodings) > 0:
                base_name = os.path.splitext(os.path.basename(img_path))[0]
                
                person_info = {
                    "person_id": base_name,
                    "name": base_name.upper(),
                    "role": "Unknown",
                    "score": 0.0 
                }
                
                try:
                    if os.path.exists(DB_PATH):
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        c.execute("SELECT name, role FROM employees WHERE person_id=?", (base_name,))
                        row = c.fetchone()
                        
                        if row:
                            person_info["name"] = row[0]
                            person_info["role"] = row[1]
                        conn.close()
                except Exception as db_err:
                    pass
                
                encoding_cache[img_path] = encodings[0]
                data_cache[img_path] = person_info
                
                temp_encodings.append(encodings[0])
                temp_data.append(person_info)
                if not quiet:
                    print(f"-> Loaded profile: {person_info['name']} ({person_info['role']})")
                
        except Exception as e:
            print(f"[!] Fatal error loading image {img_path}: {e}")

    known_face_encodings = temp_encodings
    known_face_data = temp_data

# --- 5. The Profile Watcher Thread ---
def profile_watcher():
    last_file_count = len(glob.glob(images_path))
    while not ai_stopped:
        time.sleep(3)
        current_file_count = len(glob.glob(images_path))
        
        if current_file_count != last_file_count:
            print(f"\n[🔄] Change detected in Database! Updating AI memory...")
            load_profiles(quiet=True)
            last_file_count = current_file_count
            print(f"[✔] Memory updated. Now tracking {current_file_count} personnel.")

# Execute initial load before starting the camera
load_profiles()
if not known_face_encodings:
    print("❌ No valid employee profiles loaded. (Will keep waiting for new uploads)")

# --- 6. Global Variables for Multiple AI Threads ---
current_face_ui = {cam_name: [] for cam_name in CAMERAS.keys()}  
ai_stopped = False

# --- 7. Thread for AI Processing (The Brain) ---
def ai_worker(cam_name, video_capture):
    global current_face_ui, ai_stopped
    frame_count = 0  
    
    while not ai_stopped:
        ret, frame = video_capture.read()
        if not ret or frame is None:
            continue

        frame_count += 1
        if frame_count % 3 != 0:
            continue

        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        with dlib_lock:
            locations = face_recognition.face_locations(rgb_small_frame)
            encodings = face_recognition.face_encodings(rgb_small_frame, locations)

        new_face_ui = []
        for face_location, face_encoding in zip(locations, encodings):
            
            if not known_face_encodings:
                continue
                
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            display_name = "Unknown"
            
            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                
                if matches[best_match_index]:
                    raw_distance = float(face_distances[best_match_index])
                    confidence_score = 1.0 - raw_distance if raw_distance <= 1.0 else 0.0
                    
                    person_data = known_face_data[best_match_index].copy()
                    person_data["score"] = confidence_score  
                    
                    display_name = f"{person_data['name']} ({int(confidence_score * 100)}%)"
                    person_id = person_data["person_id"]
                    
                    # --- FIXED: Use seconds instead of days for the cooldown ---
                    current_time_sec = time.time()
                    last_seen_time = recent_detections.get(person_id, 0)
                    
                    if (current_time_sec - last_seen_time) > COOLDOWN_SECONDS:
                        recent_detections[person_id] = current_time_sec
                        
                        top, right, bottom, left = face_location
                        t, r, b, l = top*2, right*2, bottom*2, left*2
                        
                        h, w, _ = frame.shape
                        crop = frame[max(0, t-20):min(h, b+20), max(0, l-20):min(w, r+20)]
                        
                        threading.Thread(target=send_to_n8n, args=(person_data, crop, cam_name), daemon=True).start()

            top, right, bottom, left = face_location
            scaled_location = (top * 2, right * 2, bottom * 2, left * 2)
            new_face_ui.append((scaled_location, display_name))

        current_face_ui[cam_name] = new_face_ui

# --- 8. Start Streams and Threads ---
print("\nConnecting to all cameras... Press 'q' to exit.")

video_streams = {}

for cam_name, src in CAMERAS.items():
    print(f"Initializing {cam_name}...")
    video_streams[cam_name] = CCTVStream(src).start()
    threading.Thread(target=ai_worker, args=(cam_name, video_streams[cam_name]), daemon=True).start()

threading.Thread(target=profile_watcher, daemon=True).start()

print("All cameras active.")

# --- 9. Main Display Loop (The Screens) ---
while True:
    for cam_name, video_capture in video_streams.items():
        ret, frame = video_capture.read()
        if not ret or frame is None:
            continue

        for (top, right, bottom, left), display_name in current_face_ui[cam_name]:
            color = (0, 255, 0) if display_name != "Unknown" else (0, 0, 255)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            cv2.putText(frame, display_name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 0, 0), 1)

        cv2.imshow(f'Verification Feed: {cam_name}', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        ai_stopped = True
        break

for video_capture in video_streams.values():
    video_capture.stop()
    
cv2.destroyAllWindows()
print("Camera streams closed successfully.")
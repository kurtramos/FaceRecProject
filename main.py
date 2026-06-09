import face_recognition
import cv2
import os
import glob
import numpy as np
import threading
import requests
import base64
import uuid
from datetime import datetime

# --- 1. CONFIGURATION ---
N8N_WEBHOOK_URL = "https://n8n.srv1335246.hstgr.cloud/webhook/1rotary-attendance"

# Add all your cameras here. 
# You can use RTSP links or 0, 1, 2 for local USB webcams.
CAMERAS = {
    "Camera-1 (Main Entry)": "rtsp://admin:%40Dmin1234@192.168.1.14:554/cam/realmonitor?channel=1&subtype=0",
    # Example for a second camera:
    # "Camera-2 (Back Door)": "rtsp://admin:%40Dmin1234@192.168.1.13:554/cam/realmonitor?channel=1&subtype=1",
    # Example for a local laptop webcam:
    # "Camera-3 (Webcam)": 0 
}

daily_detections = {} 

# --- 2. Thread for CCTV Stream (The Eyes) ---
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
# Note: Added 'camera_name' so n8n knows exactly which door they entered
def send_to_n8n(person_id, frame_crop, camera_name):
    try:
        _, buffer = cv2.imencode('.jpg', frame_crop)
        b64_image = base64.b64encode(buffer).decode('utf-8')
        b64_string = f"data:image/jpeg;base64,{b64_image}"

        current_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        payload = {
            "id": str(uuid.uuid4()),
            "person_id": person_id,
            "name": person_id, 
            "role": "Cleaner", 
            "camera": camera_name,
            "time": current_time,
            "face_image": b64_string,
            "score": 0.99, 
            "registered_photo": True,
            "ai_commentary": f"Biometric Check-in verified via {camera_name}",
            "ai_risk_score": 0.0,
            "createdAt": current_time,
            "updatedAt": current_time
        }

        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"\n[+] Webhook success: {person_id} logged at {camera_name}")
        else:
            print(f"\n[-] Webhook failed with status: {response.status_code}")
            
    except Exception as e:
        print(f"\n[!] Error sending webhook: {e}")

# --- 4. Load Profiles ---
known_face_encodings = []
known_face_names = []

images_path = r'C:\Users\user\Desktop\FaceRecProject\employees\*'
found_images = glob.glob(images_path)
print(f"Loading {len(found_images)} employee profiles...")

for img_path in found_images:
    try:
        img_bgr = cv2.imread(img_path)
        if img_bgr is None: continue
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        encodings = face_recognition.face_encodings(img_rgb)
        if len(encodings) > 0:
            known_face_encodings.append(encodings[0])
            name = os.path.splitext(os.path.basename(img_path))[0].upper()
            known_face_names.append(name)
            print(f"-> Successfully loaded profile for: {name}")
    except Exception as e:
        pass

if not known_face_encodings:
    print("❌ No valid employee profiles loaded. Check your directory path.")
    exit()

# --- 5. Global Variables for Multiple AI Threads ---
# Create a separate data dictionary for each camera
current_face_data = {cam_name: [] for cam_name in CAMERAS.keys()}  
ai_stopped = False

# --- 6. Thread for AI Processing (The Brain) ---
# Note: Now accepts specific camera feeds as arguments
def ai_worker(cam_name, video_capture):
    global current_face_data, ai_stopped
    while not ai_stopped:
        ret, frame = video_capture.read()
        if not ret or frame is None:
            continue

        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        locations = face_recognition.face_locations(rgb_small_frame)
        encodings = face_recognition.face_encodings(rgb_small_frame, locations)

        new_face_data = []
        for face_location, face_encoding in zip(locations, encodings):
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            name = "Unknown"
            
            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = known_face_names[best_match_index]
                    
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    last_seen_date = daily_detections.get(name)
                    
                    if last_seen_date != current_date:
                        daily_detections[name] = current_date
                        
                        top, right, bottom, left = face_location
                        t, r, b, l = top*2, right*2, bottom*2, left*2
                        
                        h, w, _ = frame.shape
                        crop = frame[max(0, t-20):min(h, b+20), max(0, l-20):min(w, r+20)]
                        
                        # Send to n8n, passing the exact camera name
                        threading.Thread(target=send_to_n8n, args=(name, crop, cam_name), daemon=True).start()

            top, right, bottom, left = face_location
            scaled_location = (top * 2, right * 2, bottom * 2, left * 2)
            new_face_data.append((scaled_location, name))

        # Update the data specifically for this camera
        current_face_data[cam_name] = new_face_data

# --- 7. Start Streams and Threads ---
print("\nConnecting to all cameras... Press 'q' to exit.")

video_streams = {}

for cam_name, src in CAMERAS.items():
    print(f"Initializing {cam_name}...")
    # Start the video stream thread
    video_streams[cam_name] = CCTVStream(src).start()
    
    # Start a dedicated AI worker thread for this specific camera
    threading.Thread(target=ai_worker, args=(cam_name, video_streams[cam_name]), daemon=True).start()

print("All cameras active.")

# --- 8. Main Display Loop (The Screens) ---
while True:
    # Loop through every active camera stream
    for cam_name, video_capture in video_streams.items():
        ret, frame = video_capture.read()
        if not ret or frame is None:
            continue

        # Draw boxes based on the data specific to this camera
        for (top, right, bottom, left), name in current_face_data[cam_name]:
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 0, 0), 1)

        # Show a separate window for each camera
        cv2.imshow(f'Verification Feed: {cam_name}', frame)

    # Press 'q' to shut down all cameras
    if cv2.waitKey(1) & 0xFF == ord('q'):
        ai_stopped = True
        break

# Safely close everything down
for video_capture in video_streams.values():
    video_capture.stop()
    
cv2.destroyAllWindows()
print("All camera streams closed successfully.")
import face_recognition
import cv2
import os
import glob
import numpy as np
import threading

# --- 1. Thread for CCTV Stream (The Eyes) ---
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

# --- 2. Load Profiles ---
known_face_encodings = []
known_face_names = []

images_path = 'employees/*'
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
            name = os.path.splitext(os.path.basename(img_path))[0].replace('_', ' ').title()
            known_face_names.append(name)
            print(f"-> Successfully loaded profile for: {name}")
    except Exception as e:
        pass

if not known_face_encodings:
    print("❌ No valid employee profiles loaded.")
    exit()

# --- 3. Global Variables for AI Thread ---
current_face_data = []  # Will securely hold the latest AI results
ai_stopped = False

# --- 4. Thread for AI Processing (The Brain) ---
def ai_worker():
    global current_face_data, ai_stopped
    while not ai_stopped:
        ret, frame = video_capture.read()
        if not ret:
            continue

        # Resize to 1/2 size for faster processing
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

            # Scale back up by 2 to match the original video frame
            top, right, bottom, left = face_location
            scaled_location = (top * 2, right * 2, bottom * 2, left * 2)
            new_face_data.append((scaled_location, name))

        # Quietly update the main loop's data with the newest findings
        current_face_data = new_face_data

# --- 5. Start Streams and Threads ---
cctv_url = "rtsp://admin:%40Dmin1234@192.168.1.14:554/cam/realmonitor?channel=1&subtype=0"
print("\nConnecting to CCTV and starting background threads... Press 'q' to exit.")

video_capture = CCTVStream(cctv_url).start()

# Start the separate AI worker thread
threading.Thread(target=ai_worker, daemon=True).start()

# --- 6. Main Display Loop (The Screen - Runs at pure 30 FPS) ---
while True:
    ret, frame = video_capture.read()
    if not ret:
        continue

    # Instantly draw the latest data provided by the AI thread without waiting
    for (top, right, bottom, left), name in current_face_data:
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.rectangle(frame, (left, bottom - 35), (right, bottom), (0, 255, 0), cv2.FILLED)
        cv2.putText(frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 0, 0), 1)

    cv2.imshow('CCTV Access Verification Feed', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        ai_stopped = True
        break

video_capture.stop()
cv2.destroyAllWindows()
print("Camera stream closed successfully.")
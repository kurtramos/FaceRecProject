import base64
import os
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
# This allows your HTML file to send data to this server without being blocked
CORS(app) 

# Your exact local directory
SAVE_DIR = r"C:\Users\user\Desktop\FaceRecProject\employees"

@app.route('/register', methods=['POST'])
def register_personnel():
    try:
        data = request.json
        
        person_id = data.get('person_id')
        b64_image_data = data.get('face_image')
        
        if not person_id or not b64_image_data:
            return jsonify({"error": "Missing ID or Image"}), 400

        # The image comes from the HTML as "data:image/jpeg;base64,/9j/4AAQSkZJ..."
        # We need to split it at the comma and only decode the actual data part
        encoded_data = b64_image_data.split(',')[1]
        
        # Format the file name
        file_name = f"{person_id}.jpg"
        file_path = os.path.join(SAVE_DIR, file_name)
        
        # Decode the base64 string and write it as an image file
        with open(file_path, "wb") as fh:
            fh.write(base64.b64decode(encoded_data))
            
        print(f"Success: Saved {file_name} to {SAVE_DIR}")
        return jsonify({"message": "Successfully saved locally!"}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Ensure the directory exists before trying to save to it
    os.makedirs(SAVE_DIR, exist_ok=True)
    # Run the local server
    app.run(port=5000, debug=True)
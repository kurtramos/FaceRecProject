import base64
import os
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
# Explicitly allow all origins so your HTML can connect from anywhere
CORS(app, resources={r"/*": {"origins": "*"}}) 

# Your exact local directory
SAVE_DIR = r"C:\Users\user\Desktop\FaceRecProject\employees"
DB_PATH = os.path.join(SAVE_DIR, "employees.db")

def init_db():
    os.makedirs(SAVE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS employees
                 (person_id TEXT PRIMARY KEY, name TEXT, role TEXT)''')
    conn.commit()
    conn.close()

@app.route('/image/<filename>', methods=['GET'])
def get_image(filename):
    return send_from_directory(SAVE_DIR, filename)

@app.route('/register', methods=['POST'])
def register_personnel():
    try:
        data = request.json
        person_id = data.get('person_id')
        name = data.get('name')
        role = data.get('role')
        b64_image_data = data.get('face_image')
        
        if not person_id or not b64_image_data:
            return jsonify({"error": "Missing ID or Image"}), 400

        file_name = f"{person_id}.jpg"
        file_path = os.path.join(SAVE_DIR, file_name)
        
        if os.path.exists(file_path):
            return jsonify({"error": f"Registration failed: '{file_name}' already exists locally!"}), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT person_id FROM employees WHERE person_id=?", (person_id,))
        if c.fetchone():
            conn.close()
            return jsonify({"error": f"Registration failed: Person ID '{person_id}' is already in the database!"}), 400

        encoded_data = b64_image_data.split(',')[1]
        with open(file_path, "wb") as fh:
            fh.write(base64.b64decode(encoded_data))
            
        c.execute("INSERT INTO employees (person_id, name, role) VALUES (?, ?, ?)", (person_id, name, role))
        conn.commit()
        conn.close()
            
        print(f"Success: Registered {name} ({person_id}) to database.")
        return jsonify({"message": "Successfully saved locally!"}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/employees', methods=['GET'])
def get_employees():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT person_id, name, role FROM employees")
        rows = c.fetchall()
        conn.close()
        
        employees = [{"person_id": r[0], "name": r[1], "role": r[2]} for r in rows]
        return jsonify(employees), 200
    except Exception as e:
        print(f"Error fetching directory: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/delete/<person_id>', methods=['DELETE'])
def delete_personnel(person_id):
    try:
        file_name = f"{person_id}.jpg"
        file_path = os.path.join(SAVE_DIR, file_name)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted image: {file_name}")
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM employees WHERE person_id=?", (person_id,))
        rows_deleted = c.rowcount 
        conn.commit()
        conn.close()
        
        if rows_deleted > 0:
            return jsonify({"message": f"Successfully deleted {person_id}."}), 200
        else:
            return jsonify({"error": f"Person ID '{person_id}' not found in database."}), 404

    except Exception as e:
        print(f"Error during deletion: {e}")
        return jsonify({"error": str(e)}), 500

# --- NEW: BULK DELETE ROUTE ---
@app.route('/delete_bulk', methods=['POST'])
def delete_bulk():
    try:
        data = request.json
        person_ids = data.get('person_ids', [])
        
        if not person_ids:
            return jsonify({"error": "No IDs provided for deletion."}), 400

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        deleted_count = 0

        for pid in person_ids:
            # 1. Delete Image
            file_path = os.path.join(SAVE_DIR, f"{pid}.jpg")
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # 2. Delete Database Record
            c.execute("DELETE FROM employees WHERE person_id=?", (pid,))
            deleted_count += c.rowcount

        conn.commit()
        conn.close()
        
        return jsonify({"message": f"Successfully deleted {deleted_count} personnel."}), 200
    except Exception as e:
        print(f"Bulk delete error: {e}")
        return jsonify({"error": str(e)}), 500

# --- NEW: DELETE ALL ROUTE ---
@app.route('/delete_all', methods=['DELETE'])
def delete_all():
    try:
        # 1. Delete all .jpg files in the directory
        for filename in os.listdir(SAVE_DIR):
            if filename.endswith(".jpg"):
                os.remove(os.path.join(SAVE_DIR, filename))
                
        # 2. Clear the database table completely
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM employees")
        conn.commit()
        conn.close()
        
        print("Success: Wiped all local data.")
        return jsonify({"message": "Successfully wiped all personnel data."}), 200
    except Exception as e:
        print(f"Delete all error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(port=5000, debug=True)
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)

MONGO_URI = os.environ.get("mongodb+srv://morashiftuom_db_user:I4bv4bmEr2jyazJ4@morashift.jqcplby.mongodb.net/?appName=morashift")

# Lazy DB initialisation — avoids crashing the Vercel serverless
# function at module load time when env vars may not yet be injected.
_client = None
_db = None
students_collection      = None
doctors_collection       = None
labassistants_collection = None

def _init_db():
    global _client, _db, students_collection, doctors_collection, labassistants_collection
    if _db is not None:
        return  # already initialised
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI environment variable is not set.")
    _client = MongoClient(MONGO_URI)
    _db = _client["unimed_db"]
    students_collection      = _db["students"]
    doctors_collection       = _db["doctors"]
    labassistants_collection = _db["labassistants"]
    # ── Hash indexes for O(1) lookup speed ──
    students_collection.create_index("indexNumber", unique=True)
    doctors_collection.create_index("doctorId",     unique=True)
    labassistants_collection.create_index("labId",  unique=True)

@app.before_request
def ensure_db():
    try:
        _init_db()
    except RuntimeError as e:
        from flask import abort
        app.logger.error(str(e))
        abort(500, description=str(e))


# ─────────────────────────────────────────────
#  Helper: verify password (handles plain-text
#  legacy passwords and auto-upgrades to hash)
# ─────────────────────────────────────────────

def _verify_and_upgrade(collection, query, field, incoming_password):
    """
    Returns (True, doc) if password matches, (False, doc) otherwise.
    If the stored value is plain-text and matches, it is transparently
    upgraded to a bcrypt hash in the DB.
    """
    doc = collection.find_one(query)
    if not doc:
        return False, None
    stored = doc.get(field, "")

    # Check if stored value is already a werkzeug hash
    if stored.startswith("pbkdf2:") or stored.startswith("scrypt:"):
        ok = check_password_hash(stored, incoming_password)
    else:
        # Legacy plain-text — compare directly, then upgrade
        ok = (stored == incoming_password)
        if ok:
            new_hash = generate_password_hash(incoming_password)
            collection.update_one(query, {"$set": {field: new_hash}})

    return ok, doc


# ─────────────────────────────────────────────
#  STUDENT ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/student/<index_number>', methods=['GET'])
def retrieve_student(index_number):
    index_number = index_number.upper()
    student = students_collection.find_one({"indexNumber": index_number}, {"_id": 0, "password": 0})
    if student:
        return jsonify(student), 200
    return jsonify({"error": "Not found"}), 404

@app.route('/student/<index_number>/record', methods=['POST'])
def save_visit_details(index_number):
    index_number = index_number.upper()
    data = request.json
    new_record = {
        "diagnosis":    data.get("diagnosis", ""),
        "prescription": data.get("prescription", ""),
        "timestamp":    datetime.now()
    }
    result = students_collection.update_one(
        {"indexNumber": index_number},
        {"$push": {"medicalRecords": new_record}}
    )
    if result.matched_count > 0:
        return jsonify({"message": "Success"}), 200
    return jsonify({"error": "Not found"}), 404

@app.route('/student', methods=['POST'])
def register_student():
    data = request.json
    index_number = data.get("indexNumber").upper() if data.get("indexNumber") else None
    existing = students_collection.find_one({"indexNumber": index_number})
    if existing:
        students_collection.update_one(
            {"indexNumber": index_number},
            {"$set": {"name": data.get("name", existing.get("name", ""))}}
        )
        return jsonify({"message": "Updated"}), 200
    new_student = {
        "indexNumber":    index_number,
        "name":           data.get("name", ""),
        "password":       generate_password_hash("student123"),   # hashed default
        "medicalRecords": []
    }
    students_collection.insert_one(new_student)
    return jsonify({"message": "Created"}), 201

@app.route('/student/<index_number>/login', methods=['POST'])
def student_login(index_number):
    index_number = index_number.upper()
    data = request.json
    
    # Auto-registration flow
    student = students_collection.find_one({"indexNumber": index_number})
    if not student:
        new_student = {
            "indexNumber":    index_number,
            "name":           "",
            "password":       generate_password_hash(data.get("password", "")),
            "medicalRecords": []
        }
        students_collection.insert_one(new_student)
        return jsonify({"message": "Created and logged in", "name": ""}), 200

    ok, student = _verify_and_upgrade(
        students_collection,
        {"indexNumber": index_number},
        "password",
        data.get("password", "")
    )
    if student is None:
        return jsonify({"error": "Not found"}), 404
    if ok:
        return jsonify({"message": "Login successful", "name": student.get("name", "")}), 200
    return jsonify({"error": "Incorrect password"}), 401

@app.route('/student/<index_number>/password', methods=['PUT'])
def update_student_password(index_number):
    index_number = index_number.upper()
    data = request.json
    ok, student = _verify_and_upgrade(
        students_collection,
        {"indexNumber": index_number},
        "password",
        data.get("oldPassword", "")
    )
    if student is None:
        return jsonify({"error": "Not found"}), 404
    if not ok:
        return jsonify({"error": "Incorrect current password"}), 401
    students_collection.update_one(
        {"indexNumber": index_number},
        {"$set": {"password": generate_password_hash(data.get("newPassword", ""))}}
    )
    return jsonify({"message": "Password updated"}), 200


# ─────────────────────────────────────────────
#  DOCTOR ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/doctors', methods=['GET'])
def list_doctors():
    doctors = list(doctors_collection.find({}, {"_id": 0, "password": 0}))
    return jsonify(doctors), 200

@app.route('/doctors/<doctor_id>', methods=['GET'])
def retrieve_doctor(doctor_id):
    doctor = doctors_collection.find_one({"doctorId": doctor_id}, {"_id": 0, "password": 0})
    if doctor:
        return jsonify(doctor), 200
    return jsonify({"error": "Not found"}), 404

@app.route('/doctors', methods=['POST'])
def register_doctor():
    data = request.json
    doctor_id = data.get("doctorId")
    if not doctor_id:
        return jsonify({"error": "doctorId is required"}), 400
    if doctors_collection.find_one({"doctorId": doctor_id}):
        return jsonify({"error": "Doctor ID already exists"}), 409
    new_doctor = {
        "doctorId":  doctor_id,
        "name":      data.get("name", ""),
        "password":  generate_password_hash(data.get("password", "doctor123")),  # hashed
        "createdAt": datetime.now()
    }
    doctors_collection.insert_one(new_doctor)
    return jsonify({"message": "Doctor registered"}), 201

@app.route('/doctors/<doctor_id>/login', methods=['POST'])
def doctor_login(doctor_id):
    data = request.json
    ok, doctor = _verify_and_upgrade(
        doctors_collection,
        {"doctorId": doctor_id},
        "password",
        data.get("password", "")
    )
    if doctor is None:
        return jsonify({"error": "Not found"}), 404
    if ok:
        return jsonify({"message": "Login successful", "name": doctor.get("name", "")}), 200
    return jsonify({"error": "Incorrect password"}), 401

@app.route('/doctors/<doctor_id>/password', methods=['PUT'])
def update_doctor_password(doctor_id):
    data = request.json
    ok, doctor = _verify_and_upgrade(
        doctors_collection,
        {"doctorId": doctor_id},
        "password",
        data.get("oldPassword", "")
    )
    if doctor is None:
        return jsonify({"error": "Not found"}), 404
    if not ok:
        return jsonify({"error": "Incorrect current password"}), 401
    doctors_collection.update_one(
        {"doctorId": doctor_id},
        {"$set": {"password": generate_password_hash(data.get("newPassword", ""))}}
    )
    return jsonify({"message": "Password updated"}), 200


# ─────────────────────────────────────────────
#  LAB ASSISTANT ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/labassistant', methods=['GET'])
def list_labassistants():
    assistants = list(labassistants_collection.find({}, {"_id": 0, "password": 0}))
    return jsonify(assistants), 200

@app.route('/labassistant/<lab_id>', methods=['GET'])
def retrieve_labassistant(lab_id):
    assistant = labassistants_collection.find_one({"labId": lab_id}, {"_id": 0, "password": 0})
    if assistant:
        return jsonify(assistant), 200
    return jsonify({"error": "Not found"}), 404

@app.route('/labassistant', methods=['POST'])
def register_labassistant():
    data = request.json
    lab_id = data.get("labId")
    if not lab_id:
        return jsonify({"error": "labId is required"}), 400
    if labassistants_collection.find_one({"labId": lab_id}):
        return jsonify({"error": "Lab Assistant ID already exists"}), 409
    new_assistant = {
        "labId":     lab_id,
        "name":      data.get("name", ""),
        "password":  generate_password_hash(data.get("password", "lab123")),  # hashed
        "createdAt": datetime.now()
    }
    labassistants_collection.insert_one(new_assistant)
    return jsonify({"message": "Lab Assistant registered"}), 201

@app.route('/labassistant/<lab_id>/login', methods=['POST'])
def labassistant_login(lab_id):
    data = request.json
    ok, assistant = _verify_and_upgrade(
        labassistants_collection,
        {"labId": lab_id},
        "password",
        data.get("password", "")
    )
    if assistant is None:
        return jsonify({"error": "Not found"}), 404
    if ok:
        return jsonify({"message": "Login successful", "name": assistant.get("name", "")}), 200
    return jsonify({"error": "Incorrect password"}), 401

@app.route('/labassistant/<lab_id>/password', methods=['PUT'])
def update_labassistant_password(lab_id):
    data = request.json
    ok, assistant = _verify_and_upgrade(
        labassistants_collection,
        {"labId": lab_id},
        "password",
        data.get("oldPassword", "")
    )
    if assistant is None:
        return jsonify({"error": "Not found"}), 404
    if not ok:
        return jsonify({"error": "Incorrect current password"}), 401
    labassistants_collection.update_one(
        {"labId": lab_id},
        {"$set": {"password": generate_password_hash(data.get("newPassword", ""))}}
    )
    return jsonify({"message": "Password updated"}), 200


# ─────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

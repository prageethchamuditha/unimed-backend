import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["unimed_db"]

students_collection      = db["students"]
doctors_collection       = db["doctors"]
labassistants_collection = db["labassistants"]
reset_requests_collection = db["reset_requests"]

# ─────────────────────────────────────────────
#  Hash indexes for O(1) lookup speed
# ─────────────────────────────────────────────
students_collection.create_index("indexNumber", unique=True)
doctors_collection.create_index("doctorId",     unique=True)
labassistants_collection.create_index("labId",  unique=True)
reset_requests_collection.create_index("indexNumber")


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
    student = students_collection.find_one({"indexNumber": index_number}, {"_id": 0, "password": 0})
    if student:
        return jsonify(student), 200
    return jsonify({"error": "Not found"}), 404

@app.route('/student/<index_number>/record', methods=['POST'])
def save_visit_details(index_number):
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
    index_number = data.get("indexNumber")
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
    data = request.json
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
#  PASSWORD RESET REQUEST ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/reset-request', methods=['POST'])
def submit_reset_request():
    """Student submits a password reset request with ID card image."""
    data = request.json
    index_number = data.get("indexNumber", "").strip()
    full_name    = data.get("fullName", "").strip()
    id_card_image = data.get("idCardImage", "")   # base64 data URL

    if not index_number or not full_name or not id_card_image:
        return jsonify({"error": "indexNumber, fullName and idCardImage are required"}), 400

    # Prevent duplicate pending requests
    existing = reset_requests_collection.find_one(
        {"indexNumber": index_number, "status": "pending"}
    )
    if existing:
        return jsonify({"message": "Request already pending"}), 200

    new_request = {
        "indexNumber":  index_number,
        "fullName":     full_name,
        "idCardImage":  id_card_image,
        "status":       "pending",       # pending | approved | rejected
        "rejectionReason": "",
        "submittedAt":  datetime.now()
    }
    result = reset_requests_collection.insert_one(new_request)
    return jsonify({"message": "Reset request submitted", "id": str(result.inserted_id)}), 201


@app.route('/reset-requests', methods=['GET'])
def list_reset_requests():
    """Lab assistant fetches all reset requests (newest first)."""
    from bson import ObjectId
    status_filter = request.args.get("status", "pending")
    query = {} if status_filter == "all" else {"status": status_filter}
    requests_list = list(
        reset_requests_collection.find(query, {"idCardImage": 0})
        .sort("submittedAt", -1)
    )
    # Convert ObjectId to string for JSON
    for r in requests_list:
        r["_id"] = str(r["_id"])
    return jsonify(requests_list), 200


@app.route('/reset-requests/<request_id>', methods=['GET'])
def get_reset_request(request_id):
    """Get a single reset request including the ID card image."""
    from bson import ObjectId
    try:
        req = reset_requests_collection.find_one({"_id": ObjectId(request_id)})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    if not req:
        return jsonify({"error": "Not found"}), 404
    req["_id"] = str(req["_id"])
    return jsonify(req), 200


@app.route('/reset-requests/<request_id>/approve', methods=['POST'])
def approve_reset_request(request_id):
    """Lab assistant approves request — resets student password to default."""
    from bson import ObjectId
    try:
        req = reset_requests_collection.find_one({"_id": ObjectId(request_id)})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    if not req:
        return jsonify({"error": "Request not found"}), 404

    # Reset the student's password to default
    students_collection.update_one(
        {"indexNumber": req["indexNumber"]},
        {"$set": {"password": generate_password_hash("student123")}}
    )
    # Mark request as approved
    reset_requests_collection.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": "approved", "resolvedAt": datetime.now()}}
    )
    return jsonify({"message": "Approved — password reset to student123"}), 200


@app.route('/reset-requests/<request_id>/reject', methods=['POST'])
def reject_reset_request(request_id):
    """Lab assistant rejects the reset request."""
    from bson import ObjectId
    data = request.json or {}
    try:
        req = reset_requests_collection.find_one({"_id": ObjectId(request_id)})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    if not req:
        return jsonify({"error": "Request not found"}), 404

    reset_requests_collection.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {
            "status": "rejected",
            "rejectionReason": data.get("reason", ""),
            "resolvedAt": datetime.now()
        }}
    )
    return jsonify({"message": "Request rejected"}), 200


# ─────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

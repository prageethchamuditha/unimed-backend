import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)
CORS(app)

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["unimed_db"]

students_collection    = db["students"]
doctors_collection     = db["doctors"]
labassistants_collection = db["labassistants"]

# ─────────────────────────────────────────────
#  STUDENT ENDPOINTS  (unchanged)
# ─────────────────────────────────────────────

@app.route('/student/<index_number>', methods=['GET'])
def retrieve_student(index_number):
    student = students_collection.find_one({"indexNumber": index_number}, {"_id": 0})
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
    new_student = {
        "indexNumber":    data.get("indexNumber"),
        "name":           data.get("name"),
        "medicalRecords": []
    }
    students_collection.insert_one(new_student)
    return jsonify({"message": "Created"}), 201

# ─────────────────────────────────────────────
#  DOCTOR ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/doctors', methods=['GET'])
def list_doctors():
    """List all doctors (passwords excluded)."""
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
    """Register a new doctor account."""
    data = request.json
    doctor_id = data.get("doctorId")
    if not doctor_id:
        return jsonify({"error": "doctorId is required"}), 400
    if doctors_collection.find_one({"doctorId": doctor_id}):
        return jsonify({"error": "Doctor ID already exists"}), 409
    new_doctor = {
        "doctorId": doctor_id,
        "name":     data.get("name", ""),
        "password": data.get("password", "doctor123"),   # default password
        "createdAt": datetime.now()
    }
    doctors_collection.insert_one(new_doctor)
    return jsonify({"message": "Doctor registered"}), 201

@app.route('/doctors/<doctor_id>/login', methods=['POST'])
def doctor_login(doctor_id):
    """Verify doctor password."""
    data = request.json
    doctor = doctors_collection.find_one({"doctorId": doctor_id})
    if not doctor:
        return jsonify({"error": "Not found"}), 404
    if doctor.get("password") == data.get("password"):
        return jsonify({"message": "Login successful", "name": doctor.get("name", "")}), 200
    return jsonify({"error": "Incorrect password"}), 401

@app.route('/doctors/<doctor_id>/password', methods=['PUT'])
def update_doctor_password(doctor_id):
    """Change doctor password."""
    data = request.json
    old_pwd = data.get("oldPassword")
    new_pwd = data.get("newPassword")
    doctor = doctors_collection.find_one({"doctorId": doctor_id})
    if not doctor:
        return jsonify({"error": "Not found"}), 404
    if doctor.get("password") != old_pwd:
        return jsonify({"error": "Incorrect current password"}), 401
    doctors_collection.update_one({"doctorId": doctor_id}, {"$set": {"password": new_pwd}})
    return jsonify({"message": "Password updated"}), 200

# ─────────────────────────────────────────────
#  LAB ASSISTANT ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/labassistant', methods=['GET'])
def list_labassistants():
    """List all lab assistants (passwords excluded)."""
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
    """Register a new lab assistant account."""
    data = request.json
    lab_id = data.get("labId")
    if not lab_id:
        return jsonify({"error": "labId is required"}), 400
    if labassistants_collection.find_one({"labId": lab_id}):
        return jsonify({"error": "Lab Assistant ID already exists"}), 409
    new_assistant = {
        "labId":     lab_id,
        "name":      data.get("name", ""),
        "password":  data.get("password", "lab123"),    # default password
        "createdAt": datetime.now()
    }
    labassistants_collection.insert_one(new_assistant)
    return jsonify({"message": "Lab Assistant registered"}), 201

@app.route('/labassistant/<lab_id>/login', methods=['POST'])
def labassistant_login(lab_id):
    """Verify lab assistant password."""
    data = request.json
    assistant = labassistants_collection.find_one({"labId": lab_id})
    if not assistant:
        return jsonify({"error": "Not found"}), 404
    if assistant.get("password") == data.get("password"):
        return jsonify({"message": "Login successful", "name": assistant.get("name", "")}), 200
    return jsonify({"error": "Incorrect password"}), 401

@app.route('/labassistant/<lab_id>/password', methods=['PUT'])
def update_labassistant_password(lab_id):
    """Change lab assistant password."""
    data = request.json
    old_pwd = data.get("oldPassword")
    new_pwd = data.get("newPassword")
    assistant = labassistants_collection.find_one({"labId": lab_id})
    if not assistant:
        return jsonify({"error": "Not found"}), 404
    if assistant.get("password") != old_pwd:
        return jsonify({"error": "Incorrect current password"}), 401
    labassistants_collection.update_one({"labId": lab_id}, {"$set": {"password": new_pwd}})
    return jsonify({"message": "Password updated"}), 200

# ─────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

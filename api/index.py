import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)
CORS(app)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://morashiftuom_db_user:I4bv4bmEr2jyazJ4@morashift.jqcplby.mongodb.net/?appName=morashift")
client = MongoClient(MONGO_URI)
db = client["unimed_db"]
students_collection = db["students"]

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "UniMed API is running"}), 200

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
        "diagnosis": data.get("diagnosis", ""),
        "prescription": data.get("prescription", ""),
        "timestamp": datetime.now()
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
        "indexNumber": data.get("indexNumber"),
        "name": data.get("name"),
        "medicalRecords": []
    }
    students_collection.insert_one(new_student)
    return jsonify({"message": "Created"}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

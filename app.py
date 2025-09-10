from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime

app = Flask(__name__)

# Get DB URL from environment variable (Render sets it as DATABASE_URL)
DATABASE_URL = os.environ.get("DATABASE_URL")

# Set up SQLAlchemy
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define table
class PowerData(Base):
    __tablename__ = "power_data"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False)
    power_kW = Column(Float, nullable=False)

# Create tables if not exists
Base.metadata.create_all(bind=engine)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("Received data:", data)

    # Support single object or list
    if isinstance(data, dict):
        data = [data]

    session = SessionLocal()
    try:
        for entry in data:
            ts = entry.get("timestamp")
            pw = entry.get("power_kW")
            if ts and pw:
                record = PowerData(
                    timestamp=datetime.fromisoformat(ts.replace("Z", "+00:00")),
                    power_kW=float(pw)
                )
                session.add(record)
        session.commit()
    finally:
        session.close()

    return jsonify({"status": "success"}), 200

@app.route("/data", methods=["GET"])
def get_data():
    session = SessionLocal()
    try:
        results = session.query(PowerData).order_by(PowerData.timestamp).all()
        output = [
            {"timestamp": r.timestamp.isoformat(), "power_kW": r.power_kW}
            for r in results
        ]
    finally:
        session.close()
    return jsonify(output), 200

@app.route("/")
def home():
    return "Webhook server with PostgreSQL is running!", 200

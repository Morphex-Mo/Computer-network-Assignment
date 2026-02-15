from flask import Flask, request, jsonify
import hashlib
import json

app = Flask(__name__)

# In-memory tracker database to store info_hash, file names, and seeder details
TRACKER_DB = {}

@app.route("/announce", methods=["GET", "POST"])
def announce():
    """Handle announcements from seeders."""
    if request.method == "POST":
        data = request.get_json()
        info_hash = data.get("info_hash")  # 40 hexadecimal digits
        peer_ip = data.get("peer_ip")      # Seeder's IP address
        peer_port = data.get("peer_port")  # Seeder's port
        file_name = data.get("file_name")  # Name of the shared file

        # Validate input
        if not all([info_hash, peer_ip, peer_port, file_name]):
            return jsonify({"error": "Missing required fields"}), 400

        # Store the seeder info in TRACKER_DB
        if info_hash not in TRACKER_DB:
            TRACKER_DB[info_hash] = {
                "file_name": file_name,
                "seeders": []
            }
        seeder_info = {"ip": peer_ip, "port": peer_port}
        if seeder_info not in TRACKER_DB[info_hash]["seeders"]:
            TRACKER_DB[info_hash]["seeders"].append(seeder_info)

        return jsonify({"status": "success", "message": "Seeder registered"}), 200
    return jsonify({"error": "Use POST method"}), 405

@app.route("/get_peers", methods=["GET"])
def get_seeders():
    """Get the list of seeders for a given info_hash."""
    info_hash = request.args.get("info_hash")
    if not info_hash or info_hash not in TRACKER_DB:
        return jsonify({"error": "Invalid or unknown info_hash"}), 404

    return jsonify({
        "file_name": TRACKER_DB[info_hash]["file_name"],
        "seeders": TRACKER_DB[info_hash]["seeders"]
    }), 200

@app.route("/show_tracker_data", methods=["GET"])
def show_tracker_data():
    """Show the entire tracker data."""
    return jsonify(TRACKER_DB), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
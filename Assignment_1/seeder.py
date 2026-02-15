import os
import requests
import threading
import hashlib
import bencodepy
import shutil
from flask import Flask, request, send_file

TRACKER_URL = "http://127.0.0.1:5001"
app = Flask(__name__)

def get_peer_folder(port):
    """Returns the folder path for a specific peer and ensures it exists."""
    folder = f"peer_{port}"
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder

def create_torrent(file_name):
    """Create a .torrent file for the given file."""
    if not os.path.exists(file_name):
        raise FileNotFoundError(f"File {file_name} does not exist")

    # Prepare torrent metadata
    with open(file_name, "rb") as f:
        file_content = f.read()
    piece_length = 1024 * 1024  # 1MB pieces
    pieces = [file_content[i:i + piece_length] for i in range(0, len(file_content), piece_length)]
    piece_hashes = b"".join(hashlib.sha1(piece).digest() for piece in pieces)

    torrent_data = {
        "announce": TRACKER_URL + "/announce",
        "info": {
            "length": os.path.getsize(file_name),
            "name": os.path.basename(file_name),
            "piece length": piece_length,
            "pieces": piece_hashes
        }
    }

    # Encode and write to .torrent file
    torrent_file = f"{os.path.splitext(file_name)[0]}.torrent"
    with open(torrent_file, "wb") as f:
        f.write(bencodepy.encode(torrent_data))

    # Copy to requester folder for simplicity
    requester_folder = get_peer_folder(6882)
    shutil.copy(torrent_file, requester_folder)
    return torrent_file

def get_info_hash(torrent_file_path):
    """Returns the info_hash and piece list of the torrent file."""
    try:
        with open(torrent_file_path, "rb") as f:
            decoded_data = bencodepy.decode(f.read())
        info_dict = decoded_data[b"info"]
        info_bencoded = bencodepy.encode(info_dict)
        info_hash = hashlib.sha1(info_bencoded).hexdigest()  # 40 hex digits
        piece_list = [info_dict[b"pieces"][i:i+20] for i in range(0, len(info_dict[b"pieces"]), 20)]
        return info_hash, piece_list
    except Exception as e:
        print(f"Error getting info_hash from {torrent_file_path}: {e}")
        return None, []

def announce_to_tracker(info_hash, port, shared_files):
    """Sends an announcement to the tracker with the peer's shared files."""
    params = {
        "info_hash": info_hash,
        "peer_ip": "127.0.0.1",
        "peer_port": port,
        "file_name": shared_files
    }
    try:
        response = requests.post(TRACKER_URL + "/announce", json=params)
        response.raise_for_status()
        print(f"Announced to tracker: {response.json()}")
    except Exception as e:
        print(f"Failed to announce to tracker: {e}")

@app.route("/download", methods=["GET"])
def download():
    """Serves a file to other peers upon request."""
    file_name = request.args.get("file_name")
    peer_folder = get_peer_folder(6881)
    file_path = os.path.join(peer_folder, file_name)
    if os.path.exists(file_path):
        return send_file(file_path)
    return jsonify({"error": "File not found"}), 404

def run_peer():
    """Starts the seeder's server and announces it to the tracker."""
    port = 6881
    peer_folder = get_peer_folder(port)
    shared_file = "example.txt"

    # Copy shared file to seeder folder instead of moving it
    if os.path.exists(shared_file):
        shutil.copy(shared_file, os.path.join(peer_folder, shared_file))  # 修改：从 move 改为 copy

    print(f"Peer running on port {port}, sharing folder: {peer_folder}")

    # Create torrent file
    torrent_file = create_torrent(os.path.join(peer_folder, shared_file))

    # Get info_hash and announce to tracker
    info_hash, _ = get_info_hash(torrent_file)
    if info_hash:
        announce_to_tracker(info_hash, port, shared_file)

    # Start Flask server
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)).start()
    print("Peer is running. You can now request or download the file.")

if __name__ == "__main__":
    run_peer()
import os
import requests
import hashlib
import bencodepy
from flask import Flask, request, send_file

TRACKER_URL = "http://127.0.0.1:5001"
app = Flask(__name__)

def get_peer_folder(port):
    """Returns the folder path for a specific peer and ensures it exists."""
    folder = f"peer_{port}"
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder

def get_info_hash(torrent_file_path):
    """Returns the info_hash and piece list of the torrent file."""
    try:
        with open(torrent_file_path, "rb") as f:
            decoded_data = bencodepy.decode(f.read())
        info_dict = decoded_data[b"info"]
        info_bencoded = bencodepy.encode(info_dict)
        info_hash = hashlib.sha1(info_bencoded).hexdigest()
        piece_list = [info_dict[b"pieces"][i:i+20] for i in range(0, len(info_dict[b"pieces"]), 20)]
        return info_hash, piece_list
    except Exception as e:
        print(f"Error getting info_hash from {torrent_file_path}: {e}")
        return None, []

def get_seeders_from_tracker(info_hash):
    """Requests the tracker for a list of seeders with the given info_hash."""
    try:
        response = requests.get(TRACKER_URL + "/get_peers", params={"info_hash": info_hash})
        response.raise_for_status()
        data = response.json()
        return data["seeders"], data["file_name"]
    except Exception as e:
        print(f"Error retrieving peers from tracker: {e}")
        return [], None

def download_file(file_name, peer_ip, peer_port, local_port):
    """Downloads a file from another peer and saves it in this peer's folder."""
    try:
        url = f"http://{peer_ip}:{peer_port}/download"
        response = requests.get(url, params={"file_name": file_name})
        response.raise_for_status()
        peer_folder = get_peer_folder(local_port)
        file_path = os.path.join(peer_folder, file_name)
        with open(file_path, "wb") as f:
            f.write(response.content)
        print(f"File {file_name} downloaded to {file_path}")
    except Exception as e:
        print(f"⚠️ Error downloading file: {e}")

def request_file(info_hash):
    """Requests a file from other peers based on info_hash."""
    print(f"🔍 Fetching peers for info_hash: {info_hash}...")
    seeders, file_name = get_seeders_from_tracker(info_hash)
    if not seeders:
        print("No seeders found.")
        return
    seeder = seeders[0]  # Use the first seeder
    download_file(file_name, seeder["ip"], seeder["port"], 6882)

def run_peer():
    """Starts the requester's server."""
    port = 6882
    peer_folder = get_peer_folder(port)
    print(f"Peer running on port {port}, sharing folder: {peer_folder}")

    # Prompt user for torrent file path
    torrent_file_path = os.path.join(peer_folder, "example.torrent")
    if not os.path.exists(torrent_file_path):
        print(f"Torrent file {torrent_file_path} not found in {peer_folder}")
        return

    # Get info_hash and request file
    info_hash, _ = get_info_hash(torrent_file_path)
    if info_hash:
        request_file(info_hash)

    print("Peer is running. You can now request or download the file.")

if __name__ == "__main__":
    run_peer()
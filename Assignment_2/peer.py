import socket, threading, argparse, os, json, time, struct, random, zlib

# --- Constants ---
SEGMENT_SIZE = 512
ACK_TIMEOUT = 0.5
DROP_PROBABILITY = 0.05  # Reduced to 1% for better reliability
ERROR_PROBABILITY = 0.05  # Reduced to 1% for better reliability
WINDOW_SIZE = 4
MAX_RETRIES = 8  # Increased for more chancesS
RECV_DIR = 'files'
COST_UPDATE_INTERVAL = 60
INITIAL_TTL = 10

# --- Global State ---
peer_sock = None
reassembly_buffers = {}
reassembly_expected = {}
unacked_segments = {}
retry_counts = {}
segments_cache = {}
lock = threading.Lock()

distance_vector = {}
link_costs = {}
neighbor_dv_tables = {}
dv_lock = threading.Lock()

# --- Packet Helpers ---
def make_packet(pkt_type, seq, total, src, dst, ttl, payload):
    checksum = zlib.crc32(payload) & 0xffffffff
    header = {"type": pkt_type, "seq": seq, "total": total,
              "src": src, "dst": dst, "ttl": ttl, "checksum": checksum}
    header_bytes = json.dumps(header).encode()
    return struct.pack("!I", len(header_bytes)) + header_bytes + payload

def parse_packet(data):
    header_len = struct.unpack("!I", data[:4])[0]
    header = json.loads(data[4:4+header_len].decode())
    payload = data[4+header_len:]
    return header, payload

# --- Listener and Packet Receiver ---
def listen(peer_id, ip, port, peers):
    global peer_sock
    peer_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer_sock.bind((ip, port))
    print(f"[{peer_id}] Listening on {ip}:{port}")
    while True:
        data, _ = peer_sock.recvfrom(4096)
        handle_packet(data, peer_id, peers)

def handle_packet(data, peer_id, peers):
    header, payload = parse_packet(data)
    if random.random() < DROP_PROBABILITY:
        print(f"[{peer_id}] Dropped packet (simulated)")
        return
    if header['type'] == 'DATA' and random.random() < ERROR_PROBABILITY and payload:
        i = random.randrange(len(payload))
        payload = payload[:i] + bytes([(payload[i] + 1) % 256]) + payload[i+1:]
    if zlib.crc32(payload) & 0xffffffff != header['checksum']:
        print(f"[{peer_id}] Checksum mismatch, dropping packet")
        return
    if header['ttl'] <= 0:
        print(f"[{peer_id}] TTL expired, dropping packet")
        return

    pkt_type = header['type']
    src = header['src']
    dst = header['dst']
    seq = header['seq']
    total = header['total']
    ttl = header['ttl'] - 1

    if pkt_type == 'DATA':
        if dst == peer_id:
            print(f"[{peer_id}] Received DATA segment {seq}/{total} from {src}")
            store_segment(peer_id, seq, total, payload)
            send_ack(peer_id, src, seq, peers)
        else:
            nh = get_next_hop(peer_id, dst)
            if nh and ttl > 0:
                pkt = make_packet('DATA', seq, total, src, dst, ttl, payload)
                peer_sock.sendto(pkt, tuple(peers[nh]))
                print(f"[{peer_id}] Forwarded DATA segment {seq} to {nh}")

    elif pkt_type == 'ACK':
        if dst == peer_id:
            print(f"[{peer_id}] Received ACK for segment {seq} from {src}")
            with lock:
                unacked_segments.pop(seq, None)
                retry_counts.pop(seq, None)
        else:
            nh = get_next_hop(peer_id, dst)
            if nh and ttl > 0:
                pkt = make_packet('ACK', seq, 0, src, dst, ttl, b'')
                peer_sock.sendto(pkt, tuple(peers[nh]))
                print(f"[{peer_id}] Forwarded ACK for segment {seq} to {nh}")

    elif pkt_type == 'DV':
        if dst == peer_id:
            handle_dv_update(peer_id, src, payload, peers)
        else:
            nh = get_next_hop(peer_id, dst)
            if nh and ttl > 0:
                pkt = make_packet('DV', seq, total, src, dst, ttl, payload)
                peer_sock.sendto(pkt, tuple(peers[nh]))

# --- File Transmission ---
def send_file(peer_id, dst, filename, peers):
    global segments_cache
    try:
        with open(filename, 'rb') as f:
            data = f.read()
        total = (len(data) + SEGMENT_SIZE - 1) // SEGMENT_SIZE
        segments_cache = {i: data[i * SEGMENT_SIZE:(i + 1) * SEGMENT_SIZE] for i in range(total)}
        with lock:
            unacked_segments.clear()
            retry_counts.clear()
            for i in range(total):
                unacked_segments[i] = True
        print(f"[{peer_id}] Sending {total} segments to {dst}")
        threading.Thread(target=ack_timekeeping, args=(peer_id, dst, peers, total), daemon=True).start()
        base = 0
        while base < total:
            next_seq = base
            while next_seq < min(base + WINDOW_SIZE, total):
                if next_seq in unacked_segments:
                    send_segment(peer_id, dst, segments_cache[next_seq], next_seq, peers, total)
                    print(f"[{peer_id}] Sent segment {next_seq}/{total}")
                next_seq += 1
            time.sleep(ACK_TIMEOUT)
            with lock:
                while base < total and base not in unacked_segments:
                    base += 1
                    print(f"[{peer_id}] Advanced base to {base}")
        max_wait = 30
        start_time = time.time()
        while unacked_segments and time.time() - start_time < max_wait:
            time.sleep(ACK_TIMEOUT)
            print(f"[{peer_id}] Waiting for ACKs, remaining: {sorted(unacked_segments.keys())}")
        with lock:
            if not unacked_segments:
                print(f"[{peer_id}] All segments of {filename} sent and acknowledged successfully")
            else:
                print(f"[{peer_id}] Failed to send all segments, remaining: {sorted(unacked_segments.keys())}")
    except FileNotFoundError:
        print(f"[{peer_id}] File {filename} not found")
    except Exception as e:
        print(f"[{peer_id}] Error in send_file: {e}")

def send_segment(peer_id, dst, segment, seq, peers, total):
    pkt = make_packet('DATA', seq, total, peer_id, dst, INITIAL_TTL, segment)
    nh = get_next_hop(peer_id, dst)
    if nh:
        try:
            peer_sock.sendto(pkt, tuple(peers[nh]))
        except socket.error as e:
            print(f"[{peer_id}] Error sending segment {seq}: {e}")

# --- Retransmission ---
def ack_timekeeping(peer_id, dst, peers, total):
    while True:
        time.sleep(ACK_TIMEOUT)
        with lock:
            to_retry = [seq for seq in range(total) if seq in unacked_segments]
        for seq in to_retry:
            with lock:
                if retry_counts.get(seq, 0) >= MAX_RETRIES:
                    print(f"[{peer_id}] Segment {seq} failed after {MAX_RETRIES} retries")
                    continue
                retry_counts[seq] = retry_counts.get(seq, 0) + 1
            seg = segments_cache.get(seq)
            if seg:
                print(f"[{peer_id}] Retransmitting segment {seq}")
                send_segment(peer_id, dst, seg, seq, peers, total)
        with lock:
            if not unacked_segments:
                break

# --- Reception & Reassembly ---
def store_segment(peer_id, seq, total, payload):
    with lock:
        buf = reassembly_buffers.setdefault(peer_id, {})
        reassembly_expected[peer_id] = total  # Simplified to avoid race condition
        if seq not in buf:
            buf[seq] = payload
            print(f"[{peer_id}] Stored segment {seq}/{total}")
        if len(buf) == total:
            print(f"[{peer_id}] All segments received, attempting to reassemble")
            threading.Thread(target=reassemble_file, args=(peer_id,), daemon=True).start()  # Run in separate thread to avoid lock contention

def reassemble_file(peer_id):
    try:
        # Avoid holding lock during file I/O to prevent contention
        buf_copy = None
        total = 0
        with lock:
            if peer_id not in reassembly_buffers:
                print(f"[{peer_id}] Reassembly aborted: buffer cleared")
                return
            buf_copy = reassembly_buffers[peer_id].copy()
            total = reassembly_expected.get(peer_id, 0)
            if len(buf_copy) != total:
                missing = [i for i in range(total) if i not in buf_copy]
                print(f"[{peer_id}] Missing segments: {missing}")
                return
            # Clear buffer before file I/O
            del reassembly_buffers[peer_id]
            del reassembly_expected[peer_id]
        
        path = os.path.join(RECV_DIR, peer_id, 'received_file.txt')
        print(f"[{peer_id}] Attempting to create directory: {os.path.dirname(path)}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"[{peer_id}] Writing file to {path}")
        with open(path, 'wb') as f:
            for i in range(total):
                if i not in buf_copy:
                    raise KeyError(f"Segment {i} missing during write")
                f.write(buf_copy[i])
        print(f"[{peer_id}] File received and saved to '{path}'")
    except PermissionError as e:
        print(f"[{peer_id}] Permission denied while writing file: {e}")
    except OSError as e:
        print(f"[{peer_id}] OS error while writing file: {e}")
    except Exception as e:
        print(f"[{peer_id}] Error in reassemble_file: {e}")

def send_ack(peer_id, src, seq, peers):
    pkt = make_packet('ACK', seq, 0, peer_id, src, INITIAL_TTL, b'')
    nh = get_next_hop(peer_id, src)
    if nh:
        try:
            peer_sock.sendto(pkt, tuple(peers[nh]))
            print(f"[{peer_id}] Sent ACK for segment {seq} to {src}")
        except socket.error as e:
            print(f"[{peer_id}] Error sending ACK for segment {seq}: {e}")

# --- DV Routing ---
def handle_dv_update(peer_id, nb, data, peers):
    tbl = json.loads(data.decode())
    updated = False
    with dv_lock:
        neighbor_dv_tables[nb] = tbl
        for dest, cost in tbl.items():
            via = link_costs[nb] + cost
            current_cost, _ = distance_vector.get(dest, (float('inf'), None))
            if via < current_cost:
                distance_vector[dest] = (via, nb)
                updated = True
                print(f"[{peer_id}] Updated route to {dest}: cost={via}, next_hop={nb}")
    if updated:
        broadcast_dv(peer_id, peers)

def broadcast_dv(peer_id, peers):
    with dv_lock:
        payload = json.dumps({d: c for d, (c, _) in distance_vector.items()}).encode()
    for nb in link_costs:
        pkt = make_packet('DV', 0, 0, peer_id, nb, INITIAL_TTL, payload)
        try:
            peer_sock.sendto(pkt, tuple(peers[nb]))
            print(f"[{peer_id}] Broadcast DV to {nb}")
        except socket.error as e:
            print(f"[{peer_id}] Error broadcasting DV to {nb}: {e}")
    print(f"[{peer_id}] Broadcast DV: {distance_vector}")

def routes_print(peer_id):
    with dv_lock:
        print(f"[{peer_id}] Routing table:")
        for d, (c, nh) in distance_vector.items():
            if d != peer_id:
                print(f"  {d}: cost={c}, next_hop={nh}")

def get_next_hop(peer_id, dst):
    with dv_lock:
        return distance_vector.get(dst, (None, None))[1]

def cost_update_thread(peer_id, peers):
    while True:
        time.sleep(COST_UPDATE_INTERVAL)
        changed = False
        with dv_lock:
            for nb in list(link_costs):
                new_cost = max(1, link_costs[nb] + random.choice([-1, 0, 1]))
                if new_cost != link_costs[nb]:
                    link_costs[nb] = new_cost
                    distance_vector[nb] = (new_cost, nb)
                    changed = True
                    print(f"[{peer_id}] Link cost to {nb} changed to {new_cost}")
            if changed:
                for dest in list(distance_vector):
                    if dest == peer_id:
                        continue
                    best = (float('inf'), None)
                    for nb, tbl in neighbor_dv_tables.items():
                        if dest in tbl:
                            cost_via = link_costs[nb] + tbl[dest]
                            if cost_via < best[0]:
                                best = (cost_via, nb)
                    if best[1]:
                        distance_vector[dest] = best
        if changed:
            broadcast_dv(peer_id, peers)

# --- Main ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', required=True)
    args = parser.parse_args()
    pid = args.id
    cfg = json.load(open('config.json'))
    ip, port = cfg['peers'][pid]
    peers = cfg['peers']
    global link_costs
    link_costs = cfg['links'][pid]
    with dv_lock:
        for x in peers:
            if x == pid:
                distance_vector[x] = (0, pid)
            elif x in link_costs:
                distance_vector[x] = (link_costs[x], x)
            else:
                distance_vector[x] = (float('inf'), None)
    print(f"[{pid}] Starting...")
    os.makedirs(os.path.join(RECV_DIR, pid), exist_ok=True)
    threading.Thread(target=listen, args=(pid, ip, port, peers), daemon=True).start()
    threading.Thread(target=cost_update_thread, args=(pid, peers), daemon=True).start()
    while True:
        cmd = input(f"[{pid}] > ").strip().split()
        if not cmd:
            continue
        if cmd[0] == 'send' and len(cmd) == 3:
            _, dst, fn = cmd
            if dst == pid:
                print(f"[{pid}] Cannot send to self")
            else:
                send_file(pid, dst, fn, peers)
        elif cmd[0] == 'check':
            buf = reassembly_buffers.get(pid, {})
            if buf:
                rec = sorted(buf.keys())
                tot = reassembly_expected.get(pid, max(rec) + 1 if rec else 0)
                print(f"[{pid}] Received segments: {rec}, missing: {[i for i in range(tot) if i not in buf]}")
            else:
                print(f"[{pid}] No active buffer")
        elif cmd[0] == 'routes':
            routes_print(pid)
        else:
            print(f"[{pid}] Unknown command: {cmd}")

if __name__ == '__main__':
    main()
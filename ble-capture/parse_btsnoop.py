#!/usr/bin/env python3
"""
Extract watchface BIN payloads from an Android Bluetooth HCI snoop log.

Passive capture only: this script never transmits anything. It reads a
`btsnoop_hci.log` file (or a bugreport zip that contains one), reassembles
L2CAP, then handles both possible transports for the JieLi watchface push:

  * ATT Write / Notification on a BLE link (CID 0x0004, what Fogg's
    dial-sender uses), and
  * RFCOMM/SPP frames on a BR/EDR link (same CID 0x0004; the G6 also pairs
    as a classic device advertising the JieLi UUID
    fe010000-1234-5678-abcd-00805f9b34fb).

Either way the dial does not travel as a bare BIN: AuraFit wraps it in a
proprietary `0xAB` framing (see `sma_frames` below) with a 12-byte per-frame
prologue, so the HK89 header only becomes visible once that framing is peeled
off. The reassembled bytes are then scanned for the HK89 dial container used by
the G6 / Trek 1 (JieLi AM05).

Usage:
    python3 parse_btsnoop.py btsnoop_hci.log [-o out_dir] [--gap 3.0]
    python3 parse_btsnoop.py bugreport-XXXX.zip -o out_dir
    python3 parse_btsnoop.py btsnoop_hci.log --dump-streams  # diagnostic only
    python3 parse_btsnoop.py btsnoop_hci.log --sma           # always try 0xAB

Container layout (see Fogg/comp_decomp.py:1195-1350):
    u16 pltable_size      # number of picture-lookup-table entries
    u8  num_blocks        # block descriptors
    u8  format            # usually 0x02
    num_blocks * 20-byte block descriptors
    pltable_size * u32    # compressed size of each frame
    frame data
    => total = 4 + num_blocks*20 + pltable_size*4 + sum(pltable entries)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import struct
import sys
import zipfile
from collections import defaultdict

BTSNOOP_ID = b"btsnoop\x00"
REC_HDR = struct.Struct(">IIIIq")  # orig_len, incl_len, flags, drops, ts_us

# HCI packet types
HCI_CMD, HCI_ACL, HCI_SCO, HCI_EVT = 0x01, 0x02, 0x03, 0x04

# ATT opcodes
ATT_WRITE_REQ = 0x52
ATT_WRITE_CMD = 0x42
ATT_NOTIFY = 0x1B
ATT_HANDLE_IND = 0x1D
ATT_WRITE_RSP = 0x13

L2CAP_CID_ATT = 0x0004

PEER = {0: "host->ctrl (TX)", 1: "ctrl->host (RX)"}


# --------------------------------------------------------------------------- #
# btsnoop container
# --------------------------------------------------------------------------- #
def load_records(path: str):
    """Yield (ts_seconds, payload_bytes) for every btsnoop record."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.endswith("btsnoop_hci.log")]
            if not names:
                sys.exit(f"no btsnoop_hci.log inside {path}")
            print(f"[zip] using {names[0]}")
            data = zf.read(names[0])
    else:
        with open(path, "rb") as fh:
            data = fh.read()

    if not data.startswith(BTSNOOP_ID):
        sys.exit(f"{path} is not a btsnoop log (bad magic {data[:8]!r})")
    datalink = struct.unpack_from(">I", data, 8 + 4)[0]
    print(f"[btsnoop] datalink type {datalink}, {len(data)} bytes")

    off = 16
    n = len(data)
    while off + REC_HDR.size <= n:
        orig_len, incl_len, _flags, _drops, ts = REC_HDR.unpack_from(data, off)
        off += REC_HDR.size
        if incl_len > n - off:
            break  # truncated tail
        yield ts / 1e6, data[off:off + incl_len]
        off += incl_len


def split_hci(payload: bytes):
    """Return (type, body) for one HCI packet, tolerating missing type byte."""
    if payload and payload[0] in (HCI_CMD, HCI_ACL, HCI_SCO, HCI_EVT):
        ptype, body = payload[0], payload[1:]
    else:  # unencapsulated: infer from shape
        if len(payload) >= 3 and payload[0] >= 0x04 and payload[0] <= 0x3F:
            body = payload
            return HCI_EVT, body
        if len(payload) >= 3:
            body = payload
            return HCI_CMD, body
        return None, b""
    # sanity: the declared length byte must match the record size
    if ptype == HCI_EVT and len(body) >= 2 and body[1] + 2 != len(body):
        return None, b""
    if ptype == HCI_CMD and len(body) >= 3 and body[2] + 3 != len(body):
        return None, b""
    return ptype, body


# --------------------------------------------------------------------------- #
# connection bookkeeping
# --------------------------------------------------------------------------- #
class Capture:
    def __init__(self, gap: float):
        self.gap = gap
        self.handle_addr: dict[int, str] = {}
        self.conn_type: dict[int, str] = {}  # handle -> 'le' | 'bredr'
        # (handle, direction) -> list of (ts, bytes)
        self.pdu: dict[tuple[int, int], list[tuple[float, bytes]]] = defaultdict(list)
        # raw L2CAP reassembly buffer
        self.l2buf: dict[tuple[int, int], bytearray] = defaultdict(bytearray)
        self.att: dict[tuple[int, int], list[tuple[float, int, int, bytes]]] = defaultdict(list)
        # (handle, direction) -> list of (ts, dlci, payload)  [RFCOMM/SPP]
        self.rf: dict[tuple[int, int], list[tuple[float, int, bytes]]] = defaultdict(list)
        self.counts = defaultdict(int)
        # raw CID 0x0004 PDUs, buffered so the transport can be decided per
        # handle once the whole capture is read (a snoop log may start after
        # the connection, leaving the link type unknown)
        self.cid4: list[tuple[float, int, int, bytes]] = []
        self.force: str | None = None
        self.settle(self.force)

    # -- addresses -------------------------------------------------------- #
    def on_event(self, body: bytes):
        if not body:
            return
        code = body[0]
        # subevent fields start after code(1) + plen(1) + subevent code(1)
        if code == 0x0E and len(body) >= 21:  # LE Meta
            sub = body[2]
            if sub == 0x01:  # LE Connection Complete: status, handle, role, addrtype, addr
                if body[3] != 0x00:
                    return
                handle, role, _addr_type, addr = struct.unpack_from("<HBB6s", body, 4)
                handle &= 0x0FFF
                self.conn_type[handle] = "le"
                self.handle_addr[handle] = ("periph" if role else "cent") + ":" + addr.hex(":")
            elif sub == 0x0A and len(body) >= 29:  # LE Enhanced Connection Complete
                handle, role = struct.unpack_from("<HB", body, 4)
                handle &= 0x0FFF
                self.conn_type[handle] = "le"
                self.handle_addr[handle] = ("periph" if role else "cent") + ":enhanced"
        elif code == 0x03 and len(body) >= 12:  # BR/EDR Connection Complete
            handle = struct.unpack_from("<H", body, 2)[0] & 0x0FFF
            self.conn_type[handle] = "bredr"
            self.handle_addr[handle] = "bredr"

    def on_acl(self, body: bytes, direction: int):
        """body = ACL packet without its HCI type byte.

        HCI ACL header: bits 0-11 handle, bits 12-13 PB, bit 14 BC, bit 15 direction.
        """
        if len(body) < 5:
            return
        hf, dlen = struct.unpack_from("<HH", body, 0)
        handle = hf & 0x0FFF
        pb = (hf >> 12) & 0x3
        data = body[4:4 + dlen]
        self.counts[(handle, direction)] += len(data)

        key = (handle, direction)
        buf = self.l2buf[key]

        # The PB flag means different things per link type (Core spec 4.2.1):
        #   LE     : 0b00 first non-flushable, 0b01 CONTINUATION, 0b10 first flushable
        #   BR/EDR : 0b00 first,               0b10 CONTINUATION, 0b11 complete
        # PB 0b00 is "first" in both, but 0b01 and 0b10 are only decidable with
        # the link type. Getting this backwards desynchronises the reassembly
        # and turns real payloads into nonsense CIDs. When the link type is
        # unknown (a snoop log that starts mid-connection never sees the
        # Connection Complete event), fall back to the buffer state: a
        # continuation is only plausible while an incomplete L2CAP PDU is
        # pending.
        link = self.conn_type.get(handle)
        if link == "le":
            continuation = (pb == 0x1)
        elif link == "bredr":
            continuation = (pb == 0x2)
        elif pb == 0x0:
            continuation = False
        else:
            pending = False
            if len(buf) >= 4:
                plen = struct.unpack_from("<H", buf, 0)[0]
                pending = len(buf) < 4 + plen  # incomplete PDU waiting for more
            continuation = pending

        if not continuation:
            buf = bytearray()
        self.l2buf[key] = buf
        buf += data
        # consume as many complete L2CAP PDUs as present
        while len(buf) >= 4:
            plen, cid = struct.unpack_from("<HH", buf, 0)
            if len(buf) < 4 + plen:
                break
            payload = bytes(buf[4:4 + plen])
            del buf[:4 + plen]
            self.on_l2cap(handle, direction, cid, payload)

    def on_l2cap(self, handle: int, direction: int, cid: int, payload: bytes):
        # CID 0x0004 is the fixed SIG channel: ATT on LE links, RFCOMM on BR/EDR.
        if cid != L2CAP_CID_ATT or not payload:
            return
        self.cid4.append((self.last_ts, handle, direction, payload))

    def settle(self, force: str | None = None):
        """Decide ATT vs RFCOMM per handle, then dispatch the buffered PDUs.

        The link type from a Connection Complete event is authoritative. When
        the log starts mid-connection the type is unknown, so score both
        framings over every PDU on that handle and keep the better one.
        """
        self.att.clear()
        self.rf.clear()
        att_ops = (ATT_WRITE_REQ, ATT_WRITE_CMD, ATT_NOTIFY, ATT_HANDLE_IND, ATT_WRITE_RSP)
        by_handle: dict[int, list] = defaultdict(list)
        for rec in self.cid4:
            by_handle[rec[1]].append(rec)

        for handle, recs in sorted(by_handle.items()):
            kind = self.conn_type.get(handle) or force
            if kind is None:
                att_score = sum(1 for r in recs if r[3][0] in att_ops)
                rf_score = len(recs) - att_score
                kind = "le" if att_score >= rf_score else "bredr"
                self.conn_type[handle] = kind
                print(f"[sniff] handle=0x{handle:04X} type unknown -> {kind} "
                      f"(att-like {att_score}/{len(recs)})")
            for now, _h, direction, payload in recs:
                if kind == "le":
                    self.on_att(handle, direction, payload, now)
                else:
                    self.on_rfcomm(handle, direction, payload, now)

    def on_att(self, handle: int, direction: int, payload: bytes, now: float):
        opcode = payload[0]
        if opcode in (ATT_WRITE_REQ, ATT_WRITE_CMD, ATT_NOTIFY, ATT_HANDLE_IND):
            if len(payload) >= 3:
                att_handle = struct.unpack_from("<H", payload, 1)[0]
                self.att[(handle, direction)].append((now, opcode, att_handle, payload[3:]))

    def on_rfcomm(self, handle: int, direction: int, payload: bytes, now: float):
        """Unframe RFCOMM (3GPP TS 27.007 §5.4). One L2CAP PDU holds one RFCOMM
        frame, so no cross-PDU state is needed."""
        i, n = 0, len(payload)
        while n - i >= 2:
            b0 = payload[i]
            if b0 & 0x08:  # UIH data frame: addr, dlci, len[1-2]
                if n - i < 3:
                    return
                dlci = (((b0 >> 2) & 0x3) << 4) | (payload[i + 1] & 0x0F)
                ln = payload[i + 2]
                hdr = 3
                if ln == 0xFF:  # two-octet length: 0xFF + big endian u16
                    if n - i < 5:
                        return
                    ln = (payload[i + 3] << 8) | payload[i + 4]
                    hdr = 5
                if dlci < 2:  # MCC/SCC control channel carries a fixed 3-byte payload
                    dlci, ln, hdr = 0, 3, 2
                if n - i - hdr < ln:
                    return
                self.rf[(handle, direction)].append((now, dlci, payload[i + hdr:i + hdr + ln]))
                i += hdr + ln
            else:  # SABM / UA / DM: two-byte frame, no data
                i += 2


# --------------------------------------------------------------------------- #
# SMA / JieLi "0xAB" transfer framing
# --------------------------------------------------------------------------- #
# The AuraFit app pushes the watchface over GATT ATT writes (one L2CAP PDU per
# ATT write) using a proprietary framing that the Fogg dial-sender mirrors:
#
#   ab | type | len_hi len_lo (big endian) | ?? | ?? | body...
#   0     1       2             3           4    5    6 .. 6+len
#
# `type` 0x01 carries a data frame, 0x11 an acknowledgement. A data frame body
# is SMA_PROLOGUE bytes of per-frame header followed by the file bytes. The last
# two bytes of the prologue are the running file offset as a *wrapping* 16-bit
# counter (it rolls over at 65536), so it doubles as an integrity check.
SMA_TAG = 0xAB
SMA_HDR = 6
SMA_TYPE_DATA = 0x01
SMA_TYPE_ACK = 0x11
SMA_PROLOGUE = 12


def sma_frames(stream: bytes):
    """Split a stream into SMA frames. Returns None if it is not SMA framed."""
    frames, i, n = [], 0, len(stream)
    while i < n:
        if n - i < SMA_HDR or stream[i] != SMA_TAG:
            return None
        (ln,) = struct.unpack_from(">H", stream, i + 2)
        if n - i - SMA_HDR < ln:
            return None
        frames.append((stream[i + 1], stream[i + SMA_HDR:i + SMA_HDR + ln]))
        i += SMA_HDR + ln
    return frames


def sma_reassemble(frames):
    """Rebuild the transferred file from SMA frames.

    Returns (payload, problems). `payload` is the concatenation of the data
    frames with their prologues stripped; `problems` lists human readable
    integrity complaints (gaps, overlaps, truncation).
    """
    payload = bytearray()
    problems = []
    expect = 0
    for idx, (ftype, body) in enumerate(frames):
        if ftype != SMA_TYPE_DATA:
            continue
        if len(body) < SMA_PROLOGUE:
            problems.append(f"frame {idx}: data frame shorter than prologue")
            continue
        off = struct.unpack_from(">H", body, SMA_PROLOGUE - 2)[0]
        if off != expect & 0xFFFF:
            problems.append(f"frame {idx}: offset {off} != expected {expect & 0xFFFF} "
                            f"({'gap' if off > expect else 'overlap/reorder'})")
        payload += body[SMA_PROLOGUE:]
        expect = off + len(body) - SMA_PROLOGUE
    return bytes(payload), problems


# --------------------------------------------------------------------------- #
# HK89 dial container detection
# --------------------------------------------------------------------------- #
def dial_length(buf: bytes, off: int):
    """Return exact BIN length if a valid HK89 header starts at buf[off]."""
    if off + 4 > len(buf):
        return None
    pltable_size, num_blocks, fmt = struct.unpack_from("<HBB", buf, off)
    # pltable_size is a *count* of u32 entries, so it need not be a multiple of
    # 4 (a real capture had 126). Bounds only.
    if not (4 <= pltable_size <= 4096):
        return None
    if not (1 <= num_blocks <= 64) or fmt not in (0x01, 0x02, 0x81, 0x82):
        return None
    pl_off = off + 4 + num_blocks * 20
    if pl_off + pltable_size * 4 > len(buf):
        return None
    total = pltable_size * 4
    for i in range(pltable_size):
        (size,) = struct.unpack_from("<I", buf, pl_off + i * 4)
        if size == 0 or size > 8 << 20:
            return None
        total += size
    return 4 + num_blocks * 20 + total


def find_dials(stream: bytes, exact_end: bool = True):
    """Locate HK89 dials in a byte stream.

    `exact_end` requires the container to consume the buffer up to its last
    byte. That is the only check strong enough to avoid false positives: a
    coarse header match alone will happily fire in the middle of unrelated
    bytes (the raw 0xAB frame stream does). The dial is always the last thing
    a transfer session sends, so the restriction costs nothing in practice.
    """
    hits = []
    for off in range(0, max(0, len(stream) - 4)):
        size = dial_length(stream, off)
        if size is None or off + size > len(stream):
            continue
        if exact_end and off + size != len(stream):
            continue
        hits.append((off, size))
    return hits


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="btsnoop_hci.log or bugreport zip")
    ap.add_argument("-o", "--out", default="captured", help="output directory")
    ap.add_argument("--gap", type=float, default=3.0, help="idle seconds that split sessions")
    ap.add_argument("--dump-streams", action="store_true", help="also write raw session streams")
    ap.add_argument("--transport", choices=("att", "rfcomm"),
                    help="force the transport for handles with no Connection Complete event")
    ap.add_argument("--sma", action="store_true",
                    help="also try the 0xAB SMA framing when the raw stream already "
                         "contains a dial header")
    ap.add_argument("--allow-trailing", action="store_true",
                    help="accept a dial that does not end at the last byte of the "
                         "stream (raises false positives)")
    args = ap.parse_args()

    cap = Capture(gap=args.gap)
    n_rec = 0
    for ts, payload in load_records(args.input):
        n_rec += 1
        cap.last_ts = ts
        ptype, body = split_hci(payload)
        if ptype == HCI_EVT:
            cap.on_event(body)
        elif ptype == HCI_ACL:
            if len(body) < 4:
                continue
            hf = struct.unpack_from("<H", body, 0)[0]
            cap.on_acl(body, (hf >> 15) & 0x1)

    print(f"[records] {n_rec}")
    cap.settle(args.transport)
    print("[handles]")
    for h, a in sorted(cap.handle_addr.items()):
        print(f"  0x{h:04X} {a}")
    if not cap.handle_addr:
        print("  (no LE connection-complete events seen; falling back to raw handles)")

    os.makedirs(args.out, exist_ok=True)
    found = 0

    # normalise both transports to (ts, label, value) triples
    streams: list[tuple[int, int, str, str, list]] = []
    for (handle, direction), entries in sorted(cap.att.items()):
        label = cap.handle_addr.get(handle, "?")
        streams.append((handle, direction, "att", label,
                        [(ts, f"op{op:02X}/h{ah:04X}", v) for ts, op, ah, v in entries]))
    for (handle, direction), entries in sorted(cap.rf.items()):
        label = cap.handle_addr.get(handle, "?")
        streams.append((handle, direction, "rfcomm", label,
                        [(ts, f"dlci{dlci}", v) for ts, dlci, v in entries]))

    for handle, direction, transport, label, entries in streams:
        if not entries:
            continue
        bytes_total = sum(len(e[2]) for e in entries)
        print(f"\n[conn] handle=0x{handle:04X} {label} {PEER[direction]} "
              f"{transport} msgs={len(entries)} value_bytes={bytes_total}")

        # split into sessions on idle gaps
        sessions, cur, cur_t = [], [], None
        for ts, tag, value in entries:
            if cur_t is not None and ts - cur_t > args.gap:
                sessions.append(cur)
                cur = []
            cur.append((ts, tag, value))
            cur_t = ts
        if cur:
            sessions.append(cur)

        for idx, sess in enumerate(sessions):
            stream = b"".join(v for _, _, v in sess)
            if args.dump_streams:
                p = os.path.join(args.out, f"h{handle:04X}_{transport}_{PEER[direction].split()[0]}_{idx}.stream")
                with open(p, "wb") as fh:
                    fh.write(stream)
            hits = find_dials(stream, exact_end=not args.allow_trailing)

            # AuraFit ships the dial inside 0xAB-framed chunks, so the HK89
            # header only shows up after the framing is peeled off. Try that
            # whenever the raw stream does not look like a dial by itself.
            rebuilt = None
            if not hits or args.sma:
                frames = sma_frames(stream)
                ndata = sum(1 for t, _ in frames if t == SMA_TYPE_DATA) if frames else 0
                if ndata:
                    nack = sum(1 for t, _ in frames if t == SMA_TYPE_ACK)
                    rebuilt, problems = sma_reassemble(frames)
                    span = sess[-1][0] - sess[0][0]
                    print(f"  session {idx}: SMA framing — {len(frames)} frames "
                          f"({ndata} data + {nack} ack) over {span:.1f}s, "
                          f"reassembled {len(rebuilt)} bytes")
                    for p in problems[:8]:
                        print(f"    [sma] {p}")
                    if len(problems) > 8:
                        print(f"    [sma] ... {len(problems) - 8} more")
                    if not problems:
                        print("    [sma] offsets contiguous (mod 65536) — no gaps")
                    if args.dump_streams:
                        p = os.path.join(args.out,
                                         f"h{handle:04X}_{transport}_{PEER[direction].split()[0]}_{idx}.sma.bin")
                        with open(p, "wb") as fh:
                            fh.write(rebuilt)

            for off, size in (find_dials(rebuilt, exact_end=not args.allow_trailing)
                              if rebuilt is not None else ()):
                hits.append((off, size, "sma"))
            for h in hits:
                off, size = h[0], h[1]
                src = h[2] if len(h) > 2 else "raw"
                found += 1
                base = rebuilt if src == "sma" else stream
                blob = base[off:off + size]
                digest = hashlib.sha256(blob).hexdigest()
                pltable, nblocks, fmt = struct.unpack_from("<HBB", blob, 0)
                name = (f"captured-h{handle:04X}-{transport}-s{idx}-{src}-off{off}-{size}b.bin")
                path = os.path.join(args.out, name)
                with open(path, "wb") as fh:
                    fh.write(blob)
                print(f"  -> DIAL session={idx} framing={src} offset={off} size={size} "
                      f"blocks={nblocks} pltable={pltable} format=0x{fmt:02X}")
                print(f"     {path}\n     sha256 {digest}")
            if not hits:
                span = sess[-1][0] - sess[0][0]
                extra = " (SMA framing parsed, no dial inside)" if rebuilt is not None else ""
                print(f"  session {idx}: {len(stream)} bytes over {span:.1f}s, "
                      f"no dial header{extra}")

    print(f"\n[done] {found} dial(s) extracted into {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Self-test: synthesize a btsnoop_hci.log that carries a real dial BIN, then
verify parse_btsnoop.py recovers it byte for byte.

    python3 make_fake_snoop.py <input.bin> <output.log> [--handle 0x40]
                                            [--transport att|rfcomm] [--link le|bredr]
"""

from __future__ import annotations

import argparse
import struct

BTSNOOP_ID = b"btsnoop\x00"
REC_HDR = struct.Struct(">IIIIq")


class SnoopWriter:
    def __init__(self, path: str, datalink: int = 1002):
        self.fh = open(path, "wb")
        self.fh.write(BTSNOOP_ID + struct.pack(">II", 1, datalink))
        self.ts = 1_700_000_000_000_000  # microseconds

    def record(self, payload: bytes, flags: int = 0):
        self.ts += 1000  # 1 ms between packets
        self.fh.write(REC_HDR.pack(len(payload), len(payload), flags, 0, self.ts))
        self.fh.write(payload)

    def close(self):
        self.fh.close()


def acl(handle: int, direction: int, l2cap_pdu: bytes, first: bool = True,
        link: str = "le") -> bytes:
    """Wrap a complete L2CAP PDU (length + cid + payload) in one HCI ACL packet.

    The PB flag means different things per link (Core spec 4.2.1): on LE the
    continuation value is 0b01, on BR/EDR it is 0b10. Getting this wrong
    desynchronises the parser's L2CAP reassembly, so keep it faithful.
    """
    cont = 0x1 if link == "le" else 0x2
    pb = 0x0 if first else cont
    hf = (pb << 12) | (handle & 0x0FFF) | ((direction & 1) << 15)
    return bytes([0x02]) + struct.pack("<HH", hf, len(l2cap_pdu)) + l2cap_pdu


def att_l2cap(opcode: int, att_handle: int, value: bytes) -> bytes:
    """ATT PDU wrapped in L2CAP. Writes are opcode+handle+value; notifications
    are opcode+handle+value too, so one layout serves both."""
    att = struct.pack("<BH", opcode, att_handle) + value
    return struct.pack("<HH", len(att), 0x0004) + att


def rfcomm_l2cap(dlci: int, value: bytes) -> bytes:
    """RFCOMM UIH data frame (3GPP TS 27.007 §5.4) in L2CAP, CID 0x0004.

    Address octet: EA=0 C=1 DL=0 UIH=1 PF=0, DLCI high bits, len_ext.
    Payloads over 127 bytes use the two-octet length form (0xFF + big endian).
    """
    b0 = 0x0A | ((dlci & 0x30) << 2)
    if len(value) > 127:
        b0 |= 0x80
        head = bytes([b0, dlci & 0x0F, 0xFF, (len(value) >> 8) & 0xFF, len(value) & 0xFF])
    else:
        head = bytes([b0, dlci & 0x0F, len(value)])
    frame = head + value
    return struct.pack("<HH", len(frame), 0x0004) + frame


# SMA_PROLOGUE = 12: 10 fixed bytes + 2 offset bytes, see SMA_PROLOGUE_FIXED


def sma_frame(ftype: int, body: bytes) -> bytes:
    """JieLi 0xAB transfer frame: tag, type, big endian u16 length, 2 filler
    bytes, then the body. The step is 6 + len, so the length field does not
    include the header."""
    return (bytes([0xAB, ftype]) + struct.pack(">H", len(body)) + b"\x00\x00" + body)


# 10 fixed bytes of the per-frame prologue; the two trailing bytes are the
# running file offset as a wrapping 16-bit counter, making 12 in total
SMA_PROLOGUE_FIXED = bytes.fromhex("07010000000971380000")


def sma_split(data: bytes, per_frame: int = 1018):
    """Yield (frame_type, body) data+ack pairs exactly the way the real transfer
    looks: a 12-byte prologue per data frame whose last two bytes are the
    running file offset as a wrapping 16-bit counter, plus one ack per data
    frame echoing the new offset."""
    off = 0
    while off < len(data):
        chunk = data[off:off + per_frame]
        body = SMA_PROLOGUE_FIXED + struct.pack(">H", off & 0xFFFF) + chunk
        yield 0x01, body
        off += len(chunk)
        yield 0x11, SMA_PROLOGUE_FIXED + struct.pack(">H", off & 0xFFFF)


def bredr_complete(handle: int, addr: bytes) -> bytes:
    """BR/EDR Connection Complete event: status, handle, addr, link type, enc mode."""
    body = bytes([0x03, 0x0B, 0x00]) + struct.pack("<H", handle) + addr \
        + bytes([0x01, 0x00])  # ACL link, no encryption
    assert len(body) == 2 + body[1], len(body)
    return bytes([0x04]) + body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin")
    ap.add_argument("out")
    ap.add_argument("--handle", type=lambda s: int(s, 0), default=0x0040)
    ap.add_argument("--att-handle", type=lambda s: int(s, 0), default=0x0016)
    ap.add_argument("--att-mtu", type=int, default=180)
    ap.add_argument("--transport", choices=("att", "rfcomm"), default="att")
    ap.add_argument("--link", choices=("le", "bredr"), default="le")
    ap.add_argument("--no-complete", action="store_true",
                    help="omit the connection-complete event so the parser must sniff")
    ap.add_argument("--sma", action="store_true",
                    help="wrap the payload in the JieLi 0xAB transfer framing "
                         "(1018 bytes per frame + 12-byte prologue + acks)")
    args = ap.parse_args()

    data = open(args.bin, "rb").read()
    w = SnoopWriter(args.out)

    if args.no_complete:
        pass
    elif args.link == "le":
        # LE Connection Complete: 0x0E, plen 0x14, sub 0x01, status, handle, role,
        # addrtype, addr, ...
        addr = bytes.fromhex("aabbccddeeff")
        evt_body = (bytes([0x0E, 0x14, 0x01, 0x00])
                    + struct.pack("<H", args.handle) + bytes([0x00, 0x00]) + addr
                    + struct.pack("<HHH", 0x0024, 0x0000, 0x002a) + bytes([0x00, 0x01]))
        assert len(evt_body) == 2 + evt_body[1], len(evt_body)
        w.record(bytes([0x04]) + evt_body)
    else:
        w.record(bredr_complete(args.handle, bytes.fromhex("aabbccddeeff")))

    def frame(value: bytes) -> bytes:
        if args.transport == "att":
            return att_l2cap(0x52, args.att_handle, value)
        return rfcomm_l2cap(0x02, value)

    def reply() -> bytes:
        if args.transport == "att":
            return att_l2cap(0x1B, args.att_handle, b"\x00\x00")
        return rfcomm_l2cap(0x02, b"\x00\x00")

    if args.sma:
        # the real transfer interleaves 608 data frames with 608 acks, all as
        # separate ATT writes in both directions
        for ftype, body in sma_split(data):
            direction = 0 if ftype == 0x01 else 1
            w.record(acl(args.handle, direction, frame(sma_frame(ftype, body)),
                         first=(direction == 0), link=args.link))
        per_write = 0
    else:
        # 2-byte SMA-ish prologue so the dial does not start at offset 0
        w.record(acl(args.handle, 0, frame(b"\xaa\xbb"), link=args.link))

        per_write = args.att_mtu - 3
        first = True
        for i in range(0, len(data), per_write):
            chunk = data[i:i + per_write]
            w.record(acl(args.handle, 0, frame(chunk), first=first, link=args.link))
            first = False

    # a few post-transfer replies
    for _ in range(3):
        w.record(acl(args.handle, 1, reply(), first=False, link=args.link))

    w.close()
    shape = (f"0xAB framing, {len(data)} bytes in 1018-byte frames + acks"
             if args.sma else f"{len(data)} bytes in {per_write}-byte frames")
    print(f"wrote {args.out}: {args.link}/{args.transport}, {shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

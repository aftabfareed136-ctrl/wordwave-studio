"""Minimal edge-tts client that survives the sandbox egress proxy.

The egress proxy rewrites the websocket handshake's ``Connection: Upgrade``
header to ``Connection: close``. Strict clients (aiohttp) reject the 101
response because of that; this client performs the handshake manually over a
CONNECT tunnel, only requires the 101 status, then speaks the edge-tts
message protocol (speech.config / ssml / audio / audio.metadata / turn.end)
itself. No aiohttp involved.
"""
from __future__ import annotations

import base64
import json
import os
import random
import socket
import ssl
import struct
import time
import uuid
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener, Request
from xml.sax.saxutils import escape as xml_escape

from edge_tts.constants import (
    BASE_URL,
    SEC_MS_GEC_VERSION,
    TRUSTED_CLIENT_TOKEN,
    WSS_HEADERS,
)
from edge_tts.drm import DRM

HOST = "speech.platform.bing.com"
WS_PATH = "/consumer/speech/synthesize/readaloud/edge/v1"


def _proxy_parts() -> tuple[str, int, str | None]:
    raw = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or ""
    u = urlparse(raw)
    auth = None
    if u.username:
        auth = base64.b64encode(f"{u.username}:{u.password or ''}".encode()).decode()
    return u.hostname or "localhost", u.port or 3128, auth


def _read_http_headers(sock: socket.socket) -> tuple[str, dict]:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("proxy closed connection during handshake")
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return lines[0], headers, rest


def _connect_tls(timeout: int = 30) -> socket.socket:
    phost, pport, auth = _proxy_parts()
    sock = socket.create_connection((phost, pport), timeout=timeout)
    req = (f"CONNECT {HOST}:443 HTTP/1.1\r\nHost: {HOST}:443\r\n")
    if auth:
        req += f"Proxy-Authorization: Basic {auth}\r\n"
    req += "Proxy-Connection: Keep-Alive\r\n\r\n"
    sock.sendall(req.encode())
    status, _, _ = _read_http_headers(sock)
    if "200" not in status:
        raise ConnectionError(f"proxy CONNECT failed: {status}")
    ctx = ssl.create_default_context()
    tls = ctx.wrap_socket(sock, server_hostname=HOST)
    tls.settimeout(timeout)
    return tls


def _ws_handshake(sock: socket.socket):
    key = base64.b64encode(random.randbytes(16)).decode()
    query = (
        f"TrustedClientToken={TRUSTED_CLIENT_TOKEN}"
        f"&ConnectionId={uuid.uuid4().hex}"
        f"&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
        f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}"
    )
    # WSS_HEADERS already carries Sec-WebSocket-Version etc. — never duplicate.
    lines = [f"GET {WS_PATH}?{query} HTTP/1.1", f"Host: {HOST}"]
    seen = {"host"}
    for k, v in WSS_HEADERS.items():
        lines.append(f"{k}: {v}")
        seen.add(k.lower())
    extra = [
        ("Upgrade", "websocket"),
        ("Connection", "Upgrade"),
        ("Sec-WebSocket-Key", key),
        ("Sec-WebSocket-Extensions", "permessage-deflate; client_max_window_bits"),
        ("Accept", "*/*"),
        ("Cookie", f"muid={DRM.generate_muid()};"),
    ]
    for k, v in extra:
        if k.lower() not in seen:
            lines.append(f"{k}: {v}")
            seen.add(k.lower())
    lines.append("\r\n")
    sock.sendall("\r\n".join(lines).encode())
    status, _, _ = _read_http_headers(sock)
    if "101" not in status:
        raise ConnectionError(f"websocket handshake failed: {status}")


def _ws_send_text(sock: socket.socket, text: str):
    data = text.encode("utf-8")
    mask = random.randbytes(4)
    header = bytes([0x81])
    n = len(data)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 65536:
        header += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        header += bytes([0x80 | 127]) + struct.pack(">Q", n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    sock.sendall(header + mask + masked)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("websocket closed mid-frame")
        buf += chunk
    return buf


def _ws_recv(sock: socket.socket) -> tuple[int, bytes]:
    b1, b2 = _recv_exact(sock, 2)
    opcode = b1 & 0x0F
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    if b2 & 0x80:  # server must not mask; tolerate anyway
        mask = _recv_exact(sock, 4)
        payload = _recv_exact(sock, length)
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    else:
        payload = _recv_exact(sock, length)
    return opcode, payload


def _date_string() -> str:
    return time.strftime("%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)",
                         time.gmtime())


def synthesize(text: str, voice: str, mp3_path: str) -> list[dict]:
    """Returns word boundaries: [{'text', 'start', 'end'}] (seconds)."""
    text = xml_escape(text)
    sock = _connect_tls()
    try:
        _ws_handshake(sock)
        _ws_send_text(
            sock,
            f"X-Timestamp:{_date_string()}\r\n"
            "Content-Type:application/json; charset=utf-8\r\n"
            "Path:speech.config\r\n\r\n"
            '{"context":{"synthesis":{"audio":{"metadataoptions":'
            '{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"true"},'
            '"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}\r\n',
        )
        ssml = (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
            f"<voice name='{voice}'>"
            "<prosody pitch='+0Hz' rate='+0%' volume='+100%'>"
            f"{text}</prosody></voice></speak>"
        )
        _ws_send_text(
            sock,
            f"X-RequestId:{uuid.uuid4().hex}\r\n"
            "Content-Type:application/ssml+xml\r\n"
            f"X-Timestamp:{_date_string()}Z\r\n"
            "Path:ssml\r\n\r\n"
            f"{ssml}",
        )
        words: list[dict] = []
        with open(mp3_path, "wb") as f:
            while True:
                opcode, payload = _ws_recv(sock)
                if opcode == 0x1:  # text
                    head, _, body = payload.partition(b"\r\n\r\n")
                    params = {}
                    for line in head.split(b"\r\n"):
                        if b":" in line:
                            k, v = line.split(b":", 1)
                            params[k.strip()] = v.strip()
                    path = params.get(b"Path")
                    if path == b"audio.metadata":
                        meta = json.loads(body.decode("utf-8"))
                        for m in meta.get("Metadata", []):
                            if m.get("Type") == "WordBoundary":
                                d = m["Data"]
                                words.append({
                                    "text": d["text"]["Text"],
                                    "start": d["Offset"] / 1e7,
                                    "end": (d["Offset"] + d["Duration"]) / 1e7,
                                })
                    elif path == b"turn.end":
                        break
                elif opcode == 0x2:  # binary: audio
                    if len(payload) < 2:
                        continue
                    hlen = int.from_bytes(payload[:2], "big")
                    head, _, body = payload[:hlen].partition(b"\r\n"), b"", payload[hlen:]
                    if b"Path:audio" in payload[:hlen]:
                        f.write(body)
                elif opcode == 0x8:  # close
                    break
        if not words:
            raise RuntimeError("TTS returned no word boundaries — try another voice.")
        return words
    finally:
        try:
            sock.close()
        except OSError:
            pass


def list_voices(locale_prefix: str | None = None) -> list[dict]:
    url = f"https://{BASE_URL}/voices/list?trustedclienttoken={TRUSTED_CLIENT_TOKEN}"
    opener = build_opener(ProxyHandler({"https": os.environ.get("https_proxy") or ""}))
    req = Request(url, headers={"User-Agent": WSS_HEADERS.get("User-Agent", "Mozilla/5.0")})
    with opener.open(req, timeout=30) as r:
        voices = json.loads(r.read().decode("utf-8"))
    if locale_prefix:
        voices = [v for v in voices if v["Locale"].startswith(locale_prefix)]
    return voices

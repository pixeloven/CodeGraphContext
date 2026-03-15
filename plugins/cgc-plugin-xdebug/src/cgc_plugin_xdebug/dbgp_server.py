"""
DBGp TCP listener for the Xdebug plugin.

Implements a minimal DBGp debug client that:
  1. Accepts inbound Xdebug connections on a configurable TCP port.
  2. Sends a ``stack_get`` command to retrieve the call stack.
  3. Parses the XML response into a list of frame dicts.
  4. Delegates persistence to XdebugWriter.

The server only starts when CGC_PLUGIN_XDEBUG_ENABLED=true.
Uses only Python stdlib (socket, xml.etree.ElementTree, hashlib).
"""
from __future__ import annotations

import hashlib
import logging
import os
import socket
import threading
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger(__name__)

_DBGP_NS = "urn:debugger_protocol_v1"
_DEFAULT_HOST = os.environ.get("XDEBUG_LISTEN_HOST", "0.0.0.0")
_DEFAULT_PORT = int(os.environ.get("XDEBUG_LISTEN_PORT", "9003"))
_ENABLED_ENV = "CGC_PLUGIN_XDEBUG_ENABLED"


# ---------------------------------------------------------------------------
# Pure-logic helpers (no I/O — tested directly)
# ---------------------------------------------------------------------------

def parse_stack_xml(xml_str: str) -> list[dict]:
    """
    Parse a DBGp ``stack_get`` XML response into a list of frame dicts.

    Returns frames ordered by ``level`` (ascending, 0 = current frame).
    The ``file://`` scheme prefix is stripped from filenames.
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as exc:
        logger.warning("Failed to parse DBGp XML: %s", exc)
        return []

    frames: list[dict] = []
    for stack_el in root.findall(f"{{{_DBGP_NS}}}stack") + root.findall("stack"):
        filename = stack_el.get("filename", "")
        if filename.startswith("file://"):
            filename = filename[7:]

        frames.append({
            "where": stack_el.get("where", ""),
            "level": int(stack_el.get("level", 0)),
            "filename": filename,
            "lineno": int(stack_el.get("lineno", 0)),
        })

    return sorted(frames, key=lambda f: f["level"])


def compute_chain_hash(frames: list[dict]) -> str:
    """
    Compute a deterministic SHA-256 hash for a call stack chain.

    Two identical chains (same where/filename/lineno sequence) produce the
    same hash, enabling efficient deduplication.
    """
    key = "|".join(
        f"{f.get('where','')}:{f.get('filename','')}:{f.get('lineno',0)}"
        for f in frames
    )
    return hashlib.sha256(key.encode()).hexdigest()


def build_frame_id(class_name: str, method_name: str, file_path: str, lineno: int) -> str:
    """
    Build a deterministic unique frame identifier string.

    The ID is a SHA-256 hex digest of the four components, ensuring
    stability across restarts.
    """
    key = f"{class_name}::{method_name}::{file_path}::{lineno}"
    return hashlib.sha256(key.encode()).hexdigest()


def _parse_where(where: str) -> tuple[str | None, str | None]:
    """Split a DBGp 'where' string (Class->method or Class::method) into (class, method)."""
    for sep in ("->", "::"):
        if sep in where:
            parts = where.rsplit(sep, 1)
            return parts[0], parts[1]
    return None, where or None


# ---------------------------------------------------------------------------
# TCP Server
# ---------------------------------------------------------------------------

class DBGpServer:
    """
    Minimal TCP DBGp server that captures PHP call stacks.

    Only starts when ``CGC_PLUGIN_XDEBUG_ENABLED=true``.
    """

    def __init__(self, writer: Any, host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT) -> None:
        self._writer = writer
        self._host = host
        self._port = port
        self._running = False
        self._sock: socket.socket | None = None

    def is_enabled(self) -> bool:
        return os.environ.get(_ENABLED_ENV, "").lower() == "true"

    def listen(self) -> None:
        """Start the TCP listener (blocking). Requires XDEBUG_ENABLED env var."""
        if not self.is_enabled():
            logger.warning(
                "Xdebug DBGp server NOT started — set %s=true to enable", _ENABLED_ENV
            )
            return

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._sock.listen(10)
        self._running = True
        logger.info("DBGp server listening on %s:%d", self._host, self._port)

        while self._running:
            try:
                conn, addr = self._sock.accept()
                logger.debug("Xdebug connection from %s", addr)
                t = threading.Thread(target=self._handle_connection, args=(conn,), daemon=True)
                t.start()
            except OSError:
                break  # socket closed

    def stop(self) -> None:
        self._running = False
        if self._sock:
            self._sock.close()

    def _handle_connection(self, conn: socket.socket) -> None:
        try:
            self._process_session(conn)
        except Exception as exc:
            logger.debug("DBGp session error: %s", exc)
        finally:
            conn.close()

    def _process_session(self, conn: socket.socket) -> None:
        # Read the init packet (Xdebug sends XML on connect)
        _init_xml = self._recv_packet(conn)

        seq = 1
        # Send run to start execution
        self._send_cmd(conn, f"run -i {seq}")
        seq += 1

        while True:
            # Request the current call stack
            self._send_cmd(conn, f"stack_get -i {seq}")
            seq += 1

            response = self._recv_packet(conn)
            if not response:
                break

            frames = parse_stack_xml(response)
            if frames:
                self._writer.write_chain(frames)

            # Send run to continue to next breakpoint / end of script
            self._send_cmd(conn, f"run -i {seq}")
            seq += 1

            # Check if execution ended
            ack = self._recv_packet(conn)
            if not ack or "status=\"stopped\"" in ack or "status='stopped'" in ack:
                break

    @staticmethod
    def _send_cmd(conn: socket.socket, cmd: str) -> None:
        data = (cmd + "\0").encode()
        conn.sendall(data)

    @staticmethod
    def _recv_packet(conn: socket.socket) -> str:
        """Read a DBGp length-prefixed null-terminated packet."""
        chunks: list[bytes] = []
        # Read the length digits up to the first \0
        length_bytes = bytearray()
        while True:
            byte = conn.recv(1)
            if not byte:
                return ""
            if byte == b"\0":
                break
            length_bytes.extend(byte)

        if not length_bytes:
            return ""

        try:
            length = int(length_bytes)
        except ValueError:
            return ""

        # Read the XML body (length bytes + trailing \0)
        remaining = length + 1
        while remaining > 0:
            chunk = conn.recv(min(remaining, 4096))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)

        return b"".join(chunks).rstrip(b"\0").decode("utf-8", errors="replace")

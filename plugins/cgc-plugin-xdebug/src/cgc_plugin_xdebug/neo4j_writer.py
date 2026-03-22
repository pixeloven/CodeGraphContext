"""
Neo4j writer for the Xdebug plugin.

Persists PHP call stack chains as StackFrame nodes in the graph,
with LRU-based deduplication to avoid redundant writes.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from cgc_plugin_xdebug.dbgp_server import (
    compute_chain_hash,
    build_frame_id,
    _parse_where,
)

logger = logging.getLogger(__name__)

_DEDUP_CACHE_SIZE = int(os.environ.get("XDEBUG_DEDUP_CACHE_SIZE", "10000"))

# ---------------------------------------------------------------------------
# Cypher templates
# ---------------------------------------------------------------------------

_MERGE_FRAME = """
MERGE (sf:StackFrame {frame_id: $frame_id})
ON CREATE SET
    sf.fqn              = $fqn,
    sf.class_name       = $class_name,
    sf.method_name      = $method_name,
    sf.file_path        = $file_path,
    sf.lineno           = $lineno,
    sf.observation_count = 1,
    sf.first_seen       = datetime()
ON MATCH SET
    sf.observation_count = coalesce(sf.observation_count, 0) + 1,
    sf.last_seen         = datetime()
"""

_LINK_CALLED_BY = """
MATCH (callee:StackFrame {frame_id: $callee_id}), (caller:StackFrame {frame_id: $caller_id})
MERGE (callee)-[:CALLED_BY]->(caller)
"""

_LINK_RESOLVES_TO = """
MATCH (sf:StackFrame {frame_id: $frame_id})
WHERE sf.fqn IS NOT NULL
MATCH (m:Method {fqn: sf.fqn})
MERGE (sf)-[:RESOLVES_TO]->(m)
"""

_INCREMENT_OBSERVATION = """
MATCH (sf:StackFrame {frame_id: $frame_id})
SET sf.observation_count = coalesce(sf.observation_count, 0) + 1,
    sf.last_seen = datetime()
"""


class XdebugWriter:
    """
    Writes Xdebug call stack chains to Neo4j with LRU deduplication.

    When the same chain hash is seen again the writer skips a full MERGE
    and only increments the observation_count on the root frame.
    """

    def __init__(self, db_manager: Any, cache_size: int = _DEDUP_CACHE_SIZE) -> None:
        self._db = db_manager
        self._cache: dict[str, int] = {}  # hash → root frame_id
        self._cache_size = cache_size

    def write_chain(self, frames: list[dict]) -> None:
        """
        Persist a call stack chain.

        If the chain was seen before, only increments the root frame's
        observation_count; otherwise writes all StackFrame nodes and
        CALLED_BY links, then attempts RESOLVES_TO for each frame.
        """
        if not frames:
            return

        chain_hash = compute_chain_hash(frames)
        if chain_hash in self._cache:
            root_frame_id = self._cache[chain_hash]
            self._increment_observation(root_frame_id)
            return

        driver = self._db.get_driver()
        with driver.session() as session:
            frame_ids: list[str] = []
            for frame in frames:
                class_name, method_name = _parse_where(frame.get("where", ""))
                fqn = f"{class_name}::{method_name}" if class_name and method_name else None
                frame_id = build_frame_id(
                    class_name or "",
                    method_name or "",
                    frame.get("filename", ""),
                    frame.get("lineno", 0),
                )
                session.run(
                    _MERGE_FRAME,
                    frame_id=frame_id,
                    fqn=fqn,
                    class_name=class_name,
                    method_name=method_name,
                    file_path=frame.get("filename"),
                    lineno=frame.get("lineno", 0),
                )
                frame_ids.append(frame_id)

            # CALLED_BY links: frame[n] called by frame[n+1]
            for i in range(len(frame_ids) - 1):
                session.run(
                    _LINK_CALLED_BY,
                    callee_id=frame_ids[i],
                    caller_id=frame_ids[i + 1],
                )

            # Try to link each frame to a static Method node
            for frame_id in frame_ids:
                session.run(_LINK_RESOLVES_TO, frame_id=frame_id)

        root_frame_id = frame_ids[0] if frame_ids else ""
        self._evict_if_needed()
        self._cache[chain_hash] = root_frame_id

    def _increment_observation(self, frame_id: str) -> None:
        try:
            driver = self._db.get_driver()
            with driver.session() as session:
                session.run(_INCREMENT_OBSERVATION, frame_id=frame_id)
        except Exception as exc:
            logger.warning("Failed to increment observation for frame %s: %s", frame_id, exc)

    def _evict_if_needed(self) -> None:
        if len(self._cache) >= self._cache_size:
            # Evict oldest entry (first inserted key in CPython 3.7+)
            oldest = next(iter(self._cache))
            del self._cache[oldest]

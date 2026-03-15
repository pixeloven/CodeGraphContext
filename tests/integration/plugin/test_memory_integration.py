"""
Integration tests for cgc_plugin_memory.mcp_tools handlers.

Uses a mocked db_manager (no real Neo4j required).
Tests MUST FAIL before T037 (mcp_tools.py) is implemented.
"""
from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../plugins/cgc-plugin-memory/src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_session(rows: list[dict] | None = None):
    """Build a mock Neo4j session with configurable query results."""
    session = MagicMock()
    result = MagicMock()
    result.data = MagicMock(return_value=rows or [])
    session.run = MagicMock(return_value=result)
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


def _make_db(rows: list[dict] | None = None):
    session = _make_session(rows)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    db = MagicMock()
    db.get_driver = MagicMock(return_value=driver)
    return db, session


def _get_handlers(db_manager):
    from cgc_plugin_memory.mcp_tools import get_mcp_handlers
    return get_mcp_handlers({"db_manager": db_manager})


# ---------------------------------------------------------------------------
# memory_store
# ---------------------------------------------------------------------------

class TestMemoryStore:
    def test_issues_merge_memory_node(self):
        """memory_store issues a MERGE for the Memory node."""
        db, session = _make_db()
        handlers = _get_handlers(db)
        handlers["memory_store"](entity_type="spec", name="Order spec", content="Order entity spec")

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("Memory" in c and "MERGE" in c for c in cypher_calls), \
            f"No Memory MERGE found: {cypher_calls}"

    def test_memory_store_with_links_to_creates_describes(self):
        """memory_store with links_to creates a DESCRIBES relationship."""
        db, session = _make_db()
        handlers = _get_handlers(db)
        handlers["memory_store"](
            entity_type="spec",
            name="Order spec",
            content="...",
            links_to="App\\Controllers\\OrderController",
        )

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("DESCRIBES" in c for c in cypher_calls), \
            f"No DESCRIBES found: {cypher_calls}"

    def test_memory_store_without_links_to_no_describes(self):
        """memory_store without links_to does NOT create DESCRIBES."""
        db, session = _make_db()
        handlers = _get_handlers(db)
        handlers["memory_store"](entity_type="spec", name="Standalone note", content="...")

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert not any("DESCRIBES" in c for c in cypher_calls)


# ---------------------------------------------------------------------------
# memory_search
# ---------------------------------------------------------------------------

class TestMemorySearch:
    def test_search_uses_fulltext_index(self):
        """memory_search queries the memory_search fulltext index."""
        db, session = _make_db(rows=[{"name": "Order spec", "entity_type": "spec", "content": "..."}])
        handlers = _get_handlers(db)
        result = handlers["memory_search"](query="order")

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("memory_search" in c or "FULLTEXT" in c.upper() or "CALL db.index" in c or "fulltext" in c.lower()
                   for c in cypher_calls), f"No fulltext query found: {cypher_calls}"

    def test_search_returns_results_key(self):
        """memory_search result dict contains a 'results' key."""
        db, session = _make_db(rows=[{"name": "X", "entity_type": "spec", "content": "y"}])
        handlers = _get_handlers(db)
        result = handlers["memory_search"](query="test")
        assert "results" in result


# ---------------------------------------------------------------------------
# memory_undocumented
# ---------------------------------------------------------------------------

class TestMemoryUndocumented:
    def test_undocumented_queries_class_nodes(self):
        """memory_undocumented queries Class nodes without DESCRIBES."""
        db, session = _make_db(rows=[{"fqn": "App\\Foo", "type": "Class"}])
        handlers = _get_handlers(db)
        result = handlers["memory_undocumented"](node_type="Class")

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("Class" in c for c in cypher_calls)

    def test_undocumented_returns_nodes_key(self):
        """memory_undocumented result dict contains a 'nodes' key."""
        db, session = _make_db(rows=[])
        handlers = _get_handlers(db)
        result = handlers["memory_undocumented"](node_type="Class")
        assert "nodes" in result


# ---------------------------------------------------------------------------
# memory_link
# ---------------------------------------------------------------------------

class TestMemoryLink:
    def test_link_creates_describes_edge(self):
        """memory_link creates a DESCRIBES relationship."""
        db, session = _make_db()
        handlers = _get_handlers(db)
        handlers["memory_link"](
            memory_id="mem-001",
            node_fqn="App\\Controllers\\OrderController",
            node_type="Class",
        )

        cypher_calls = [str(c.args[0]) for c in session.run.call_args_list]
        assert any("DESCRIBES" in c for c in cypher_calls), \
            f"No DESCRIBES found: {cypher_calls}"

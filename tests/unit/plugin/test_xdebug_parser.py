"""
Unit tests for cgc_plugin_xdebug.dbgp_server parsing logic.

No TCP connections required — pure XML/logic tests.
Tests MUST FAIL before T030 (dbgp_server.py) is implemented.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../plugins/cgc-plugin-xdebug/src"))

_SAMPLE_STACK_XML = """\
<?xml version="1.0" encoding="iso-8859-1"?>
<response xmlns="urn:debugger_protocol_v1" command="stack_get" transaction_id="2">
  <stack where="App\\Http\\Controllers\\OrderController->index"
         level="0" type="file"
         filename="file:///var/www/html/app/Http/Controllers/OrderController.php"
         lineno="42"/>
  <stack where="Illuminate\\Routing\\Controller->callAction"
         level="1" type="file"
         filename="file:///var/www/html/vendor/laravel/framework/src/Illuminate/Routing/Controller.php"
         lineno="54"/>
  <stack where="{main}" level="2" type="file"
         filename="file:///var/www/html/public/index.php"
         lineno="55"/>
</response>
"""

_EMPTY_STACK_XML = """\
<?xml version="1.0" encoding="iso-8859-1"?>
<response xmlns="urn:debugger_protocol_v1" command="stack_get" transaction_id="3">
</response>
"""


def _import_parser():
    from cgc_plugin_xdebug.dbgp_server import (
        parse_stack_xml,
        compute_chain_hash,
        build_frame_id,
    )
    return parse_stack_xml, compute_chain_hash, build_frame_id


# ---------------------------------------------------------------------------
# parse_stack_xml
# ---------------------------------------------------------------------------

class TestParseStackXml:
    def test_returns_correct_frame_count(self):
        parse_stack_xml, *_ = _import_parser()
        frames = parse_stack_xml(_SAMPLE_STACK_XML)
        assert len(frames) == 3

    def test_frame_fields_present(self):
        parse_stack_xml, *_ = _import_parser()
        frames = parse_stack_xml(_SAMPLE_STACK_XML)
        frame = frames[0]
        assert "where" in frame
        assert "level" in frame
        assert "filename" in frame
        assert "lineno" in frame

    def test_frame_level_is_integer(self):
        parse_stack_xml, *_ = _import_parser()
        frames = parse_stack_xml(_SAMPLE_STACK_XML)
        assert all(isinstance(f["level"], int) for f in frames)

    def test_frames_ordered_by_level(self):
        parse_stack_xml, *_ = _import_parser()
        frames = parse_stack_xml(_SAMPLE_STACK_XML)
        levels = [f["level"] for f in frames]
        assert levels == sorted(levels)

    def test_empty_stack_returns_empty_list(self):
        parse_stack_xml, *_ = _import_parser()
        assert parse_stack_xml(_EMPTY_STACK_XML) == []

    def test_first_frame_where_parsed(self):
        parse_stack_xml, *_ = _import_parser()
        frames = parse_stack_xml(_SAMPLE_STACK_XML)
        assert "OrderController" in frames[0]["where"]

    def test_filename_stripped_of_scheme(self):
        """file:// prefix should be stripped from the filename."""
        parse_stack_xml, *_ = _import_parser()
        frames = parse_stack_xml(_SAMPLE_STACK_XML)
        assert not frames[0]["filename"].startswith("file://")


# ---------------------------------------------------------------------------
# compute_chain_hash
# ---------------------------------------------------------------------------

class TestComputeChainHash:
    def test_same_frames_same_hash(self):
        parse_stack_xml, compute_chain_hash, _ = _import_parser()
        frames = parse_stack_xml(_SAMPLE_STACK_XML)
        assert compute_chain_hash(frames) == compute_chain_hash(frames)

    def test_different_frames_different_hash(self):
        parse_stack_xml, compute_chain_hash, _ = _import_parser()
        frames1 = parse_stack_xml(_SAMPLE_STACK_XML)
        frames2 = frames1[:-1]  # drop last frame
        assert compute_chain_hash(frames1) != compute_chain_hash(frames2)

    def test_empty_frames_returns_hash(self):
        _, compute_chain_hash, _ = _import_parser()
        h = compute_chain_hash([])
        assert isinstance(h, str) and len(h) > 0

    def test_hash_is_deterministic_across_calls(self):
        parse_stack_xml, compute_chain_hash, _ = _import_parser()
        frames = parse_stack_xml(_SAMPLE_STACK_XML)
        assert compute_chain_hash(frames) == compute_chain_hash(frames)


# ---------------------------------------------------------------------------
# build_frame_id
# ---------------------------------------------------------------------------

class TestBuildFrameId:
    def test_returns_string(self):
        _, _, build_frame_id = _import_parser()
        fid = build_frame_id("App\\Controllers\\Foo", "bar", "/var/www/Foo.php", 10)
        assert isinstance(fid, str)

    def test_deterministic(self):
        _, _, build_frame_id = _import_parser()
        a = build_frame_id("App\\Foo", "bar", "/var/www/Foo.php", 10)
        b = build_frame_id("App\\Foo", "bar", "/var/www/Foo.php", 10)
        assert a == b

    def test_different_inputs_different_ids(self):
        _, _, build_frame_id = _import_parser()
        a = build_frame_id("App\\Foo", "bar", "/var/www/Foo.php", 10)
        b = build_frame_id("App\\Foo", "baz", "/var/www/Foo.php", 10)
        assert a != b

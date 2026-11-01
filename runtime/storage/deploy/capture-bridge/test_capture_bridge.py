#!/usr/bin/env python3
# Contract tests for the capture bridge normalizer/selector. Pure (no network, no files
# besides a temp transcript). Run: python3 -I test_capture_bridge.py
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture_bridge as cb

failures = []

def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)

# --- normalize_content ------------------------------------------------------------------
blocks, unknown = cb.normalize_content("hello world")
check("string content -> single text block",
      blocks == [{"type": "text", "text": "hello world"}] and unknown == [])

blocks, unknown = cb.normalize_content([
    {"type": "thinking", "text": "HIDDEN-COT"},
    {"type": "tool_use", "text": "{\"cmd\":\"x\"}"},
    {"type": "tool_result", "text": "secret-ish"},
    {"type": "text", "text": "visible answer"},
])
check("thinking/tool blocks become TYPE-ONLY (no bytes leave)",
      {"type": "thinking"} in blocks and {"type": "tool_use"} in blocks
      and {"type": "tool_result"} in blocks)
check("non-text block text is never carried",
      all("text" not in b for b in blocks if b["type"] != "text"))
check("text block preserved", {"type": "text", "text": "visible answer"} in blocks)
check("known blocks are not flagged unknown", unknown == [])

blocks, unknown = cb.normalize_content([{"type": "image", "source": {}},
                                        {"type": "text", "text": "cap"}])
check("image (known non-text) dropped QUIETLY, not flagged",
      blocks == [{"type": "text", "text": "cap"}] and unknown == [])

blocks, unknown = cb.normalize_content([{"type": "future-contentful-kind", "text": "DATA"},
                                        {"type": "text", "text": "cap"}])
check("UNKNOWN content block type is surfaced (not silently lost)",
      unknown == ["future-contentful-kind"] and blocks == [{"type": "text", "text": "cap"}])

blocks, unknown = cb.normalize_content({"weird": "object"})
check("non-string/non-list content -> None (unusable shape)", blocks is None)

# --- select_turn: session identity + selection ------------------------------------------
objs = [
    {"type": "file-history-snapshot", "x": 1},
    {"type": "user", "uuid": "U1", "parentUuid": "root", "sessionId": "S",
     "message": {"role": "user", "content": "decide the date"}},
    {"type": "api-request-blob", "data": "ignore"},
    {"type": "assistant", "uuid": "A0", "parentUuid": "U1", "sessionId": "S",
     "message": {"role": "assistant", "content": [{"type": "tool_use", "text": "{}"}]}},
    {"type": "user", "uuid": "U2", "parentUuid": "A0", "sessionId": "S",
     "message": {"role": "user", "content": [{"type": "tool_result", "text": "Fri"}]}},
    {"type": "assistant", "uuid": "A1", "parentUuid": "U2", "sessionId": "S",
     "message": {"role": "assistant", "content": [
         {"type": "thinking", "text": "COT"}, {"type": "text", "text": "Decision: Friday"}]}},
    # a DIFFERENT session's assistant message must be excluded
    {"type": "assistant", "uuid": "X9", "parentUuid": "", "sessionId": "OTHER",
     "message": {"role": "assistant", "content": [{"type": "text", "text": "other session"}]}},
    {"type": "attachment", "foo": 1},
]
prompt, assistant, stats = cb.select_turn(objs, "S")
check("final assistant = last assistant with visible text (A1, not tool-only A0)",
      assistant is not None and assistant["uuid"] == "A1")
check("human prompt resolved to the string-content user U1",
      prompt is not None and prompt["uuid"] == "U1"
      and prompt["blocks"] == [{"type": "text", "text": "decide the date"}])
check("assistant forwards thinking type-only + decision text",
      {"type": "thinking"} in assistant["blocks"]
      and {"type": "text", "text": "Decision: Friday"} in assistant["blocks"])
check("other-session line excluded and counted", stats["other_session_lines"] == 1)
check("known metadata line types NOT flagged unrecognized",
      stats["unrecognized_line_types"] == {})

# unrecognized contentful line type must be surfaced, never silently dropped
objs2 = objs + [{"type": "brand-new-contentful-line", "message": {"role": "user",
                 "content": "maybe important"}}]
_, _, stats2 = cb.select_turn(objs2, "S")
check("unrecognized top-level line type surfaced (not silently lost)",
      stats2["unrecognized_line_types"].get("brand-new-contentful-line") == 1)

# --- read_transcript: partial / unparseable last line -----------------------------------
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tf:
    tf.write('{"type":"user","uuid":"U1","sessionId":"S","message":{"role":"user","content":"ok"}}\n')
    tf.write('{"type":"assistant","uuid":"A1","parentUuid":"U1","sessionId":"S","message":{"role":"assistant","content":[{"type":"text","text":"done"}]}}\n')
    tf.write('{"type":"user","uuid":"U2","sessionId":"S","message":{"role":"user","content":"partial last line cut off her')  # no newline, truncated JSON
    path = tf.name
objs3, skipped = cb.read_transcript(path)
os.unlink(path)
check("partial/unparseable last line is skipped and counted (not fatal)",
      skipped == 1 and len(objs3) == 2)
p3, a3, _ = cb.select_turn(objs3, "S")
check("turn still selected despite truncated trailing line",
      p3 is not None and a3 is not None and a3["uuid"] == "A1")

print()
if failures:
    print("FAILURES: %d -> %s" % (len(failures), failures)); sys.exit(1)
print("ALL CONTRACT TESTS PASSED")

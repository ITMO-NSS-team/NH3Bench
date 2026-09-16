import json
import http.client
import os
import unittest
from unittest.mock import patch

from nh3twin.llm_policy import CodexCLIPolicy, ZAIChatPolicy, parse_action


class CodexEventParsingTests(unittest.TestCase):
    def test_extracts_last_message_and_usage(self):
        events = [
            {"type": "thread.started", "thread_id": "t"},
            {"type": "item.completed", "item": {
                "type": "agent_message", "text": "ДЕЙСТВИЕ: NO_OP"}},
            {"type": "turn.completed", "usage": {
                "input_tokens": 100, "cached_input_tokens": 80,
                "output_tokens": 12, "reasoning_output_tokens": 5}},
        ]
        stdout = "\n".join(json.dumps(e, ensure_ascii=False) for e in events)
        text, usage, tool_calls, errors = CodexCLIPolicy._parse_events(stdout)
        self.assertEqual(text, "ДЕЙСТВИЕ: NO_OP")
        self.assertEqual(usage["output_tokens"], 12)
        self.assertEqual(tool_calls, 0)
        self.assertEqual(errors, [])

    def test_counts_tool_calls(self):
        event = {"type": "item.completed", "item": {
            "type": "command_execution", "status": "completed"}}
        _, _, tool_calls, _ = CodexCLIPolicy._parse_events(json.dumps(event))
        self.assertEqual(tool_calls, 1)


class ActionParsingTests(unittest.TestCase):
    def test_russian_action_marker(self):
        aid, status = parse_action("Кратко.\nДЕЙСТВИЕ: NO_OP", {"NO_OP"})
        self.assertEqual((aid, status), ("NO_OP", "ok"))


class ZAIChatPolicyTests(unittest.TestCase):
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "ДЕЙСТВИЕ: NO_OP"}}],
                "usage": {
                    "prompt_tokens": 123,
                    "completion_tokens": 45,
                    "prompt_tokens_details": {"cached_tokens": 20},
                },
            }).encode("utf-8")

    @patch.dict(os.environ, {"ZAI_API_KEY": "test-only"}, clear=False)
    @patch("urllib.request.urlopen")
    def test_coding_plan_request_and_usage(self, urlopen):
        urlopen.return_value = self._Response()
        policy = ZAIChatPolicy()
        text, tokens, cost, error = policy._call("test")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(text, "ДЕЙСТВИЕ: NO_OP")
        self.assertEqual((tokens, cost, error), (45, 0.0, None))
        self.assertEqual(policy.stats.input_tokens, 123)
        self.assertEqual(policy.stats.cached_input_tokens, 20)
        self.assertEqual(payload["model"], "glm-5.3")
        self.assertEqual(payload["reasoning_effort"], "max")
        self.assertEqual(
            request.full_url,
            "https://api.z.ai/api/coding/paas/v4/chat/completions",
        )
        self.assertNotIn("test-only", request.full_url)
        self.assertNotIn("test-only", request.data.decode("utf-8"))

    @patch.dict(os.environ, {"ZAI_API_KEY": "test-only"}, clear=False)
    @patch("urllib.request.urlopen")
    def test_remote_disconnect_becomes_retryable_error(self, urlopen):
        urlopen.side_effect = http.client.RemoteDisconnected(
            "remote closed without response")
        policy = ZAIChatPolicy()
        text, tokens, cost, error = policy._call("test")
        self.assertEqual((text, tokens, cost), ("", 0, 0.0))
        self.assertIn("network:", error)


if __name__ == "__main__":
    unittest.main()

"""Safe client measurements with local HTTP fixtures, never organizer API."""
import json
import unittest

from app.provider import Client, ProviderError, normalize_config
from app.telemetry import RATE_HEADERS, content_sizes, numeric_usage, size
from tests.test_qwen import SECRET, api, response


class TelemetryTests(unittest.TestCase):
    def test_unicode_sizes_are_explicit_not_token_counts(self):
        self.assertEqual(size('я'), {'characters': 1, 'utf8_bytes': 2})
        self.assertNotIn('tokens', size('я'))
        self.assertIsNone(content_sizes('{"marker":"</think>"}')['reasoning_prefix_size'])
        self.assertIsNone(content_sizes('```json\n{"ok":true}\n```')['reasoning_prefix_size'])

    def test_only_numeric_usage_is_retained(self):
        usage = {'prompt_tokens': 5, 'completion_tokens_details': {'reasoning_tokens': 9, 'other': 0},
                 'provider_note': SECRET, 'bad': True, 'negative': -1, 'infinite': float('inf'),
                 'nan': float('nan'), 'x-invalid-name': 123, 'fraction': 1.5}
        self.assertEqual(numeric_usage(usage), {'prompt_tokens': 5, 'completion_tokens_details.reasoning_tokens': 9,
                                               'completion_tokens_details.other': 0, 'fraction': 1.5})
        self.assertIsNone(numeric_usage(None));self.assertIsNone(numeric_usage({'note': SECRET}))

    def test_provider_keeps_sizes_usage_and_finish_without_reasoning_text(self):
        thought = 'PRIVATE_REASONING_TEXT'
        content = '<think>'+thought+'</think>\n{"ok":true}'
        body = response(content, usage={'prompt_tokens': 4, 'completion_tokens': 25,
                        'completion_tokens_details': {'reasoning_tokens': 20}, 'private': SECRET})
        with api([(200, body)]) as (url, received):
            client = Client(normalize_config({'base_url': url, 'model': 'local-fixture', 'max_tokens': 321}))
            self.assertEqual(client.complete([{'role': 'user', 'content': 'JSON please'}], 'test', 1), content)
            call = client.calls[0]
            self.assertEqual(call['message_content_size'], size(content))
            self.assertEqual(call['reasoning_prefix_size'], size('<think>'+thought+'</think>'))
            self.assertEqual(call['usage_numeric']['completion_tokens_details.reasoning_tokens'], 20)
            self.assertEqual(call['input_tokens'], 4);self.assertEqual(call['output_tokens'], 25)
            self.assertEqual(call['finish_reason'], 'stop');self.assertIsNone(call['parsed_json_size'])
            self.assertNotIn(thought, json.dumps(call));self.assertNotIn(SECRET, json.dumps(call))
            self.assertEqual(set(received[0][2]), {'model', 'messages', 'temperature', 'max_tokens', 'stream'})
            self.assertEqual(received[0][2]['max_tokens'], 321)

    def test_truncated_content_is_measured_without_hidden_retry(self):
        body = response('partial output', usage={'prompt_tokens': 1, 'completion_tokens': 3})
        body['choices'][0]['finish_reason'] = 'length'
        with api([(200, body)]) as (url, received):
            client = Client(normalize_config({'base_url': url, 'model': 'local-fixture'}))
            with self.assertRaises(ProviderError):client.complete([], 'test', 1)
            self.assertEqual(client.calls[0]['message_content_size'], size('partial output'))
            self.assertEqual(client.calls[0]['finish_reason'], 'length')
            self.assertIsNone(client.calls[0]['parsed_json_size'])
            self.assertEqual(len(received), 1)

    def test_429_header_allowlist_and_unknown_values(self):
        headers = {'Retry-After': '30', 'X-RateLimit-Limit-Requests': '20',
                   'X-RateLimit-Remaining-Requests': '0', 'X-RateLimit-Reset-Requests': '1m30s',
                   'X-RateLimit-Limit-Tokens': '10000', 'X-RateLimit-Remaining-Tokens': SECRET,
                   'Authorization': SECRET, 'Set-Cookie': SECRET, 'X-Private': SECRET}
        with api([(429, SECRET.encode(), headers)]) as (url, received):
            client = Client(normalize_config({'base_url': url, 'model': 'local-fixture', 'api_key': SECRET}))
            with self.assertRaises(ProviderError):client.complete([], 'test', 1)
            call = client.calls[0]
            self.assertEqual(set(call['rate_limit_headers']), set(RATE_HEADERS))
            self.assertEqual(call['rate_limit_headers']['Retry-After'], '30')
            self.assertEqual(call['rate_limit_headers']['X-RateLimit-Reset-Requests'], '1m30s')
            self.assertIsNone(call['rate_limit_headers']['X-RateLimit-Remaining-Tokens'])
            self.assertIsNone(call['rate_limit_headers']['X-RateLimit-Reset-Tokens'])
            self.assertIsNone(call['input_tokens']);self.assertIsNone(call['message_content_size'])
            self.assertIsNone(call['usage_numeric']);self.assertIsNone(call['finish_reason'])
            self.assertNotIn(SECRET, json.dumps(call));self.assertNotIn('Authorization', json.dumps(call))
            self.assertNotIn('Set-Cookie', json.dumps(call));self.assertEqual(len(received), 1)


if __name__ == '__main__': unittest.main()

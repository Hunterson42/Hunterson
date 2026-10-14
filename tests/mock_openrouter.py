"""
A stand-in for OpenRouter, for testing the probe without spending money.
Serves the endpoint listing from a saved census day, and answers chat
requests with a streamed reply in OpenRouter's format, including the final
usage record with a cost. Two tags behave badly on purpose: one is refused
with HTTP 404, one breaks with an error part way through the stream.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CENSUS_DAY = None          # folder of saved endpoint listings
REFUSE_TAG = "parasail/fp8"
BREAK_TAG = "venice/fp8"
SEEN = []                  # every chat request body received


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        prefix = "/api/v1/models/"
        if self.path.startswith(prefix) and self.path.endswith("/endpoints"):
            model = self.path[len(prefix):-len("/endpoints")]
            path = os.path.join(CENSUS_DAY, "endpoints", model.replace("/", "__") + ".json")
            if os.path.exists(path):
                with open(path) as f:
                    return self._json(200, json.load(f))
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        SEEN.append(body)
        if self.headers.get("Authorization") != "Bearer test-key":
            return self._json(401, {"error": {"message": "bad key"}})
        tag = ((body.get("provider") or {}).get("only") or ["direct"])[0]
        if tag == REFUSE_TAG:
            return self._json(404, {"error": {"code": 404, "message": "No endpoints found"}})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def send(obj):
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()

        self.wfile.write(b": OPENROUTER PROCESSING\n\n")
        provider = tag.split("/")[0]
        words = ["ISLAND DUKE Prospero\n", "LAST SPEAKER Miranda\n"] + ["word "] * 60
        for i, w in enumerate(words):
            send({"id": "gen-1", "provider": provider,
                  "choices": [{"index": 0, "delta": {"content": w}, "finish_reason": None}]})
            if tag == BREAK_TAG and i == 5:
                send({"id": "gen-1", "error": {"code": 502, "message": "upstream died"}})
                return
        send({"id": "gen-1", "provider": provider,
              "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}]})
        prompt_tokens, completion_tokens = 7900, 500
        send({"id": "gen-1", "provider": provider, "choices": [],
              "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                        "completion_tokens_details": {"reasoning_tokens": 0},
                        "prompt_tokens_details": {"cached_tokens": 0},
                        "cost": 0.00123}})
        self.wfile.write(b"data: [DONE]\n\n")


def start(census_day, port=0):
    global CENSUS_DAY
    CENSUS_DAY = census_day
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    s = start(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8790)
    print(f"mock on {s.server_address}")
    threading.Event().wait()

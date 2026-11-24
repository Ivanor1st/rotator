"""Regression : un fournisseur qui repond en gzip (Gemini) ne doit pas casser le flux SSE.

Avant le correctif, main.py relayait response.aiter_raw() (octets bruts, donc
encore compresses) sans l'en-tete Content-Encoding : le client recevait du gzip
illisible. L'adaptateur Anthropic decodait ces octets en UTF-8 et ne trouvait
aucune ligne "data:".
"""
import asyncio
import gzip
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import _anthropic_stream_adapter  # noqa: E402

SSE = (
    'data: {"choices":[{"delta":{"content":"Bonjour","role":"assistant"},"finish_reason":null,"index":0}]}\n\n'
    'data: {"choices":[{"delta":{"content":" monde"},"finish_reason":"stop","index":0}]}\n\n'
    "data: [DONE]\n\n"
)


def _gzip_response_stream():
    """Reponse en flux dont le corps est gzip + Content-Encoding: gzip."""
    body = gzip.compress(SSE.encode("utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream", "content-encoding": "gzip"},
            content=body,
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_anthropic_adapter_reads_gzipped_upstream():
    async def run():
        out = []
        async with _gzip_response_stream() as client:
            async with client.stream("POST", "http://upstream/v1/chat/completions") as resp:
                async for ev in _anthropic_stream_adapter(resp, "coding", "msg_1"):
                    out.append(ev)
        return "".join(out)

    text = asyncio.run(run())
    deltas = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: ") and "text_delta" in line:
                deltas.append(json.loads(line[6:])["delta"]["text"])
    assert "".join(deltas) == "Bonjour monde"

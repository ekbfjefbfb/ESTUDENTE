import msgpack
from fastapi.responses import Response
from typing import Any

class MessagePackResponse(Response):
    media_type = "application/x-msgpack"

    def render(self, content: Any) -> bytes:
        return msgpack.packb(content, use_bin_type=True)

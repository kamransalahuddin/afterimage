from __future__ import annotations

from urllib.parse import quote

from fastapi.responses import Response


def file_response(data: bytes, mime: str, filename: str, *, inline: bool = False) -> Response:
    ascii_name = "".join(c if c.isascii() and c.isprintable() and c not in '"\\' else "_" for c in filename)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )


def png_response(data: bytes) -> Response:
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "no-store, private"})

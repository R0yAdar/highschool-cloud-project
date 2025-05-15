""" This is the streaming server, it is used to stream mp4 files using HTTPS 
    and HTTP_206_PARTIAL_CONTENT responses. It follows RFC7233, and runs with
    fastapi above uvicorn ASGI server."""

# Official
import os
import shutil

# 3rd Party
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse, RedirectResponse

# Mine
import peewee_db as  pwDB
from file_encryption import EncryptedFile

def send_bytes_range_requests(
    file_obj, start: int, end: int, chunk_size: int = 10_000):
    """Send a file in chunks according to RFC7233
    `start` and `end` parameters are both inclusive.
    """
    with file_obj as f:
        f.seek(start)
        distance = end - start
        while distance >= 0:
            read_size = min(chunk_size, distance)
            yield f.read(read_size)
            distance -= read_size


def _get_range_header(range_header: str, file_size: int) -> tuple[int, int]: 
    """ Converts request into a legal byte-range request, 
        if it's invalid -> raises an HTTPException."""  
    try:
        h = range_header.replace("bytes=", "").split("-")
        start = int(h[0]) if h[0] != "" else 0
        end = int(h[1]) if h[1] != "" else file_size - 1
        
    except ValueError:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=f"Invalid request range (Range:{range_header!r})",)

    if start > end or start < 0 or end > file_size - 1:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=f"Invalid request range (Range:{range_header!r})",)
    
    return start, end


async def range_requests_response(
    request: Request, file_path: str, content_type: str
) -> StreamingResponse:
    """ Streams a video using HTTP_206_PARTIAL_CONTENT responses..."""
    if os.path.exists(file_path.replace('Files', 'VideoCache')):
        pass
    else:
        async with EncryptedFile(file_path).get_read(ownership=False) as file:
            shutil.copy(file.name, file_path.replace('Files', 'VideoCache'))
    
    file_path = file_path.replace('Files', 'VideoCache')

    file_size = os.stat(file_path).st_size
    range_header = request.headers.get("range")

    headers = {
        "content-type": content_type,
        "accept-ranges": "bytes",
        "content-encoding": "identity",
        "content-length": str(file_size),
        "access-control-expose-headers": (
            "content-type, accept-ranges, content-length, "
            "content-range, content-encoding"
        ),
    }
    
    start = 0
    end = file_size - 1 # Start counting from zero
    status_code = status.HTTP_200_OK

    if range_header:
        start, end = _get_range_header(range_header, file_size)
        size = end - start + 1 # Start counting from 1
        headers["content-length"] = str(size)
        headers["content-range"] = f"bytes {start}-{end}/{file_size}"
        status_code = status.HTTP_206_PARTIAL_CONTENT
    response = StreamingResponse(
        send_bytes_range_requests(open(file_path, mode="rb"), start, end),
        headers=headers,
        status_code=status_code,
    )
    return response


app = FastAPI()

# Defining endpoints and running the server

@app.get("/")
async def redirect() -> RedirectResponse:
    return RedirectResponse('/watch')

@app.get("/watch/")
async def get_video(request: Request, v: str) -> StreamingResponse:
    # get file path with video_id + key
    path = 'default.mp4'
    if stream := await pwDB.get_stream_by_token(v):
        path = (await pwDB.async_manager._get_foreign_key_target(stream, 'file')).real_path    

    return await range_requests_response(   
            request, file_path=f"{path}", content_type="video/mp4")

if __name__ == "__main__":
    uvicorn.run("streaming_server:app", host='0.0.0.0', port=443, ssl_keyfile='rap.key',
                ssl_certfile='rap.crt', log_level="info", reload=True)
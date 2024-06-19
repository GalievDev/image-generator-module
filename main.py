import base64
import logging
import sys
from io import BytesIO

from fastapi import FastAPI, WebSocket
from PIL import Image
from pydantic import BaseModel
from rembg import remove

app = FastAPI(title="image-generator")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter("%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%("
                                  "levelname)s] %(name)s: %(message)s")
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

logger.info('API is starting up')


class ImageData(BaseModel):
    id: int
    name: str
    bytes: str


@app.websocket("/ws/rmbg")
async def remove_background(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        image_data = ImageData.parse_raw(data)

        image_bytes = base64.b64decode(image_data.bytes)
        image = Image.open(BytesIO(image_bytes))

        output = remove(image)

        buffered = BytesIO()
        output.save(buffered, format="PNG")
        new_bytes = base64.b64encode(buffered.getvalue()).decode('utf-8')

        await websocket.send_text(new_bytes)


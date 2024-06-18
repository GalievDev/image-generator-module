import base64
from io import BytesIO

from fastapi import FastAPI
from pydantic import BaseModel
from rembg import remove
from starlette.websockets import WebSocket

app = FastAPI()


class Image(BaseModel):
    id: int
    name: str
    bytes: str


@app.get("/")
async def root():
    return {"Hello": "World"}


@app.websocket("/ws/rmbg")
async def rmbg(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            image_data = Image.parse_raw(data)

            image_bytes = base64.b64decode(image_data.bytes)
            image = Image.open(BytesIO(image_bytes))

            output = remove(image)

            buffered = BytesIO()
            output.save(buffered, format="PNG")
            processed_image_bytes = buffered.getvalue()

            encoded_bytes = base64.b64encode(processed_image_bytes).decode('utf-8')

            response_data = Image(id=image_data.id, name=image_data.name, bytes=encoded_bytes)
            await websocket.send_text(response_data.json())

    except Exception as e:
        await websocket.send_text(f"Error processing image data: {str(e)}")
    finally:
        await websocket.close()

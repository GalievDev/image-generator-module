import base64
import logging
import sys
from io import BytesIO
from typing import List

from fastapi import FastAPI, HTTPException
from PIL import Image, ImageOps
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


def merge_images(images: List[Image.Image]) -> Image.Image:
    max_width = max(img.width for img in images)
    max_height = max(img.height for img in images)

    resized_images = []
    for img in images:
        img = ImageOps.fit(img, (max_width, max_height), Image.Resampling.BICUBIC)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        else:
            img = img.convert('RGB')
        resized_images.append(img)

    total_height = max_height * len(resized_images)

    merged_image = Image.new('RGB', (max_width, total_height), (255, 255, 255))

    current_height = 0
    for img in resized_images:
        merged_image.paste(img, (0, current_height))
        current_height += max_height + 20

    return merged_image


@app.post("/generate_outfit/")
async def generate_outfit(images: List[ImageData]):
    pil_images = []
    for image_data in images:
        image_bytes = base64.b64decode(image_data.bytes)
        image = Image.open(BytesIO(image_bytes))
        pil_images.append(image)

    try:
        merged_image = merge_images(pil_images)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    merged_image_bytes = BytesIO()
    merged_image.save(merged_image_bytes, format='PNG')
    merged_image_bytes.seek(0)

    merged_image_base64 = base64.b64encode(merged_image_bytes.read()).decode('utf-8')

    response = ImageData(id=1, name="outfit", bytes=merged_image_base64)

    return response


@app.post("/rmbg/")
async def remove_background(item: ImageData):
    try:
        image_bytes = base64.b64decode(item.bytes)
        image = Image.open(BytesIO(image_bytes))

        output = remove(image)

        buffered = BytesIO()
        output.save(buffered, format="PNG")
        new_bytes = base64.b64encode(buffered.getvalue()).decode('utf-8')

        response_data = ImageData(id=item.id, name=item.name, bytes=new_bytes)

        return response_data
    except Exception as e:
        logger.error(str(e))


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


class ClothType:
    TOP = "TOP"
    OUTWEAR = "OUTWEAR"
    UNDERWEAR = "UNDERWEAR"
    FOOTWEAR = "FOOTWEAR"
    ACCESSORY = "ACCESSORY"
    NONE = "NONE"


class Cloth(BaseModel):
    name: str
    link: str
    description: str
    type: str
    image: str


class ImageData(BaseModel):
    id: int
    name: str
    bytes: str


def merge_images(images: List[tuple], spacing: int = 10) -> Image.Image:
    max_width = max(img.width for _, img in images)
    max_height = max(img.height for _, img in images)

    resized_images = []
    for cloth_type, img in images:
        img = ImageOps.fit(img, (max_width, max_height), Image.Resampling.LANCZOS)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        else:
            img = img.convert('RGB')
        resized_images.append((cloth_type, img))

    total_width = max_width * 2 + spacing
    total_height = max_height * 3 + spacing * 2
    merged_image = Image.new('RGB', (total_width, total_height), (255, 255, 255))

    current_y = 0
    for i, (cloth_type, img) in enumerate(resized_images):
        if cloth_type in [ClothType.TOP, ClothType.OUTWEAR]:
            x_offset = 0 if cloth_type == ClothType.TOP else max_width + spacing
            merged_image.paste(img, (x_offset, current_y))
        elif cloth_type in [ClothType.UNDERWEAR, ClothType.ACCESSORY]:
            x_offset = 0 if cloth_type == ClothType.UNDERWEAR else max_width + spacing
            merged_image.paste(img, (x_offset, current_y))
        elif cloth_type == ClothType.FOOTWEAR:
            merged_image.paste(img, (0, current_y))
        if (cloth_type == ClothType.FOOTWEAR or i == len(resized_images) - 1 or resized_images[i+1][0] in
                [ClothType.TOP, ClothType.UNDERWEAR]):
            current_y += max_height + spacing

    return merged_image


@app.post("/generate_outfit/")
async def generate_outfit(clothes: List[Cloth]):
    type_order = [ClothType.TOP, ClothType.OUTWEAR, ClothType.UNDERWEAR, ClothType.FOOTWEAR,
                  ClothType.ACCESSORY, ClothType.NONE]

    clothes.sort(key=lambda x: type_order.index(x.type))

    images = []
    for cloth in clothes:
        try:
            image_bytes = base64.b64decode(cloth.image)
            image = Image.open(BytesIO(image_bytes))
            images.append((cloth.type, image))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error decoding image {cloth.name}: {str(e)}")

    try:
        merged_image = merge_images(images)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error merging images: {str(e)}")

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

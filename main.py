import base64
import logging
import sys
from io import BytesIO
from math import ceil

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


class Outfit(BaseModel):
    name: str
    description: str
    image: str


class ImageData(BaseModel):
    id: int
    name: str
    bytes: str


CLOTH_TYPE_ORDER = [ClothType.TOP, ClothType.OUTWEAR, ClothType.UNDERWEAR, ClothType.FOOTWEAR,
                    ClothType.ACCESSORY, ClothType.NONE]


def merge_images_for_outfit(images: list[tuple[str, Image.Image]], spacing: int = 10) -> Image.Image:
    max_width = max(image.width for cloth_type, image in images)
    max_height = max(image.height for cloth_type, image in images)
    outwear_indexes = set()
    accessory_indexes = set()
    for i, (cloth_type, image) in enumerate(images):
        image = ImageOps.fit(image, (max_width, max_height), Image.Resampling.LANCZOS,)
        # ratio = (max_width / image.width + max_height / image.height) / 2
        # image = ImageOps.scale(image, ratio)
        if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
            background = Image.new('RGB', (max_width, max_height), (255, 255, 255))
            background.paste(image, (0, 0), mask=image)
            image = background
        else:
            image = image.convert('RGB')
        images[i] = (cloth_type, image)
        if cloth_type == ClothType.OUTWEAR:
            outwear_indexes.add(i)
        elif cloth_type == ClothType.ACCESSORY:
            accessory_indexes.add(i)
    number_of_main_attributes = len(images) - len(outwear_indexes) - len(accessory_indexes)
    total_width = max_width * (1 + len(outwear_indexes)) + spacing * len(outwear_indexes)
    total_height = max_height * number_of_main_attributes + (number_of_main_attributes - 1) * spacing
    if len(outwear_indexes) == 0:
        accessory_per_row = ceil(len(accessory_indexes) / number_of_main_attributes)
        total_width += accessory_per_row * (max_width + spacing)
    else:
        number_of_accessory_rows = ceil(len(accessory_indexes) / len(outwear_indexes))
        if number_of_accessory_rows + 1 > number_of_main_attributes:
            total_height = (number_of_accessory_rows + 1) * max_height + spacing * number_of_accessory_rows
    merged_image = Image.new("RGB", (total_width * 2, total_height * 2), (255, 255, 255))
    main_attributes_y_offset = 0
    outwear_x_offset = spacing + max_width
    accessory_x_offset = outwear_x_offset
    accessory_y_offset = 0 if len(outwear_indexes) == 0 else spacing + max_height
    for i, (cloth_type, image) in enumerate(images):
        w = image.width
        h = image.height
        if i not in accessory_indexes and i not in outwear_indexes:
            merged_image.paste(image, (0, main_attributes_y_offset))
            main_attributes_y_offset += h + spacing
        elif i in outwear_indexes:
            merged_image.paste(image, (outwear_x_offset, 0))
            outwear_x_offset += spacing + w
        elif i in accessory_indexes:
            merged_image.paste(image, (accessory_x_offset, accessory_y_offset))
            if accessory_x_offset + spacing + max_width > total_width // 2:
                accessory_y_offset += spacing + h
                accessory_x_offset = spacing + w
            else:
                accessory_x_offset += spacing + w
    return merged_image


@app.post("/generate_outfit/")
async def generate_outfit(clothes: list[Cloth]):
    clothes.sort(key=lambda x: CLOTH_TYPE_ORDER.index(x.type))
    images = []
    for cloth in clothes:
        try:
            image = Image.open(BytesIO(base64.b64decode(cloth.image)))
            # bbox_image = image.crop(image.getbbox(alpha_only=True))
            images.append((cloth.type, image))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error decoding image {cloth.name}: {str(e)}")
    try:
        merged_image = merge_images_for_outfit(images)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error merging images: {str(e)}")
    merged_image_bytes = BytesIO()
    merged_image.save(merged_image_bytes, format='PNG')
    merged_image_bytes.seek(0)
    merged_image_base64 = base64.b64encode(merged_image_bytes.read()).decode('utf-8')
    response = ImageData(id=1, name="outfit", bytes=merged_image_base64)
    return response


@app.post("/generate_capsule/")
async def generate_capsule(outfits: list[Outfit]):
    # TODO: Later
    return


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


@app.get("/")
async def root():
    return {
        "name": "Image Generator API",
        "description": "API for removing image background and generating images"
    }

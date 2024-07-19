import base64
import logging
import sys
from io import BytesIO
from typing import List, Tuple

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


def process_images(images: List[Tuple]) -> List[Image.Image]:
    processed_images = []

    for cloth_type, img in images:
        bbox = img.getbbox()
        img_cropped = img.crop(bbox)
        if img_cropped.mode in ('RGBA', 'LA') or (img_cropped.mode == 'P' and 'transparency' in img_cropped.info):
            background = Image.new('RGB', img_cropped.size, (255, 255, 255))
            background.paste(img_cropped, mask=img_cropped.split()[3])  # 3 - это альфа-канал
            img_cropped = background
        else:
            img_cropped = img_cropped.convert('RGB')
        processed_images.append((cloth_type, img_cropped))

    return processed_images


def merge_group(images: List[Image.Image], spacing: int = 10) -> Image.Image:
    total_width = max(img.width for img in images)
    total_height = sum(img.height for img in images) + spacing * (len(images) - 1)
    merged_image = Image.new('RGB', (total_width, total_height), (255, 255, 255))

    current_y = 0
    for img in images:
        x_offset = (total_width - img.width) // 2
        merged_image.paste(img, (x_offset, current_y))
        current_y += img.height + spacing

    return merged_image


def merge_images_for_outfit(images: List[Tuple[str, Image.Image]], spacing: int = 10) -> Image.Image:
    processed_images = process_images(images)

    top_img = next((img for cloth_type, img in processed_images if cloth_type == ClothType.TOP), None)
    outwear_img = next((img for cloth_type, img in processed_images if cloth_type == ClothType.OUTWEAR), None)
    underwear_img = next((img for cloth_type, img in processed_images if cloth_type == ClothType.UNDERWEAR), None)
    footwear_img = next((img for cloth_type, img in processed_images if cloth_type == ClothType.FOOTWEAR), None)
    accessory_imgs = [img for cloth_type, img in processed_images if cloth_type == ClothType.ACCESSORY]

    base_group = [top_img, underwear_img, footwear_img]
    overlay_group = [outwear_img] + accessory_imgs

    base_image = merge_group([img for img in base_group if img], spacing)
    overlay_image = merge_group([img for img in overlay_group if img], spacing)

    max_width = (base_image.width if base_image else 0) + (overlay_image.width if overlay_image else 0) + spacing
    max_height = max(base_image.height if base_image else 0, overlay_image.height if overlay_image else 0)

    merged_image = Image.new('RGB', (max_width, max_height), (255, 255, 255))

    if base_image:
        base_x = (max_width - base_image.width - (overlay_image.width if overlay_image else 0) - spacing) // 2
        merged_image.paste(base_image, (base_x, 0))

    if overlay_image:
        overlay_x = base_x + base_image.width + spacing
        merged_image.paste(overlay_image, (overlay_x, 0))

    return merged_image


def merge_images_for_capsule(images: list[Image.Image], spacing: int = 10) -> Image.Image:
    capsule_image_width = capsule_image_height = 0
    for image in images:
        capsule_image_height += image.height
        capsule_image_width += image.width
    avg_outfit_image_box = (int(capsule_image_width / len(images)), int(capsule_image_height / len(images)))
    capsule_image = Image.new("RGB", (avg_outfit_image_box[0] * len(images) + spacing * (len(images) - 1),
                                      avg_outfit_image_box[1]), (255, 255, 255))
    x_offset = 0
    real_size = [0, 0]
    for image in images:
        factor = min(avg_outfit_image_box[0] / image.width, avg_outfit_image_box[1] / image.height)
        scaled_image = ImageOps.scale(image, factor)
        real_size[0] += scaled_image.width
        real_size[1] = max(real_size[1], scaled_image.height)
        capsule_image.paste(scaled_image, (x_offset, 0))
        x_offset += spacing + scaled_image.width
    return capsule_image.crop((0, 0, real_size[0] + spacing * (len(images) - 1), real_size[1]))


@app.post("/generate_outfit/")
async def generate_outfit(clothes: List[Cloth]):
    clothes.sort(key=lambda x: CLOTH_TYPE_ORDER.index(x.type))
    images = []
    for cloth in clothes:
        try:
            image = Image.open(BytesIO(base64.b64decode(cloth.image)))
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
async def generate_capsule(outfits: List[Outfit]):
    images = []
    for outfit in outfits:
        try:
            images.append(Image.open(BytesIO(base64.b64decode(outfit.image))))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Error decoding image: {str(exc)}")
    try:
        merged_image = merge_images_for_capsule(images)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error merging images: {str(exc)}")
    merged_image_bytes = BytesIO()
    merged_image.save(merged_image_bytes, format='PNG')
    merged_image_bytes.seek(0)
    merged_image_base64 = base64.b64encode(merged_image_bytes.read()).decode('utf-8')
    response = ImageData(id=1, name="capsule", bytes=merged_image_base64)
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


@app.get("/")
async def root():
    return {
        "name": "Image Generator API",
        "description": "API for removing image background and generating images"
    }

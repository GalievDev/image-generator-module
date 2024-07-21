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
    id: int
    name: str
    description: str
    image: int
    clothes: List[int]


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


def merge_images_for_capsule(top_list: list[Image.Image], underwear_list: list[Image.Image],
                             footwear_list: list[Image.Image], outwear_list: list[Image.Image],
                             accessory_list: list[Image.Image], spacing: int = 10) -> Image.Image:
    def paste_row(main_image: Image.Image, images: list[Image.Image], x_offset: int, y_offset: int,
                  real_width: int) -> (Image.Image, int):
        for image in images:
            main_image.paste(image, (x_offset + int((item_width - image.width) / 2),
                                     y_offset + int((item_height - image.height) / 2)))
            real_width = real_width + spacing + item_width if x_offset >= real_width else real_width
            x_offset += spacing + item_width
        return main_image, real_width

    item_width = item_height = 0
    for image in top_list + underwear_list + footwear_list + outwear_list + accessory_list:
        item_width = max(item_height, image.width)
        item_height = max(item_height, image.height)
    max_items_in_row = max(len(top_list) + len(outwear_list), len(accessory_list), len(underwear_list),
                           len(footwear_list))
    max_items_in_col = ((1 if len(top_list) + len(outwear_list) > 0 else 0) + (1 if len(underwear_list) > 0 else 0)
                        + (1 if len(accessory_list) > 0 else 0) + (1 if len(footwear_list) > 0 else 0))
    fake_width = max_items_in_row * item_width + (max_items_in_row - 1) * spacing
    fake_height = max_items_in_col * item_height + (max_items_in_col - 1) * spacing
    main_image = Image.new("RGB", (fake_width, fake_height), (255, 255, 255))
    real_width = -spacing
    x_offset = y_offset = 0
    main_image, real_width = paste_row(main_image, top_list + outwear_list, x_offset, y_offset, real_width)
    y_offset += spacing + item_height
    main_image, real_width = paste_row(main_image, accessory_list, x_offset, y_offset, real_width)
    y_offset += spacing + item_height
    main_image, real_width = paste_row(main_image, underwear_list, x_offset, y_offset, real_width)
    y_offset += spacing + item_height
    main_image, real_width = paste_row(main_image, footwear_list, x_offset, y_offset, real_width)
    return main_image.crop((0, 0, real_width, fake_height))


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
async def generate_capsule(clothes: list[Cloth]):
    tops = []
    underwears = []
    footwears = []
    accessories = []
    outwears = []
    for cloth in clothes:
        try:
            image = Image.open(BytesIO(base64.b64decode(cloth.image)))
            image = image.crop(image.getbbox())
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Error decoding image {cloth.name}: {str(exc)}")
        if cloth.type == ClothType.TOP:
            tops.append(image)
        elif cloth.type == ClothType.UNDERWEAR:
            underwears.append(image)
        elif cloth.type == ClothType.FOOTWEAR:
            footwears.append(image)
        elif cloth.type == ClothType.OUTWEAR:
            outwears.append(image)
        elif cloth.type == ClothType.ACCESSORY:
            accessories.append(image)
    try:
        merged_image = merge_images_for_capsule(top_list=tops, underwear_list=underwears, footwear_list=footwears,
                                                outwear_list=outwears, accessory_list=accessories)
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

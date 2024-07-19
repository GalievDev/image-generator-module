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
    clothes: list[Cloth]


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


def merge_images_for_capsule(outfits: list[Outfit], spacing: int = 10) -> Image.Image:
    try:
        tops = []
        underwears = []
        footwears = []
        outwears = []
        accessories = []
        max_top_width = max_top_height = 0
        max_underwear_width = max_underwear_height = 0
        max_footwear_width = max_footwear_height = 0
        max_outwear_width = max_outwear_height = 0
        max_accessory_width = max_accessory_height = 0
        for outfit in outfits:
            for cloth in outfit.clothes:
                try:
                    cloth_image = Image.open(BytesIO(base64.b64decode(cloth.image)))
                    cloth_image = cloth_image.crop(cloth_image.getbbox(alpha_only=True))
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"Error decoding image {cloth.name}: {str(exc)}")
                if cloth.type == ClothType.TOP:
                    tops.append(cloth_image)
                    max_top_width = max(max_top_width, cloth_image.width)
                    max_top_height = max(max_top_height, cloth_image.height)
                elif cloth.type == ClothType.UNDERWEAR:
                    underwears.append(cloth_image)
                    max_underwear_width = max(max_underwear_width, cloth_image.width)
                    max_underwear_height = max(max_underwear_height, cloth_image.height)
                elif cloth.type == ClothType.FOOTWEAR:
                    footwears.append(cloth_image)
                    max_footwear_width = max(max_footwear_width, cloth_image.width)
                    max_footwear_height = max(max_footwear_height, cloth_image.height)
                elif cloth.type == ClothType.OUTWEAR:
                    outwears.append(cloth_image)
                    max_outwear_width = max(max_outwear_width, cloth_image.width)
                    max_outwear_height = max(max_outwear_height, cloth_image.height)
                elif cloth.type == ClothType.ACCESSORY:
                    accessories.append(cloth_image)
                    max_accessory_width = max(max_accessory_width, cloth_image.width)
                    max_accessory_height = max(max_accessory_height, cloth_image.height)
        unit_width = max(max_top_width, max_underwear_width, max_footwear_width,
                         max_outwear_width, max_accessory_width)
        unit_height = max(max_underwear_height, max_outwear_height, max_footwear_height,
                          max_accessory_height, max_top_height)
        total_width = (len(tops) - 1) * spacing + len(tops) * unit_width
        total_width += (max(len(outwears), len(accessories)) - 1) * spacing + max(len(outwears), len(accessories)) * unit_width
        total_height = 2 * spacing + 3 * unit_height
        merged_image = Image.new('RGB', (total_width, total_height), (255, 255, 255))
        x_offset = y_offset = 0
        real_width = -spacing
        for top in tops:
            merged_image.paste(top, (x_offset + int((unit_width - top.width) / 2), y_offset))
            x_offset += spacing + unit_width
            real_width += spacing + unit_width
        if len(outwears) != 0:
            dx = x_offset
            for outwear in outwears:
                merged_image.paste(outwear, (x_offset + int((unit_width - outwear.width) / 2), y_offset))
                x_offset += spacing + outwear.width
            if len(accessories) != 0:
                x_offset = dx
                y_offset += spacing + unit_height
                for accessory in accessories:
                    merged_image.paste(accessory, (x_offset + int((unit_width - accessory.width) / 2), y_offset))
                    x_offset += spacing + accessory.width
            real_width += (max(len(outwears), len(accessories)) * unit_width +
                           (max(len(outwears), len(accessories)) - 1) * spacing)
        elif len(accessories) != 0:
            for accessory in accessories:
                merged_image.paste(accessory, (x_offset + int((unit_width - accessory.width) / 2), y_offset))
                x_offset += spacing + accessory.width
                real_width += spacing + unit_width
        x_offset = 0
        y_offset += spacing + unit_height
        for underwear in underwears:
            merged_image.paste(underwear, (x_offset + int((unit_width - underwear.width) / 2), y_offset))
            x_offset += spacing + underwear.width
        x_offset = 0
        y_offset += spacing + unit_height
        for footwear in footwears:
            merged_image.paste(footwear, (x_offset + int((unit_width - footwear.width) / 2), y_offset))
            x_offset += spacing + footwear.width
        return merged_image.crop((0, 0, real_width, total_height))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error merging images: {str(exc)}")


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
    merged_image = merge_images_for_capsule(outfits)
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


@app.get("/")
async def root():
    return {
        "name": "Image Generator API",
        "description": "API for removing image background and generating images"
    }

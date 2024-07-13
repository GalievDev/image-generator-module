# Image-generator-module



## Description
Module for image processing and generating.

## Features
- Image background removing from added cloth
- Image generation for outfits and clothes

## Deployed url
**There are deployed url of [module](http://10.90.136.54:5050/)** 

## Deployement
Section **for customer**

Firstly you should have to installed python 3.9 on your machine

|OS|Download Away|
|-|-|
|Windows|https://www.python.org/|
|Ubuntu|`sudo apt install python`|
|Arch Linux|`sudo pacman -S python`|


Clone the repository: 
```bash
git clone https://gitlab.pg.innopolis.university/ise25/image-generator-module
```

Install requirements:

```bash
pip install -r requirements.txt
```

Run application with this command:

```bash
uvicorn main:app --host {YOUR_URL} --port {YOUR_PORT}
```

## Used technologies
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)

from fastapi import FastAPI, File, UploadFile, Form, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from io import BytesIO
import easyocr
import pytesseract
from paddleocr import PaddleOCR
from pydantic import BaseModel
from typing import List
from PIL import Image
import base64
import numpy as np
import time
import cv2
import torch
import os

app = FastAPI()

class OCRRequest(BaseModel):
    file: str  # Строка Base64
    engine: str  # Имя движка OCR

# Здесь 'directory' должен указывать на папку, где находятся static файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Разрешаем запросы CORS от любого источника
origins = ["*"]  # Для простоты можно разрешить доступ со всех источников
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def preprocess_image_from_base64(base64_data):
    """Обрабатывает изображение, переданное в base64, для OCR."""
    image_data = base64.b64decode(base64_data)
    image = Image.open(BytesIO(image_data)).convert("RGB") 
    image = np.array(image)
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

@app.get("/")
async def root():
   return RedirectResponse(url="/index.html")

@app.get("/index.html", response_class=HTMLResponse)
async def index_page(request: Request):
    # Просто рендерим страницу без параметров engines
    return templates.TemplateResponse("index.html", {"request": request})

USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
CUDA_AVAILABLE = torch.cuda.is_available()
USE_GPU_FINAL = USE_GPU and CUDA_AVAILABLE

@app.post("/GetOcr")
async def get_ocr(request: OCRRequest):
    try:
        image = preprocess_image_from_base64(request.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка при декодировании изображения: {str(e)}")

    result = {}
    

    if request.engine == "easyocr":
        reader = easyocr.Reader(['ru'], gpu=USE_GPU_FINAL, detector='DB', recognizer = 'Transformer')
        start_time = time.time()
        ocr_result = reader.readtext(np.array(image))
        execution_time = time.time() - start_time
        result = {"engine": "easyocr", "execution_time": f"{execution_time:.2f}", "text": "\n".join([r[1] for r in ocr_result])}

    elif request.engine == "tesseract":
        start_time = time.time()
        ocr_result = pytesseract.image_to_string(image, lang='rus')
        execution_time = time.time() - start_time
        result = {"engine": "tesseract", "execution_time": f"{execution_time:.2f}", "text": ocr_result}

    elif request.engine == "paddleocr":
        ocr = PaddleOCR(use_angle_cls=True, 
                        lang='ru', 
                        gpu=USE_GPU_FINAL, 
                        drop_score=0.3, 
                        rec_algorithm='SVTR_LCNet', 
                        enable_mkldnn=True, 
                        det_model_dir="PaddleOCR/ml_PP-OCRv3_det_infer",
                        rec_model_dir="PaddleOCR/ru_mobile_v2.0_rec_infer")
        start_time = time.time()
        ocr_result = ocr.ocr(np.array(image))
        execution_time = time.time() - start_time
        text_blocks = [(item[1][0], item[1][1]) for sublist in ocr_result for item in sublist]
        chunks = [block for block in text_blocks if len(block) > 0]
        result = {"engine": "paddleocr", "execution_time": f"{execution_time:.2f}", "text": "\n".join(chunk[0] for chunk in chunks)}

    else:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый движок OCR: {request.engine}")

    return {"result": result}

@app.get("/GetOcrList")
async def get_ocr_list():
    engines = ["easyocr", "tesseract", "paddleocr"]
    return {"available_engines": engines}

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8000)) 
    host = os.getenv("HOST", "0.0.0.0")

    print(f"Starting server on {host}:{port}") 

    uvicorn.run("main:app", host=host, port=port)
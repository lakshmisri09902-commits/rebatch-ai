from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
import qrcode
import os
import json
import base64
import io
from PIL import Image, ImageStat
from datetime import datetime

app = FastAPI(title="ReBatch AI Engine")

os.makedirs("static/qr_codes", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Buyer matching database classified by material type
BUYER_MATCHES = {
    "Organic / Agricultural Waste": [
        {"name": "GreenGrain Bio-Energy", "type": "Biogas Feedstock"},
        {"name": "SoilRich Compost Co.", "type": "Organic Fertilizer"}
    ],
    "Textile / Synthetic Fiber Scrap": [
        {"name": "EcoPoly Materials", "type": "Recycled Polymers"},
        {"name": "AcoustiTex Boards", "type": "Sound Insulation Panels"}
    ],
    "Dense Industrial Residue": [
        {"name": "BuildGreen Aggregates", "type": "Eco-Concrete Additive"},
        {"name": "CleanCarbon Refiners", "type": "Industrial Fuel"}
    ]
}

class ScanRequest(BaseModel):
    image_data: Optional[str] = None  # Base64 camera snapshot

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/v1/scan")
async def process_scan(data: ScanRequest):
    # Default values if image fails to parse
    detected_material = "Organic / Agricultural Waste"
    moisture_pct = 55.0
    protein_pct = 18.0
    
    if data.image_data and "," in data.image_data:
        # Decode base64 image from camera
        image_bytes = base64.b64decode(data.image_data.split(",")[1])
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        
        # Extract RGB averages & luminance from camera capture
        stat = ImageStat.Stat(img)
        r, g, b = stat.mean
        brightness = sum(stat.mean) / 3.0
        
        # Color & visual profile detection logic
        if g > r and g > b:
            # High Green content -> Agricultural / Bio Scrap
            detected_material = "Organic / Agricultural Waste"
            moisture_pct = round(min(85.0, 45.0 + (g / 255.0) * 40.0), 1)
            protein_pct = round(12.0 + (r / 255.0) * 15.0, 1)
        elif abs(r - g) < 20 and abs(g - b) < 20 and brightness < 120:
            # Dark / Dense material -> Industrial Residue
            detected_material = "Dense Industrial Residue"
            moisture_pct = round(15.0 + (brightness / 120.0) * 20.0, 1)
            protein_pct = round(5.0 + (r / 255.0) * 8.0, 1)
        else:
            # Bright or multi-color -> Textile / Fiber Scrap
            detected_material = "Textile / Synthetic Fiber Scrap"
            moisture_pct = round(8.0 + (b / 255.0) * 15.0, 1)
            protein_pct = round(2.0 + (g / 255.0) * 5.0, 1)

    # Calculate price & decay based on detected parameters
    decay_hours = round(max(6.0, 72.0 - (moisture_pct * 0.6)), 1)
    base_price = 4500.0 if "Organic" in detected_material else (6500.0 if "Textile" in detected_material else 3800.0)
    final_price = round(base_price * (1.0 + (protein_pct / 100.0) - (moisture_pct / 200.0)), 2)

    batch_id = f"BATCH-{int(datetime.utcnow().timestamp())}"
    passport_payload = {
        "batch_id": batch_id,
        "material": detected_material,
        "moisture": f"{moisture_pct}%",
        "protein": f"{protein_pct}%",
        "fair_price": f"₹{final_price}",
        "spoilage_window": f"{decay_hours} hrs"
    }
    
    qr_img = qrcode.make(json.dumps(passport_payload))
    qr_path = f"static/qr_codes/{batch_id}.png"
    qr_img.save(qr_path)

    return {
        "batch_id": batch_id,
        "detected_material": detected_material,
        "metrics": {
            "moisture": moisture_pct,
            "protein": protein_pct,
            "decay_hours": decay_hours,
            "fair_price": final_price,
            "methane_saved": round(moisture_pct * 1.2, 1)
        },
        "qr_code_url": f"/{qr_path}",
        "matches": BUYER_MATCHES.get(detected_material, BUYER_MATCHES["Organic / Agricultural Waste"])
    }

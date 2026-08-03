---
name: handwriting-reader
description: "Read handwritten text from images using vision + OCR."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [OCR, handwriting, Hindi, image, text-extraction]
    related_skills: [ocr-and-documents]
---

# Handwriting Reader

Read and transcribe handwritten text from images. Works with Hindi (Devanagari), English, numbers, and calculations.

## When to Use
- User provides an image with handwritten text
- User wants to read a note, receipt, or paper from a photo
- OCR or handwriting transcription needed

## Steps

### Step 1: Vision Analysis (Primary)
Use `vision_analyze` with a detailed prompt:

```
vision_analyze(
    image_url="<path>",
    question="This is a handwritten note. Read EVERY word carefully, character by character. Transcribe all text exactly as written. Include all numbers, dates, and calculations. Describe handwriting style and any unclear words."
)
```

### Step 2: Install OCR Tools (if needed)
```bash
pip install pytesseract Pillow
# Windows: also install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
# Linux: sudo apt install tesseract-ocr tesseract-ocr-hin
# Mac: brew install tesseract
```

### Step 3: Tesseract OCR (Backup/Detail)
```bash
python3 -c "
from PIL import Image
import pytesseract
# For Hindi + English
text = pytesseract.image_to_string(Image.open('image.png'), lang='hin+eng')
print(text)
"
```

### Step 4: Present Results
- Show full transcription in code block
- Explain each line/number
- Translate if needed (Hindi → English)
- Note handwriting style and clarity

## Pitfalls
- Poor lighting/blurry images reduce accuracy
- Vision model may misread similar Hindi characters
- Signatures are usually unreadable (intentional scribble)
- Always try vision first, Tesseract as backup

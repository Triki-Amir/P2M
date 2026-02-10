import sys
# Python 3.8 compatibility - install zoneinfo backport
if sys.version_info < (3, 9):
    try:
        import backports.zoneinfo as zoneinfo
        sys.modules['zoneinfo'] = zoneinfo
    except ImportError:
        pass

import pdf2image
from PIL import Image
import os 
from paddleocr import PaddleOCR
import subprocess
import shutil

# Initialize PaddleOCR with GPU support
print("Initializing PaddleOCR with GPU...")
ocr = PaddleOCR(lang='fr', use_gpu=True, show_log=False)

# Converting PDF to Images
resolution = 600
pdf_path = "CERT-1.pdf"

print("Converting PDF to images...")
pil_images = pdf2image.convert_from_path(
    pdf_path, 
    dpi=resolution, 
    poppler_path=r'C:\Program Files\poppler-25.12.0\Library\bin'
)

# Setup directories
os.chdir(r"C:\P2M\multilanguage-OCR-main")
file_path = r"C:\P2M\multilanguage-OCR-main\input_images"

if os.path.exists(file_path):
    shutil.rmtree(file_path)

new_folder_name = "input_images"
subprocess.call("mkdir " + new_folder_name, shell=True)

index = 1
for image in pil_images:
    print(f"Converting page {index}")
    image.save(f"input_images/page_{index}.PNG")
    index += 1

# Extracting text from images using PaddleOCR with GPU
total_pages = index - 1
text = ""

for i in range(total_pages):
    print(f"Extracting text from page {i + 1} (GPU-accelerated)...")
    image_path = f"input_images/page_{i + 1}.PNG"
    
    # Run OCR on the image
    result = ocr.ocr(image_path, cls=True)
    
    # Extract text from result
    if result[0] is not None:
        for line in result[0]:
            text += line[1][0] + "\n"
    
    text += "\n"

# Store text
print("Saving results...")
with open("unformatted.txt", "w", encoding="utf-8") as myfile:
    myfile.write(text)

# Formatting extracted text
edited_text = ""

for i in range(len(text)):
    if i > 0 and i < len(text) - 1 and text[i] == "\n" and text[i+1] != "\n" and text[i-1] != "\n":
        edited_text = edited_text + " "
    else:
        edited_text = edited_text + text[i]
        
# Storing to a text file
with open("formatted.txt", "w", encoding="utf-8") as myfile:
    myfile.write(edited_text)

print("\nOCR Complete!")
print(f"Processed {total_pages} pages with GPU acceleration")
print("Files created:")
print("  - unformatted.txt")
print("  - formatted.txt")

# Open result
os.startfile("unformatted.txt")
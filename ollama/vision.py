from ollama import chat

path = 'avis.jpg'
prompt = (
"ACT AS AN OCR EXPERT. Accurately transcribe all visible text from the provided image (English, French, and Arabic)."
"STEP 1: Transcribe the text word-for-word with maximum accuracy, preserving paragraphs and tables."
"STEP 2: Exclude all header content and any stamps, seals, logos, signatures, company names, and director names."
"STEP 3: Output ONLY the extracted content, wrapped in a valid LaTeX document structure."
"Do NOT use sample or placeholder text. Use only text present in the image."
)
response = chat(
    model='glm-ocr:latest',
    messages=[
        {
            'role': 'user',
            'content': prompt,
            'images': [path],
        }
    ],
)

print(response.message.content)
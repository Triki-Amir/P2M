# Multilanguage_OCR: Extract text of different language from PDFs.
This end-to-end tool can extract all the information provided via. PDF and outputs a text file with the extracted text. The following is done in two simple steps, first convert the input PDF to images for all pages(store them in a folder). And the second extracts text from the generated images. One can even use the same code for multiple languages. 

## Install the following</br>
* pdf2image
* poppler
* Image
* pytesseract 

**Note:** To change the language, simply update the _lang_ attribute in _main-ocr.py_ to your desired language. The codes for the other languages can be found [here](https://github.com/tesseract-ocr/tesseract/blob/main/doc/tesseract.1.asc).

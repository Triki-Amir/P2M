import asyncio
from ocr_service.publisher import OCRPublisher

async def main():
    p = OCRPublisher()
    await p.connect()
    await p.publish_ocr_completed('1', 't', 'f.pdf', None)
    print('done')
    await p.close()

asyncio.run(main())

import asyncio
from dotenv import load_dotenv
load_dotenv()
from app.services.storage_swift import get_swift_uploader
import tempfile
import os

async def test_upload():
    # 테스트 파일 생성
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('This is a test file for Swift upload')
        test_file = f.name

    try:
        uploader = get_swift_uploader()
        result = await uploader.upload_file(test_file, 'test-upload.txt')
        print(f'Upload successful: {result}')
    except Exception as e:
        print(f'Upload failed: {e}')
    finally:
        # 테스트 파일 정리
        if os.path.exists(test_file):
            os.unlink(test_file)

if __name__ == "__main__":
    asyncio.run(test_upload())

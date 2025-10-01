"""
OpenStack Swift 업로더
"""
import os
import asyncio
from typing import List, Optional
from pathlib import Path
import logging
import mimetypes

logger = logging.getLogger(__name__)


class SwiftUploader:
    """OpenStack Swift 업로드 유틸리티"""
    
    def __init__(self, auth_url: str, username: str, password: str, 
                 project_name: str, region_name: str, container: str,
                 user_domain_name: str = "Default", project_domain_name: str = "Default"):
        self.auth_url = auth_url
        self.username = username
        self.password = password
        self.project_name = project_name
        self.region_name = region_name
        self.container = container
        self.user_domain_name = user_domain_name
        self.project_domain_name = project_domain_name
        self._client = None
    
    async def _get_client(self):
        """Swift 클라이언트 초기화 (lazy loading)"""
        if self._client is None:
            try:
                # swift client는 동기 라이브러리이므로 executor에서 실행
                try:
                    import swiftclient
                except ImportError:
                    logger.error("python-swiftclient가 설치되지 않았습니다. pip install python-swiftclient로 설치하세요.")
                    raise
                
                # 현재 사용하는 URL 로그 출력
                logger.info(f"Swift 클라이언트 초기화 시도: auth_url={self.auth_url}")
                
                # SSL 비활성화를 위한 환경변수 설정
                os.environ['PYTHONHTTPSVERIFY'] = '0'
                os.environ['CURL_CA_BUNDLE'] = ''
                
                auth_options = {
                    'auth_version': '3',
                    'user': self.username,
                    'key': self.password,
                    'tenant_name': self.project_name,  # tenant_name 사용
                    'authurl': self.auth_url,
                    'insecure': True,  # SSL 인증서 검증 무시
                    'cacert': '',  # CA 인증서 비활성화
                    'os_options': {
                        'region_name': self.region_name,
                        'user_domain_name': self.user_domain_name,
                        'project_domain_name': self.project_domain_name,
                        'identity_api_version': '3',
                        'interface': 'public',
                        'object_storage_url': 'http://116.89.191.2:8080/v1/AUTH_5ec66c4e21054d7d89b918f1fa287f24'
                    }
                }
                
                # 동기 함수를 비동기로 실행
                loop = asyncio.get_event_loop()
                self._client = await loop.run_in_executor(
                    None, 
                    lambda: swiftclient.Connection(**auth_options)
                )
                
                # 컨테이너 생성 (존재하지 않는 경우)
                await loop.run_in_executor(
                    None,
                    lambda: self._client.put_container(self.container)
                )
                
                logger.info(f"Swift 클라이언트 초기화 완료: {self.container}")
                
            except Exception as e:
                logger.error(f"Swift 클라이언트 초기화 실패: {e}")
                raise
        
        return self._client
    
    async def upload_file(
        self,
        local_path: str,
        object_key: str,
        content_type: Optional[str] = None,
        content_disposition: Optional[str] = None,
    ) -> str:
        """단일 파일 업로드 (컨텐츠 타입/디스포지션 지원)"""
        try:
            client = await self._get_client()
            
            # 파일 읽기
            try:
                import aiofiles
                async with aiofiles.open(local_path, 'rb') as f:
                    content = await f.read()
            except ImportError:
                # aiofiles가 없으면 동기 방식으로
                with open(local_path, 'rb') as f:
                    content = f.read()
            
            # 콘텐츠 타입 추론
            if not content_type:
                guessed, _ = mimetypes.guess_type(local_path)
                content_type = guessed or 'application/octet-stream'

            headers = {}
            if content_disposition:
                headers['Content-Disposition'] = content_disposition

            # 업로드 실행 (동기 함수를 비동기로)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.put_object(
                    self.container,
                    object_key,
                    content,
                    content_type=content_type,
                    headers=headers if headers else None,
                )
            )
            
            logger.info(f"파일 업로드 완료: {local_path} -> {object_key}")
            return object_key
            
        except Exception as e:
            logger.error(f"파일 업로드 실패: {local_path} -> {object_key}, 오류: {e}")
            raise

    async def upload_bytes(
        self,
        content: bytes,
        object_key: str,
        content_type: str = "application/octet-stream",
        content_disposition: Optional[str] = None,
    ) -> str:
        """바이트 데이터를 직접 업로드"""
        try:
            client = await self._get_client()

            headers = {}
            if content_disposition:
                headers['Content-Disposition'] = content_disposition

            # 업로드 실행 (동기 함수를 비동기로)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.put_object(
                    self.container,
                    object_key,
                    content,
                    content_type=content_type,
                    headers=headers if headers else None,
                )
            )
            
            logger.info(f"바이트 데이터 업로드 완료: {len(content)} bytes -> {object_key}")
            return object_key
            
        except Exception as e:
            logger.error(f"바이트 데이터 업로드 실패: {object_key}, 오류: {e}")
            raise
    
    async def upload_dir_to_swift(self, local_dir: str, prefix: str) -> List[str]:
        """
        local_dir 하위 모든 파일을 {prefix}/... 경로로 업로드.
        반환: 업로드된 오브젝트 키 리스트.
        """
        uploaded_keys = []
        local_path = Path(local_dir)
        
        if not local_path.exists():
            logger.warning(f"업로드할 디렉터리가 존재하지 않습니다: {local_dir}")
            return uploaded_keys
        
        try:
            # 모든 파일 찾기
            files_to_upload = []
            for file_path in local_path.rglob('*'):
                if file_path.is_file():
                    # 상대 경로 계산
                    relative_path = file_path.relative_to(local_path)
                    object_key = f"{prefix.rstrip('/')}/{relative_path.as_posix()}"
                    files_to_upload.append((str(file_path), object_key))
            
            logger.info(f"업로드할 파일 {len(files_to_upload)}개 발견: {local_dir}")
            
            # 병렬 업로드 (동시 5개까지)
            semaphore = asyncio.Semaphore(5)
            
            async def upload_single(local_file, object_key):
                async with semaphore:
                    return await self.upload_file(local_file, object_key)
            
            # 모든 파일 업로드
            tasks = [upload_single(local_file, object_key) 
                    for local_file, object_key in files_to_upload]
            
            uploaded_keys = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 예외 처리
            successful_uploads = []
            for i, result in enumerate(uploaded_keys):
                if isinstance(result, Exception):
                    logger.error(f"파일 업로드 실패: {files_to_upload[i][0]}, 오류: {result}")
                else:
                    successful_uploads.append(result)
            
            logger.info(f"디렉터리 업로드 완료: {len(successful_uploads)}/{len(files_to_upload)} 파일 성공")
            return successful_uploads
            
        except Exception as e:
            logger.error(f"디렉터리 업로드 실패: {local_dir}, 오류: {e}")
            raise


# 글로벌 업로더 인스턴스 (지연 초기화)
_swift_uploader = None

def get_swift_uploader() -> SwiftUploader:
    """Swift 업로더 싱글톤 인스턴스 반환"""
    global _swift_uploader
    
    if _swift_uploader is None:
        from app.core.config import settings
        
        logger.info(f"Swift 업로더 초기화: OS_AUTH_URL={settings.OS_AUTH_URL}")
        
        # 필수 설정 확인
        required_settings = [
            settings.OS_AUTH_URL,
            settings.OS_USERNAME, 
            settings.OS_PASSWORD,
            settings.OS_PROJECT_NAME,
            settings.OS_REGION_NAME,
            settings.SWIFT_CONTAINER
        ]
        
        if not all(required_settings):
            raise ValueError("Swift 업로드를 위한 필수 환경변수가 설정되지 않았습니다")
        
        _swift_uploader = SwiftUploader(
            auth_url=settings.OS_AUTH_URL,
            username=settings.OS_USERNAME,
            password=settings.OS_PASSWORD,
            project_name=settings.OS_PROJECT_NAME,
            region_name=settings.OS_REGION_NAME,
            container=settings.SWIFT_CONTAINER,
            user_domain_name=settings.OS_USER_DOMAIN_NAME,
            project_domain_name=settings.OS_PROJECT_DOMAIN_NAME
        )
    
    return _swift_uploader

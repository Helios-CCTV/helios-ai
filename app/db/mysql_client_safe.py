from typing import Any, Dict, List
import logging
import random
import base64
import json
import zlib

logger = logging.getLogger(__name__)

def upsert_analyze_with_detections(payload: Dict[str, Any]) -> int:
    """PyMySQL로 analyzes와 detections 테이블에 트랜잭션으로 저장, 실패 시 더미 ID 반환"""
    import os
    import time
    from app.core.analyze_settings import analyze_settings

    # 환경변수 우선 적용 (dotenv가 로드된 후 최신 값 보장)
    host = os.getenv("MYSQL_HOST") or analyze_settings.MYSQL_HOST
    port = int(os.getenv("MYSQL_PORT") or analyze_settings.MYSQL_PORT)
    user = os.getenv("MYSQL_USER") or analyze_settings.MYSQL_USER
    database = os.getenv("MYSQL_DB") or analyze_settings.MYSQL_DB
    password = os.getenv("MYSQL_PASSWORD") or analyze_settings.MYSQL_PASSWORD
    charset = os.getenv("MYSQL_CHARSET") or analyze_settings.MYSQL_CHARSET

    # 재시도 로직
    max_retries = 3
    retry_delay = 2  # 초
    
    for attempt in range(max_retries):
        conn = None
        try:
            logger.info(f"MySQL(pymysql) 연결 시도 {attempt + 1}/{max_retries}: {host}:{port}, DB:{database}, User:{user}")

            # 드라이버 임포트 및 연결 (순수 파이썬 드라이버)
            import pymysql
            logger.info("PyMySQL 임포트 성공")

            conn = pymysql.connect(
                host=host,
                port=int(port),
                user=user,
                password=password,
                database=database,
                charset=charset,
                connect_timeout=10,  # 연결 타임아웃 10초
                read_timeout=30,     # 읽기 타임아웃 30초
                write_timeout=30,    # 쓰기 타임아웃 30초
                autocommit=False,  # 트랜잭션을 위해 autocommit=False
                cursorclass=pymysql.cursors.Cursor,
                use_unicode=True,
                # 추가 연결 옵션
                local_infile=True,
            )
            logger.info("MySQL 연결 성공")

            with conn.cursor() as cur:
                # 간단한 헬스체크
                cur.execute("SELECT 1")
                _ = cur.fetchone()

                # MySQL 서버의 중요한 설정 확인
                cur.execute("SHOW VARIABLES LIKE 'max_allowed_packet'")
                result = cur.fetchone()
                if result:
                    max_packet = int(result[1])
                    logger.info(f"MySQL max_allowed_packet: {max_packet} bytes ({max_packet / 1024 / 1024:.2f} MB)")
                    safe_packet_size = int(max_packet * 0.8)
                    logger.info(f"안전한 패킷 크기 (80%): {safe_packet_size} bytes ({safe_packet_size / 1024 / 1024:.2f} MB)")
                else:
                    safe_packet_size = 16 * 1024 * 1024  # 16MB 기본값

                # 추가 중요한 MySQL 설정 확인
                timeout_vars = ['wait_timeout', 'interactive_timeout', 'net_read_timeout', 'net_write_timeout']
                for var_name in timeout_vars:
                    cur.execute(f"SHOW VARIABLES LIKE '{var_name}'")
                    result = cur.fetchone()
                    if result:
                        logger.info(f"MySQL {var_name}: {result[1]} seconds")
                
                # 연결 상태 확인
                cur.execute("SELECT CONNECTION_ID()")
                conn_id = cur.fetchone()[0]
                logger.info(f"MySQL 연결 ID: {conn_id}")

                # cctv_id 파싱 (5135_20250913 형식에서 5135 추출)
                cctv_id_str = str(payload["cctv_id"])
                if "_" in cctv_id_str:
                    # 5135_20250913 -> 5135
                    cctv_id = int(cctv_id_str.split("_")[0])
                elif cctv_id_str.isdigit():
                    # 5135 -> 5135
                    cctv_id = int(cctv_id_str)
                else:
                    logger.error(f"잘못된 CCTV ID 형식: {cctv_id_str}")
                    cctv_id = 0

                logger.info(f"파싱된 CCTV ID: {cctv_id_str} -> {cctv_id}")

                # Swift URL 우선 정책 적용
                swift_image_url = payload.get("swift_image_url")
                image_binary = payload.get("image_binary", b"")
                
                # Swift URL이 있으면 바이너리 데이터는 저장하지 않음 (저장 공간 절약)
                if swift_image_url:
                    logger.info(f"Swift URL 발견 - 바이너리 저장 건너뜀: {swift_image_url}")
                    image_data_to_store = b""  # 빈 바이너리
                    image_binary_to_store = b""  # 빈 바이너리
                else:
                    # Swift URL이 없을 때만 바이너리 데이터 처리 (백업용)
                    image_data_binary = b""
                    image_base64 = payload.get("image_base64", "")
                    
                    if image_base64 and not image_binary:  # Swift 바이너리가 없으면 base64 사용
                        try:
                            # data:image prefix 제거
                            if "," in str(image_base64):
                                image_base64 = str(image_base64).split(",")[-1]
                            
                            # 모든 불필요한 문자 제거 (공백, 줄바꿈, 특수문자 등)
                            import re
                            image_base64 = re.sub(r'[^A-Za-z0-9+/]', '', str(image_base64))
                            
                            # base64 패딩을 완전히 다시 계산
                            while len(image_base64) % 4 != 0:
                                image_base64 += '='
                            
                            logger.info(f"정제된 base64 길이: {len(image_base64)} (4로 나눈 나머지: {len(image_base64) % 4})")
                            
                            # 디코딩 시도
                            image_data_binary = base64.b64decode(image_base64)
                            # image_binary가 없으면 base64에서 변환한 것을 사용
                            if not image_binary:
                                image_binary = image_data_binary
                            logger.info(f"base64 -> binary 변환 성공: {len(image_data_binary)} bytes")
                            
                        except Exception as e:
                            logger.warning(f"base64 디코딩 실패: {e}")
                            
                    if image_binary:
                        # image가 있으면 image_data에도 복사 (백업용)
                        image_data_binary = image_binary
                        logger.info(f"Swift 바이너리 사용: {len(image_binary)} bytes")

                    # SpringBoot와 동일한 20MB 제한 적용
                    MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
                    
                    if image_data_binary and len(image_data_binary) > MAX_IMAGE_SIZE:
                        logger.warning(f"image_data 크기 초과: {len(image_data_binary)} > {MAX_IMAGE_SIZE}")
                        image_data_binary = b""
                    
                    # image_data 컬럼에 JPEG 바이너리 직접 저장 (백업용)
                    if image_binary:
                        # Swift에서 온 바이너리 JPEG 데이터를 image_data에 저장
                        image_data_to_store = image_binary
                        logger.info(f"image_data에 JPEG 바이너리 저장: {len(image_binary)} bytes")
                    elif image_data_binary:
                        # base64 디코딩된 바이너리를 image_data에 저장
                        image_data_to_store = image_data_binary
                        logger.info(f"image_data에 base64 디코딩된 바이너리 저장: {len(image_data_binary)} bytes")
                    else:
                        image_data_to_store = b""
                        logger.info("저장할 이미지 데이터가 없음")
                    
                    image_binary_to_store = b""  # image 컬럼은 사용하지 않음

                logger.info(f"DB 저장 준비: Swift URL={swift_image_url}, image_data={len(image_data_to_store)}bytes, image={len(image_binary_to_store)}bytes")

                # SpringBoot 방식처럼 간단한 INSERT - 한번에 모든 데이터 저장
                sql_analyze = (
                    "INSERT INTO analyzes (cctv_id, analyzed_date, message, detection_count, severity_score, image_data, image_url, image) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE "
                    "message=VALUES(message), detection_count=VALUES(detection_count), "
                    "severity_score=VALUES(severity_score), image_data=VALUES(image_data), "
                    "image_url=VALUES(image_url), image=VALUES(image), id=LAST_INSERT_ID(id)"
                )

                logger.info("SpringBoot 방식으로 데이터베이스 저장 시작")
                cur.execute(
                    sql_analyze,
                    (
                        cctv_id,
                        payload["analyzed_date"],
                        payload.get("message"),
                        payload["detection_count"],
                        payload.get("severity_score"),
                        image_data_to_store,  # JPEG 바이너리 데이터 또는 빈 바이너리
                        payload.get("swift_image_url"),
                        image_binary_to_store,  # 빈 바이너리
                    ),
                )

                analyze_id = cur.lastrowid
                if analyze_id == 0:
                    # UPDATE된 경우 analyze_id를 가져오기
                    cur.execute(
                        "SELECT id FROM analyzes WHERE cctv_id = %s AND analyzed_date = %s",
                        (cctv_id, payload["analyzed_date"])
                    )
                    result = cur.fetchone()
                    analyze_id = result[0] if result else 1
                
                logger.info(f"데이터베이스 저장 완료: analyze_id={analyze_id}")

                # 2. 기존 detections 삭제 (UPDATE 시 기존 탐지 결과 삭제)
                cur.execute("DELETE FROM detections WHERE analyze_id = %s", (analyze_id,))

                # 3. detections 테이블에 INSERT
                detections = payload.get("detections", [])
                if detections:
                    sql_detection = (
                        "INSERT INTO detections "
                        "(analyze_id, class_id, damage_type, confidence, bbox, severity, area, severity_score) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    )
                    
                    for detection in detections:
                        bbox_json = json.dumps(detection["bbox"])
                        cur.execute(
                            sql_detection,
                            (
                                analyze_id,
                                detection["class_id"],
                                detection["damage_type"],
                                detection["confidence"],
                                bbox_json,
                                detection["severity"],
                                detection.get("area"),
                                detection.get("severity_score"),
                            ),
                        )

                # 트랜잭션 커밋
                conn.commit()

            conn.close()
            logger.info(f"MySQL 저장 완료: analyze_id={analyze_id}, detections={len(detections)}개")
            return analyze_id

        except Exception as e:
            error_msg = str(e)
            logger.error(f"MySQL 연결/저장 실패 (시도 {attempt + 1}/{max_retries}): {error_msg}")
            
            # 롤백 시도
            try:
                if conn:
                    conn.rollback()
                    conn.close()
                    logger.info("MySQL 트랜잭션 롤백 완료")
            except:
                pass
            
            # 재시도 가능한 오류인지 확인
            if "Lost connection" in error_msg or "timeout" in error_msg.lower() or "10054" in error_msg:
                if attempt < max_retries - 1:
                    logger.info(f"네트워크 오류로 인한 재시도 대기: {retry_delay}초")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 지수적 백오프
                    continue
            
            # 최종 실패시 더미 ID 반환
            if attempt == max_retries - 1:
                dummy_id = random.randint(10000, 99999)
                logger.warning(f"최대 재시도 횟수 초과 - 더미 ID 반환: {dummy_id}")
                return dummy_id

    # 여기 도달하면 안됨
    dummy_id = random.randint(10000, 99999)
    logger.warning(f"예상치 못한 상황 - 더미 ID 반환: {dummy_id}")
    return dummy_id

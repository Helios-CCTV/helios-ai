import requests
import json
import os
import sys
from urllib.parse import urlencode
from dotenv import load_dotenv
import mysql.connector
from shapely.geometry import Point, Polygon
from shapely import wkt
import logging
from typing import List, Dict, Any, Optional

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CCTVToDatabase:
    def __init__(self):
        """CCTV API 클라이언트 및 데이터베이스 연결 초기화"""
        load_dotenv()
        
        # API 설정
        self.api_key = os.getenv('ITS_API_KEY')
        self.api_url = "https://openapi.its.go.kr:9443/cctvInfo"
        
        # 데이터베이스 연결 설정 - 환경변수에서 직접 로드
        self.db_config = {
            'host': os.getenv('DB_HOST'),
            'database': os.getenv('DB_NAME'), 
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'port': int(os.getenv('DB_PORT', '3306')),
            'charset': 'utf8mb4',
            'autocommit': True,
            'use_unicode': True,
            'ssl_verify_cert': False,
            'ssl_verify_identity': False
        }
        
        self.connection = None
        
    def connect_to_database(self) -> bool:
        """데이터베이스 연결"""
        try:
            self.connection = mysql.connector.connect(**self.db_config)
            logger.info("데이터베이스 연결 성공")
            return True
        except Exception as e:
            logger.error(f"데이터베이스 연결 실패: {e}")
            return False
    
    def close_database_connection(self):
        """데이터베이스 연결 종료"""
        if self.connection:
            self.connection.close()
            logger.info("데이터베이스 연결이 종료되었습니다.")
    
    def fetch_cctv_data(self, min_x: float = 126.8, max_x: float = 127.2, 
                       min_y: float = 37.4, max_y: float = 37.7) -> Optional[Dict[str, Any]]:
        """
        CCTV API에서 데이터 조회
        
        Args:
            min_x: 최소 경도
            max_x: 최대 경도
            min_y: 최소 위도
            max_y: 최대 위도
            
        Returns:
            API 응답 데이터 (JSON)
        """
        try:
            # URL 파라미터 구성
            params = {
                'apiKey': self.api_key,
                'type': 'all',
                'cctvType': '2',
                'minX': str(min_x),
                'maxX': str(max_x),
                'minY': str(min_y),
                'maxY': str(max_y),
                'getType': 'json'
            }
            
            # API 요청
            response = requests.get(self.api_url, params=params, timeout=30)
            
            logger.info(f"API 응답 코드: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"CCTV 데이터 조회 성공: {len(data.get('response', {}).get('data', []))}개")
                return data
            else:
                logger.error(f"API 요청 실패: {response.status_code}")
                logger.error(f"응답 내용: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"CCTV 데이터 조회 중 오류 발생: {e}")
            return None
    
    def get_polygon_data(self) -> List[Dict[str, Any]]:
        """
        데이터베이스에서 폴리곤 데이터 조회
        
        Returns:
            폴리곤 데이터 리스트
        """
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # regions 테이블에서 폴리곤 데이터 조회 (실제 테이블 구조에 맞게 수정)
            query = """
                SELECT id, sgg_nm as name, ST_AsText(polygon) as polygon_wkt
                FROM regions
                WHERE ST_IsValid(polygon) = 1
            """
            
            cursor.execute(query)
            polygons = cursor.fetchall()
            cursor.close()
            
            logger.info(f"폴리곤 데이터 조회 완료: {len(polygons)}개")
            return polygons
            
        except Exception as e:
            logger.error(f"폴리곤 데이터 조회 중 오류 발생: {e}")
            return []
    
    def find_polygon_for_point(self, longitude: float, latitude: float, 
                             polygons: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        주어진 좌표가 포함되는 폴리곤 찾기
        
        Args:
            longitude: 경도
            latitude: 위도
            polygons: 폴리곤 데이터 리스트
            
        Returns:
            해당하는 폴리곤 정보
        """
        try:
            point = Point(longitude, latitude)
            
            for polygon_data in polygons:
                polygon_wkt = polygon_data['polygon_wkt']
                polygon = wkt.loads(polygon_wkt)
                
                if polygon.contains(point):
                    return polygon_data
                    
            return None
            
        except Exception as e:
            logger.error(f"폴리곤 매칭 중 오류 발생: {e}")
            return None
    
    def save_cctv_to_database(self, cctv_data: Dict[str, Any], polygon_info: Optional[Dict[str, Any]]):
        """
        CCTV 데이터를 데이터베이스에 저장
        
        Args:
            cctv_data: CCTV 정보
            polygon_info: 해당하는 폴리곤 정보
        """
        try:
            cursor = self.connection.cursor()
            
            longitude = float(cctv_data.get('coordx', 0))
            latitude = float(cctv_data.get('coordy', 0))
            
            # CCTV 데이터 저장 쿼리 (MySQL 문법으로 수정)
            insert_query = """
                INSERT INTO cctvs 
                (location, latitude, longitude, point, region_id, created_at, updated_at)
                VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                    location = VALUES(location),
                    latitude = VALUES(latitude),
                    longitude = VALUES(longitude),
                    point = VALUES(point),
                    region_id = VALUES(region_id),
                    updated_at = NOW()
            """
            
            region_id = polygon_info['id'] if polygon_info else None
            point_wkt = f"POINT({longitude} {latitude})"
            
            cursor.execute(insert_query, (
                cctv_data.get('cctvname'),
                latitude,
                longitude,
                point_wkt,
                region_id
            ))
            
            cursor.close()
            
        except Exception as e:
            logger.error(f"CCTV 데이터 저장 중 오류 발생: {e}")
            raise
    
    def process_cctv_data(self, min_x: float = 126.8, max_x: float = 127.2, 
                         min_y: float = 37.4, max_y: float = 37.7):
        """
        CCTV 데이터 처리 메인 함수
        
        Args:
            min_x: 최소 경도
            max_x: 최대 경도
            min_y: 최소 위도
            max_y: 최대 위도
        """
        try:
            # 데이터베이스 연결
            if not self.connect_to_database():
                return False
            
            # CCTV 데이터 조회
            logger.info("CCTV 데이터 조회 시작...")
            cctv_response = self.fetch_cctv_data(min_x, max_x, min_y, max_y)
            
            if not cctv_response:
                logger.error("CCTV 데이터 조회 실패")
                return False
            
            # 폴리곤 데이터 조회
            logger.info("폴리곤 데이터 조회 시작...")
            polygons = self.get_polygon_data()
            
            if not polygons:
                logger.warning("폴리곤 데이터가 없습니다. CCTV 데이터만 저장합니다.")
            
            # CCTV 데이터 처리
            cctv_list = cctv_response.get('response', {}).get('data', [])
            success_count = 0
            error_count = 0
            
            logger.info(f"총 {len(cctv_list)}개의 CCTV 데이터 처리 시작...")
            
            for cctv in cctv_list:
                try:
                    longitude = float(cctv.get('coordx', 0))
                    latitude = float(cctv.get('coordy', 0))
                    
                    # 좌표가 유효한지 확인
                    if longitude == 0 or latitude == 0:
                        logger.warning(f"유효하지 않은 좌표: CCTV ID {cctv.get('cctvid')}")
                        continue
                    
                    # 해당하는 폴리곤 찾기
                    polygon_info = None
                    if polygons:
                        polygon_info = self.find_polygon_for_point(longitude, latitude, polygons)
                    
                    # 데이터베이스에 저장
                    self.save_cctv_to_database(cctv, polygon_info)
                    success_count += 1
                    
                    if success_count % 100 == 0:
                        logger.info(f"처리 진행률: {success_count}/{len(cctv_list)}")
                        self.connection.commit()  # 중간 커밋
                    
                except Exception as e:
                    logger.error(f"CCTV 데이터 처리 중 오류: {cctv.get('cctvid', 'Unknown')} - {e}")
                    error_count += 1
            
            # 최종 커밋
            self.connection.commit()
            
            logger.info(f"CCTV 데이터 처리 완료: 성공 {success_count}개, 오류 {error_count}개")
            return True
            
        except Exception as e:
            logger.error(f"데이터 처리 중 오류 발생: {e}")
            if self.connection:
                self.connection.rollback()
            return False
        
        finally:
            self.close_database_connection()



def main():
    """메인 실행 함수"""
    print("=== CCTV 데이터 수집 및 DB 저장 프로그램 ===")
    
    # 명령행 인수 처리
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("사용법:")
            print("  python cctv_to_db.py             # CCTV 데이터 수집 및 저장")
            print("  python cctv_to_db.py --api-only  # API 데이터만 조회 (DB 저장 안함)")
            print("  python cctv_to_db.py --help      # 도움말")
            return
        elif sys.argv[1] == "--api-only":
            # API 데이터만 조회하고 출력
            processor = CCTVToDatabase()
            min_x = 125.86370427196482
            max_x = 128.30432205756796
            min_y = 36.84606018570888
            max_y = 37.90300313505868
            
            print(f"좌표 범위: 경도 {min_x}~{max_x}, 위도 {min_y}~{max_y}")
            print("API 데이터만 조회 (데이터베이스 저장하지 않음)")
            
            cctv_response = processor.fetch_cctv_data(min_x, max_x, min_y, max_y)
            if cctv_response:
                cctv_list = cctv_response.get('response', {}).get('data', [])
                print(f"조회된 CCTV 데이터: {len(cctv_list)}개")
                # 처음 5개 샘플 출력
                for i, cctv in enumerate(cctv_list[:5]):
                    print(f"  {i+1}. {cctv.get('cctvname', 'Unknown')} - 위도: {cctv.get('coordy')}, 경도: {cctv.get('coordx')}")
                if len(cctv_list) > 5:
                    print(f"  ... 외 {len(cctv_list)-5}개")
            else:
                print("CCTV 데이터 조회 실패")
            return
    
    # CCTV 데이터 처리 시작
    processor = CCTVToDatabase()
    
    # 좌표 범위 설정 (한국 전체 지역)
    min_x = 125.86370427196482  # 최소 경도
    max_x = 128.30432205756796  # 최대 경도  
    min_y = 36.84606018570888   # 최소 위도
    max_y = 37.90300313505868   # 최대 위도
    
    print(f"좌표 범위: 경도 {min_x}~{max_x}, 위도 {min_y}~{max_y}")
    
    success = processor.process_cctv_data(min_x, max_x, min_y, max_y)
    
    if success:
        print("CCTV 데이터 처리가 성공적으로 완료되었습니다.")
    else:
        print("CCTV 데이터 처리 중 오류가 발생했습니다.")
        sys.exit(1)

if __name__ == "__main__":
    main()

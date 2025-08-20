from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional

router = APIRouter(prefix="/items", tags=["items"])

# 임시 아이템 데이터
fake_items_db = {
    "item1": {"name": "CCTV-001", "location": "서울특별시 강남구", "latitude": 37.5172, "longitude": 127.0473},
    "item2": {"name": "CCTV-002", "location": "서울특별시 송파구", "latitude": 37.5145, "longitude": 127.1060},
    "item3": {"name": "CCTV-003", "location": "서울특별시 강동구", "latitude": 37.5384, "longitude": 127.1368}
}

@router.get("/", summary="모든 CCTV 목록 조회")
async def get_items(skip: int = 0, limit: int = 10):
    items = list(fake_items_db.values())
    return items[skip : skip + limit]

@router.get("/search", summary="CCTV 검색")
async def search_items(location: Optional[str] = None, min_lat: Optional[float] = None, 
                      max_lat: Optional[float] = None, min_lng: Optional[float] = None, 
                      max_lng: Optional[float] = None):
    results = []
    
    for item in fake_items_db.values():
        if location and location.lower() not in item["location"].lower():
            continue
            
        lat, lng = item["latitude"], item["longitude"]
        
        if min_lat and lat < min_lat:
            continue
        if max_lat and lat > max_lat:
            continue
        if min_lng and lng < min_lng:
            continue
        if max_lng and lng > max_lng:
            continue
            
        results.append(item)
        
    return results

@router.get("/{item_id}", summary="특정 CCTV 정보 조회")
async def get_item(item_id: str):
    if item_id not in fake_items_db:
        raise HTTPException(status_code=404, detail="CCTV를 찾을 수 없습니다")
    return fake_items_db[item_id]

@router.post("/", summary="새 CCTV 등록", status_code=201)
async def create_item(name: str, location: str, latitude: float, longitude: float):
    item_id = f"item{len(fake_items_db) + 1}"
    fake_items_db[item_id] = {
        "name": name,
        "location": location,
        "latitude": latitude,
        "longitude": longitude
    }
    return {"item_id": item_id, **fake_items_db[item_id]}

@router.put("/{item_id}", summary="CCTV 정보 업데이트")
async def update_item(item_id: str, name: str = None, location: str = None, 
                     latitude: float = None, longitude: float = None):
    if item_id not in fake_items_db:
        raise HTTPException(status_code=404, detail="CCTV를 찾을 수 없습니다")
    
    item = fake_items_db[item_id]
    if name:
        item["name"] = name
    if location:
        item["location"] = location
    if latitude:
        item["latitude"] = latitude
    if longitude:
        item["longitude"] = longitude
    
    return item

@router.delete("/{item_id}", summary="CCTV 삭제", status_code=204)
async def delete_item(item_id: str):
    if item_id not in fake_items_db:
        raise HTTPException(status_code=404, detail="CCTV를 찾을 수 없습니다")
    
    del fake_items_db[item_id]
    return None

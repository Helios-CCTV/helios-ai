from fastapi import APIRouter, HTTPException, Depends
from typing import List

router = APIRouter(prefix="/users", tags=["users"])

# 임시 사용자 데이터
fake_users_db = {
    "user1": {"username": "johndoe", "email": "john@example.com", "full_name": "John Doe", "disabled": False},
    "user2": {"username": "alice", "email": "alice@example.com", "full_name": "Alice Smith", "disabled": True}
}

@router.get("/", summary="모든 사용자 목록 조회")
async def get_users():
    return list(fake_users_db.values())

@router.get("/{user_id}", summary="특정 사용자 정보 조회")
async def get_user(user_id: str):
    if user_id not in fake_users_db:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return fake_users_db[user_id]

@router.post("/", summary="새 사용자 생성", status_code=201)
async def create_user(username: str, email: str, full_name: str = None):
    user_id = f"user{len(fake_users_db) + 1}"
    fake_users_db[user_id] = {"username": username, "email": email, "full_name": full_name, "disabled": False}
    return {"user_id": user_id, **fake_users_db[user_id]}

@router.put("/{user_id}", summary="사용자 정보 업데이트")
async def update_user(user_id: str, username: str = None, email: str = None, full_name: str = None):
    if user_id not in fake_users_db:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    user = fake_users_db[user_id]
    if username:
        user["username"] = username
    if email:
        user["email"] = email
    if full_name:
        user["full_name"] = full_name
    
    return user

@router.delete("/{user_id}", summary="사용자 삭제", status_code=204)
async def delete_user(user_id: str):
    if user_id not in fake_users_db:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    del fake_users_db[user_id]
    return None

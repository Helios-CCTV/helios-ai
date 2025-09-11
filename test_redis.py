import redis
import json
import uuid

# Redis 연결
r = redis.Redis(host='61.252.59.26', port=6379, password='tlgmdaoghkrhemdgkrry', decode_responses=True)

try:
    # 스트림 상태 확인
    try:
        info = r.xinfo_stream('stream:preprocess')
        print(f'Stream length: {info["length"]}')
        
        # 최근 메시지 확인
        messages = r.xrange('stream:preprocess', count=5)
        print(f'Recent messages: {len(messages)}')
        for msg_id, fields in messages[-3:]:  # 최근 3개만
            print(f'  {msg_id}: {fields}')
            
    except redis.ResponseError:
        print('Stream not found, will create test message')
        
    # 테스트 메시지 추가
    test_data = {
        'task_id': str(uuid.uuid4()),
        'hls_url': 'http://example.com/test.m3u8', 
        'metadata': json.dumps({'test': True, 'source': 'manual_test'})
    }
    
    msg_id = r.xadd('stream:preprocess', test_data)
    print(f'Added test message: {msg_id}')
    
except Exception as e:
    print(f'Error: {e}')

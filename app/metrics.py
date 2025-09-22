"""
메트릭 관리 (처리/실패/대기 카운터)
"""
import threading
from datetime import datetime
from typing import Dict, Any


class Metrics:
    """간단한 in-memory 메트릭 관리"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._counters = {
            "processed": 0,
            "failed": 0,
            "retried": 0,
            "dlq": 0,
            "pending": 0,
            "concurrency_current": 0
        }
        self._start_time = datetime.now()
    
    def increment(self, counter: str, value: int = 1):
        """카운터 증가"""
        with self._lock:
            if counter in self._counters:
                self._counters[counter] += value
    
    def decrement(self, counter: str, value: int = 1):
        """카운터 감소"""
        with self._lock:
            if counter in self._counters:
                self._counters[counter] = max(0, self._counters[counter] - value)
    
    def set(self, counter: str, value: int):
        """카운터 설정"""
        with self._lock:
            if counter in self._counters:
                self._counters[counter] = value
    
    def get_all(self) -> Dict[str, Any]:
        """모든 메트릭 반환"""
        with self._lock:
            uptime = (datetime.now() - self._start_time).total_seconds()
            return {
                "counters": self._counters.copy(),
                "uptime_seconds": uptime,
                "start_time": self._start_time.isoformat()
            }
    
    def reset(self):
        """모든 카운터 리셋"""
        with self._lock:
            for key in self._counters:
                if key != "concurrency_current":  # 현재 동시성은 유지
                    self._counters[key] = 0
            self._start_time = datetime.now()


# 글로벌 메트릭 인스턴스
metrics = Metrics()

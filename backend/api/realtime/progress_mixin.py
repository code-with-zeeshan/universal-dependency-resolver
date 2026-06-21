"""Progress reporting mixin for core modules"""
from typing import Callable, Optional, Dict, Any
import asyncio
from datetime import datetime
import uuid

class ProgressReporter:
    """Mixin for adding progress reporting to core modules"""
    
    def __init__(self):
        self._progress_callback: Optional[Callable] = None
        self._operation_id: Optional[str] = None
        self._progress_data = {
            'current_step': '',
            'progress': 0,
            'total_steps': 0,
            'details': {},
            'started_at': None,
            'estimated_completion': None
        }
    
    def set_progress_callback(self, callback: Callable, operation_id: str = None):
        """Set callback for progress updates"""
        self._progress_callback = callback
        self._operation_id = operation_id or str(uuid.uuid4())
        self._progress_data['started_at'] = datetime.utcnow().isoformat()
        return self._operation_id
    
    async def report_progress(
        self, 
        step: str, 
        progress: int, 
        total_steps: int = 100,
        details: Dict[str, Any] = None,
        estimated_completion: datetime = None
    ):
        """Report progress update"""
        self._progress_data.update({
            'current_step': step,
            'progress': min(progress, 100),
            'total_steps': total_steps,
            'details': details or {},
            'estimated_completion': estimated_completion.isoformat() if estimated_completion else None,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        if self._progress_callback and self._operation_id:
            try:
                await self._progress_callback(
                    self._operation_id,
                    {
                        'type': 'progress',
                        'operation_id': self._operation_id,
                        **self._progress_data
                    }
                )
            except Exception as e:
                print(f"Failed to report progress: {e}")
    
    async def report_completion(self, result: Any = None, details: Dict[str, Any] = None):
        """Report operation completion"""
        if self._progress_callback and self._operation_id:
            await self._progress_callback(
                self._operation_id,
                {
                    'type': 'complete',
                    'operation_id': self._operation_id,
                    'result': result,
                    'details': details or {},
                    'completed_at': datetime.utcnow().isoformat()
                }
            )
    
    async def report_error(self, error: str, details: Dict[str, Any] = None):
        """Report operation error"""
        if self._progress_callback and self._operation_id:
            await self._progress_callback(
                self._operation_id,
                {
                    'type': 'error',
                    'operation_id': self._operation_id,
                    'error': error,
                    'details': details or {},
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
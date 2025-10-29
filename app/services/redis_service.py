# app/services/redis_service.py - Redis Service (Minimal Hot Data Only)
import redis
import json
import logging
from typing import Dict, Optional, List
from datetime import timedelta, datetime

from config import Config

logger = logging.getLogger(__name__)

class RedisService:
    """Redis service for HOT DATA ONLY - active session state and locks"""

    def __init__(self):
        self.client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            password=Config.REDIS_PASSWORD,
            db=Config.REDIS_DB,
            decode_responses=True
        )
        logger.info("Redis service initialized (minimal hot data mode)")
    
    def test_connection(self) -> bool:
        """Test Redis connection"""
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Redis connection failed: {str(e)}")
            return False

    # ===== SESSION STATE MANAGEMENT (HOT DATA) =====

    def store_session_state(self, session_id: str, state: Dict) -> bool:
        """
        Store minimal active session state (hot data only)
        State includes: student_id, current_proficiency, next_question_id, status, questions_answered
        """
        try:
            state['last_activity'] = datetime.now().isoformat()

            self.client.setex(
                f"session:{session_id}:state",
                timedelta(minutes=30),  # 30-minute inactivity timeout
                json.dumps(state, default=str)
            )
            logger.debug(f"Stored session state for {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error storing session state: {str(e)}")
            return False

    def get_session_state(self, session_id: str) -> Optional[Dict]:
        """Get active session state from Redis"""
        try:
            data = self.client.get(f"session:{session_id}:state")
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error getting session state: {str(e)}")
            return None

    def update_session_proficiency(self, session_id: str, proficiency: List[float],
                                   questions_answered: int) -> bool:
        """Update only proficiency and question count (fast partial update)"""
        try:
            state = self.get_session_state(session_id)
            if not state:
                return False

            state['current_proficiency'] = proficiency
            state['questions_answered'] = questions_answered
            state['last_activity'] = datetime.now().isoformat()

            return self.store_session_state(session_id, state)
        except Exception as e:
            logger.error(f"Error updating proficiency: {str(e)}")
            return False

    def delete_session_state(self, session_id: str) -> bool:
        """Delete session state from Redis"""
        try:
            return bool(self.client.delete(f"session:{session_id}:state"))
        except Exception as e:
            logger.error(f"Error deleting session state: {str(e)}")
            return False

    # ===== SUBMISSION LOCKS (PREVENT DOUBLE SUBMIT) =====

    def acquire_submission_lock(self, session_id: str, question_id: str,
                               timeout_seconds: int = 5) -> bool:
        """
        Acquire a lock to prevent duplicate submissions
        Returns True if lock acquired, False if already locked
        """
        try:
            lock_key = f"lock:{session_id}:{question_id}"
            # SET NX (set if not exists) with expiry
            result = self.client.set(lock_key, "1", nx=True, ex=timeout_seconds)
            return bool(result)
        except Exception as e:
            logger.error(f"Error acquiring lock: {str(e)}")
            return False

    def release_submission_lock(self, session_id: str, question_id: str) -> bool:
        """Release submission lock"""
        try:
            lock_key = f"lock:{session_id}:{question_id}"
            return bool(self.client.delete(lock_key))
        except Exception as e:
            logger.error(f"Error releasing lock: {str(e)}")
            return False

    # ===== QUESTION POOL CACHING (TIER 1 - HOT CACHE) =====

    def cache_question_pool(self, pool_id: str, pool_data: Dict,
                           ttl_hours: int = 24) -> bool:
        """
        Cache entire question pool in Redis (Tier 1)
        TTL: 24 hours by default
        """
        try:
            # Add cache metadata
            pool_data['cached_at'] = datetime.now().isoformat()
            pool_data['cache_tier'] = 'redis'

            self.client.setex(
                f"pool:{pool_id}",
                timedelta(hours=ttl_hours),
                json.dumps(pool_data, default=str)
            )
            logger.info(f"Cached question pool {pool_id} in Redis (TTL: {ttl_hours}h)")
            return True
        except Exception as e:
            logger.error(f"Error caching question pool: {str(e)}")
            return False

    def get_cached_question_pool(self, pool_id: str) -> Optional[Dict]:
        """Get cached question pool from Redis (Tier 1)"""
        try:
            data = self.client.get(f"pool:{pool_id}")
            if data:
                logger.info(f"Cache HIT (Redis): pool {pool_id}")
                return json.loads(data)

            logger.info(f"Cache MISS (Redis): pool {pool_id}")
            return None
        except Exception as e:
            logger.error(f"Error getting cached pool: {str(e)}")
            return None

    def invalidate_question_pool(self, pool_id: str) -> bool:
        """Invalidate/delete question pool from Redis cache"""
        try:
            deleted = self.client.delete(f"pool:{pool_id}")
            if deleted:
                logger.info(f"Invalidated question pool {pool_id} from Redis")
            return bool(deleted)
        except Exception as e:
            logger.error(f"Error invalidating pool: {str(e)}")
            return False

    # ===== INDIVIDUAL QUESTION CACHING (OPTIONAL) =====

    def cache_question(self, question_id: str, question_data: Dict,
                      ttl_hours: int = 1) -> bool:
        """Cache a frequently accessed question (without correct answer for security)"""
        try:
            # Remove correct_answer before caching
            safe_question = {k: v for k, v in question_data.items()
                           if k != 'correct_answer'}

            self.client.setex(
                f"question:{question_id}",
                timedelta(hours=ttl_hours),
                json.dumps(safe_question, default=str)
            )
            return True
        except Exception as e:
            logger.error(f"Error caching question: {str(e)}")
            return False

    def get_cached_question(self, question_id: str) -> Optional[Dict]:
        """Get cached question (returns None if not cached)"""
        try:
            data = self.client.get(f"question:{question_id}")
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error getting cached question: {str(e)}")
            return None

    # ===== CLEANUP & MONITORING =====

    def get_all_session_keys(self) -> List[str]:
        """Get all session state keys"""
        try:
            return [key.replace('session:', '').replace(':state', '')
                    for key in self.client.keys('session:*:state')]
        except Exception as e:
            logger.error(f"Error getting all sessions: {str(e)}")
            return []

    def cleanup_inactive_sessions(self, inactivity_minutes: int = 30) -> int:
        """Remove sessions inactive for more than specified minutes"""
        try:
            cleanup_count = 0
            current_time = datetime.now()
            inactivity_threshold = timedelta(minutes=inactivity_minutes)

            # Get all session state keys
            session_keys = self.client.keys('session:*:state')

            for key in session_keys:
                try:
                    data = self.client.get(key)
                    if data:
                        session_data = json.loads(data)
                        last_activity_str = session_data.get('last_activity')

                        if last_activity_str:
                            last_activity = datetime.fromisoformat(last_activity_str)
                            time_since_activity = current_time - last_activity

                            if time_since_activity > inactivity_threshold:
                                self.client.delete(key)
                                cleanup_count += 1
                                logger.info(f"Cleaned up inactive session: {key}")
                except Exception as e:
                    logger.error(f"Error processing session {key}: {str(e)}")
                    continue

            logger.info(f"Cleaned up {cleanup_count} inactive sessions")
            return cleanup_count

        except Exception as e:
            logger.error(f"Error during session cleanup: {str(e)}")
            return 0

    def get_stats(self) -> Dict:
        """Get Redis statistics for monitoring"""
        try:
            session_count = len(self.client.keys('session:*:state'))
            lock_count = len(self.client.keys('lock:*'))
            question_cache_count = len(self.client.keys('question:*'))

            info = self.client.info('memory')

            return {
                'active_sessions': session_count,
                'active_locks': lock_count,
                'cached_questions': question_cache_count,
                'memory_used_mb': round(info.get('used_memory', 0) / (1024 * 1024), 2),
                'total_keys': self.client.dbsize()
            }
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {}

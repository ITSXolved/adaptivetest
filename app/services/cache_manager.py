# app/services/cache_manager.py - 3-Tier Cache Manager
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class CacheManager:
    """
    3-Tier Cache Manager for Question Pools

    Tier 1: Redis (Fast, ~1ms latency, 24-hour TTL)
    Tier 2: Supabase (Medium, ~50ms latency, 7-day TTL)
    Tier 3: External API (Slow, ~500ms latency, source of truth)

    Cache Strategy:
    - READ: Try Tier 1 → Tier 2 → Tier 3 (waterfall)
    - WRITE: Write to all tiers on cache miss
    - INVALIDATE: Clear all tiers
    """

    def __init__(self, redis_service, supabase_service, external_api_service):
        self.redis = redis_service
        self.supabase = supabase_service
        self.external_api = external_api_service

        # Cache statistics
        self.stats = {
            'redis_hits': 0,
            'redis_misses': 0,
            'supabase_hits': 0,
            'supabase_misses': 0,
            'external_api_calls': 0,
            'total_requests': 0
        }

        logger.info("3-Tier Cache Manager initialized")

    def get_question_pool(self, level: str, level_id: str,
                         fetch_all_pages: bool = True) -> Optional[Dict]:
        """
        Get question pool with 3-tier caching strategy

        Args:
            level: 'topic', 'chapter', 'subject', 'class', or 'exam'
            level_id: UUID of the level
            fetch_all_pages: If True, fetch all pages from external API

        Returns:
            Question pool data or None if not found
        """
        self.stats['total_requests'] += 1
        pool_id = f"{level}_{level_id}"

        logger.info(f"🔍 Fetching question pool: {pool_id}")

        # === TIER 1: Try Redis (fastest) ===
        try:
            redis_data = self.redis.get_cached_question_pool(pool_id)
            if redis_data:
                self.stats['redis_hits'] += 1
                logger.info(f"✅ TIER 1 HIT (Redis): {pool_id} - Latency: ~1ms")
                return redis_data
            else:
                self.stats['redis_misses'] += 1
        except Exception as e:
            logger.warning(f"Redis error (continuing to Tier 2): {str(e)}")

        # === TIER 2: Try Supabase (medium) ===
        try:
            supabase_data = self.supabase.get_cached_question_pool(pool_id)
            if supabase_data:
                self.stats['supabase_hits'] += 1
                logger.info(f"✅ TIER 2 HIT (Supabase): {pool_id} - Latency: ~50ms")

                # Cache in Tier 1 (write-through)
                self._cache_to_redis(pool_id, supabase_data)

                return supabase_data
            else:
                self.stats['supabase_misses'] += 1
        except Exception as e:
            logger.warning(f"Supabase error (continuing to Tier 3): {str(e)}")

        # === TIER 3: Fetch from External API (slowest, source of truth) ===
        try:
            self.stats['external_api_calls'] += 1
            logger.info(f"⏳ TIER 3: Fetching from External API - Latency: ~500ms")

            if fetch_all_pages:
                raw_data = self.external_api.fetch_all_pages(level, level_id)
            else:
                raw_data = self.external_api.fetch_question_pool(level, level_id)

            if not raw_data:
                logger.error(f"❌ External API returned no data for {pool_id}")
                return None

            # Transform to internal format
            pool_data = self.external_api.transform_to_internal_format(raw_data)

            if pool_data:
                logger.info(f"✅ TIER 3: Fetched {pool_data['total_questions']} questions from External API")

                # Cache in all tiers (write-through)
                self._cache_to_all_tiers(pool_id, pool_data)

                return pool_data
            else:
                logger.error(f"❌ Failed to transform External API data for {pool_id}")
                return None

        except Exception as e:
            logger.error(f"External API error: {str(e)}")
            return None

    def invalidate_question_pool(self, level: str, level_id: str) -> bool:
        """
        Invalidate question pool from all cache tiers

        Use cases:
        - Question pool updated in external system
        - Manual cache refresh requested
        - Data corruption detected
        """
        pool_id = f"{level}_{level_id}"
        logger.info(f"🗑️  Invalidating question pool from all tiers: {pool_id}")

        success = True

        # Invalidate Tier 1 (Redis)
        try:
            self.redis.invalidate_question_pool(pool_id)
            logger.info(f"✅ Invalidated from Tier 1 (Redis)")
        except Exception as e:
            logger.error(f"Failed to invalidate from Redis: {str(e)}")
            success = False

        # Invalidate Tier 2 (Supabase)
        try:
            self.supabase.invalidate_question_pool(pool_id)
            logger.info(f"✅ Invalidated from Tier 2 (Supabase)")
        except Exception as e:
            logger.error(f"Failed to invalidate from Supabase: {str(e)}")
            success = False

        return success

    def refresh_question_pool(self, level: str, level_id: str) -> Optional[Dict]:
        """
        Force refresh question pool from External API and update all caches

        Use this when you know the data has changed
        """
        pool_id = f"{level}_{level_id}"
        logger.info(f"🔄 Force refreshing question pool: {pool_id}")

        # First, invalidate existing caches
        self.invalidate_question_pool(level, level_id)

        # Then fetch fresh data from External API
        return self.get_question_pool(level, level_id)

    def get_cache_stats(self) -> Dict:
        """Get cache performance statistics"""
        total = self.stats['total_requests']

        if total == 0:
            return {
                **self.stats,
                'redis_hit_rate': 0.0,
                'supabase_hit_rate': 0.0,
                'external_api_rate': 0.0
            }

        return {
            **self.stats,
            'redis_hit_rate': round(self.stats['redis_hits'] / total * 100, 2),
            'supabase_hit_rate': round(self.stats['supabase_hits'] / total * 100, 2),
            'external_api_rate': round(self.stats['external_api_calls'] / total * 100, 2),
            'overall_cache_hit_rate': round(
                (self.stats['redis_hits'] + self.stats['supabase_hits']) / total * 100, 2
            )
        }

    def reset_cache_stats(self):
        """Reset cache statistics"""
        self.stats = {
            'redis_hits': 0,
            'redis_misses': 0,
            'supabase_hits': 0,
            'supabase_misses': 0,
            'external_api_calls': 0,
            'total_requests': 0
        }
        logger.info("Cache statistics reset")

    # === PRIVATE HELPER METHODS ===

    def _cache_to_redis(self, pool_id: str, pool_data: Dict) -> bool:
        """Cache question pool to Redis (Tier 1)"""
        try:
            self.redis.cache_question_pool(pool_id, pool_data, ttl_hours=24)
            logger.debug(f"Cached to Redis: {pool_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cache to Redis: {str(e)}")
            return False

    def _cache_to_supabase(self, pool_id: str, pool_data: Dict) -> bool:
        """Cache question pool to Supabase (Tier 2)"""
        try:
            self.supabase.cache_question_pool(pool_id, pool_data)
            logger.debug(f"Cached to Supabase: {pool_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cache to Supabase: {str(e)}")
            return False

    def _cache_to_all_tiers(self, pool_id: str, pool_data: Dict) -> bool:
        """Cache question pool to all tiers (write-through)"""
        success = True

        # Cache to Tier 2 (Supabase) - more reliable, longer TTL
        if not self._cache_to_supabase(pool_id, pool_data):
            success = False

        # Cache to Tier 1 (Redis) - fastest access
        if not self._cache_to_redis(pool_id, pool_data):
            success = False

        return success

    def warmup_cache(self, pools: list[tuple[str, str]]) -> Dict:
        """
        Pre-warm cache with commonly used question pools

        Args:
            pools: List of (level, level_id) tuples

        Example:
            warmup_cache([
                ('topic', '62ae33ad-2598-4827-9eab-9d886586c7a6'),
                ('chapter', 'effce0f5-c5fd-413f-8fbd-fb5bc8b95c0f')
            ])
        """
        logger.info(f"🔥 Warming up cache for {len(pools)} question pools")

        results = {
            'success': 0,
            'failed': 0,
            'details': []
        }

        for level, level_id in pools:
            try:
                pool_data = self.get_question_pool(level, level_id)
                if pool_data:
                    results['success'] += 1
                    results['details'].append({
                        'pool_id': f"{level}_{level_id}",
                        'status': 'success',
                        'questions': pool_data['total_questions']
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'pool_id': f"{level}_{level_id}",
                        'status': 'failed',
                        'error': 'No data returned'
                    })
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'pool_id': f"{level}_{level_id}",
                    'status': 'error',
                    'error': str(e)
                })

        logger.info(f"✅ Cache warmup complete: {results['success']} success, {results['failed']} failed")
        return results

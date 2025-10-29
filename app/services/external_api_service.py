# app/services/external_api_service.py - External API Service (Tier 3)
import requests
import logging
from typing import Dict, List, Optional
from datetime import datetime

from config import Config

logger = logging.getLogger(__name__)

class ExternalAPIService:
    """Service for fetching question pools from external API (Tier 3 - Source of Truth)"""

    def __init__(self):
        self.base_url = Config.EXTERNAL_API_URL
        self.api_key = Config.EXTERNAL_API_KEY
        self.timeout = Config.EXTERNAL_API_TIMEOUT
        logger.info("External API service initialized")

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make HTTP request to external API with error handling"""
        try:
            url = f"{self.base_url}{endpoint}"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            logger.info(f"Fetching from external API: {endpoint}")
            response = requests.get(url, headers=headers, params=params, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"Resource not found: {endpoint}")
                return None
            else:
                logger.error(f"External API error {response.status_code}: {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"External API timeout after {self.timeout}s: {endpoint}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"External API connection error: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"External API unexpected error: {str(e)}")
            return None

    def fetch_question_pool(self, level: str, level_id: str,
                           page: int = 1, page_size: int = 100) -> Optional[Dict]:
        """
        Fetch question pool from external API

        Args:
            level: 'topic', 'chapter', 'subject', 'class', or 'exam'
            level_id: UUID of the level
            page: Page number (default: 1)
            page_size: Questions per page (default: 100)

        Returns:
            Question pool data or None if error
        """
        valid_levels = ['topic', 'chapter', 'subject', 'class', 'exam']
        if level not in valid_levels:
            logger.error(f"Invalid level: {level}. Must be one of {valid_levels}")
            return None

        endpoint = f"/api/hierarchy/{level}/{level_id}/questions/enhanced"
        params = {
            'page': page,
            'page_size': page_size
        }

        data = self._make_request(endpoint, params)

        if data:
            logger.info(f"Fetched {data.get('total_questions', 0)} questions from {level}/{level_id}")
            # Add metadata for caching
            data['fetched_at'] = datetime.now().isoformat()
            data['cache_source'] = 'external_api'

        return data

    def fetch_all_pages(self, level: str, level_id: str, page_size: int = 100) -> Optional[Dict]:
        """
        Fetch all pages of a question pool (for large datasets)

        Returns:
            Complete question pool with all pages merged
        """
        # Fetch first page
        first_page = self.fetch_question_pool(level, level_id, page=1, page_size=page_size)

        if not first_page:
            return None

        # If only one page, return it
        pagination = first_page.get('pagination', {})
        if not pagination.get('has_more', False):
            return first_page

        # Fetch remaining pages
        all_questions = first_page['questions']
        total_pages = pagination.get('total_pages', 1)

        for page in range(2, total_pages + 1):
            logger.info(f"Fetching page {page}/{total_pages} for {level}/{level_id}")
            page_data = self.fetch_question_pool(level, level_id, page=page, page_size=page_size)

            if page_data:
                all_questions.extend(page_data['questions'])
            else:
                logger.warning(f"Failed to fetch page {page}, returning partial data")
                break

        # Update first page with all questions
        first_page['questions'] = all_questions
        first_page['total_questions'] = len(all_questions)
        first_page['pagination']['page'] = 1
        first_page['pagination']['total_pages'] = 1
        first_page['pagination']['has_more'] = False

        logger.info(f"Fetched all {len(all_questions)} questions for {level}/{level_id}")
        return first_page

    def transform_to_internal_format(self, external_data: Dict) -> Dict:
        """
        Transform external API format to internal question pool format

        Returns:
            {
                'pool_id': str,
                'level': str,
                'level_id': str,
                'attributes': List[Dict],
                'questions': List[Dict],
                'metadata': Dict
            }
        """
        if not external_data:
            return None

        # Generate pool ID from level and level_id
        pool_id = f"{external_data['level']}_{external_data['level_id']}"

        # Transform questions to internal format
        internal_questions = []
        for q in external_data.get('questions', []):
            internal_questions.append({
                'id': q['id'],
                'content': q['content'],
                'options': q.get('options', []),
                'correct_answer': q['correct_answer'],
                'difficulty': q.get('difficulty', 0.5),
                'discrimination': q.get('discrimination', 1.0),
                'guessing': q.get('guessing', 0.25),
                'concepts': q.get('q_vector', [1, 0, 0, 0, 0]),  # Map q_vector to concepts
                'topic_id': q.get('topic_id'),
                'chapter_id': q.get('chapter_id'),
                'subject_id': q.get('subject_id'),
                'class_id': q.get('class_id'),
                'exam_id': q.get('exam_id')
            })

        # Transform attributes
        attributes = external_data.get('attributes', [])

        return {
            'pool_id': pool_id,
            'level': external_data['level'],
            'level_id': external_data['level_id'],
            'attribute_count': external_data.get('attribute_count', len(attributes)),
            'attributes': attributes,
            'questions': internal_questions,
            'total_questions': len(internal_questions),
            'metadata': {
                'fetched_at': external_data.get('fetched_at'),
                'cache_source': 'external_api',
                'original_pagination': external_data.get('pagination', {})
            }
        }

    def test_connection(self) -> bool:
        """Test connection to external API"""
        try:
            # Make a simple health check request
            response = requests.get(
                f"{self.base_url}/health",
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"External API connection test failed: {str(e)}")
            return False

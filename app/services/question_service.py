import uuid
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class QuestionService:
    """Service for managing questions and Q-matrix with 3-tier caching"""

    def __init__(self, cache_manager=None, supabase_service=None, redis_service=None):
        """
        Initialize Question Service

        Args:
            cache_manager: 3-Tier CacheManager (preferred)
            supabase_service: Direct Supabase access (fallback)
            redis_service: Direct Redis access (fallback)
        """
        self.cache_manager = cache_manager
        self.supabase = supabase_service
        self.redis = redis_service

        if cache_manager:
            logger.info("QuestionService initialized with 3-tier cache manager")
        else:
            logger.warning("QuestionService initialized without cache manager (legacy mode)")

    def store_questions(self, questions: List[Dict]) -> Dict:
        """Store and validate questions in database"""
        try:
            # Validate questions
            validation_result = self._validate_questions(questions)
            if not validation_result['valid']:
                return {'success': False, 'message': validation_result['error']}

            # Generate unique pool ID
            pool_id = str(uuid.uuid4())

            # Store questions in database
            success = self.supabase.store_questions(pool_id, questions)
            if not success:
                return {'success': False, 'message': 'Failed to store questions in database'}

            return {'success': True, 'question_pool_id': pool_id}

        except Exception as e:
            logger.error(f"Error storing questions: {str(e)}")
            return {'success': False, 'message': 'Internal error'}

    def get_questions_from_external(self, level: str, level_id: str,
                                    fetch_all_pages: bool = True) -> List[Dict]:
        """
        Get questions from external API with 3-tier caching

        Args:
            level: 'topic', 'chapter', 'subject', 'class', or 'exam'
            level_id: UUID of the level
            fetch_all_pages: If True, fetch all pages from external API

        Returns:
            List of questions
        """
        if not self.cache_manager:
            logger.error("Cache manager not initialized, cannot fetch from external API")
            return []

        try:
            # Use 3-tier cache to get question pool
            pool_data = self.cache_manager.get_question_pool(level, level_id, fetch_all_pages)

            if pool_data:
                return pool_data.get('questions', [])
            else:
                logger.warning(f"No questions found for {level}/{level_id}")
                return []

        except Exception as e:
            logger.error(f"Error fetching questions from external API: {str(e)}")
            return []

    def get_question_pool(self, level: str, level_id: str,
                         fetch_all_pages: bool = True) -> Optional[Dict]:
        """
        Get complete question pool with metadata and attributes

        Returns:
            {
                'pool_id': str,
                'level': str,
                'level_id': str,
                'attributes': List[Dict],
                'questions': List[Dict],
                'total_questions': int,
                'metadata': Dict
            }
        """
        if not self.cache_manager:
            logger.error("Cache manager not initialized")
            return None

        return self.cache_manager.get_question_pool(level, level_id, fetch_all_pages)

    def get_questions(self, pool_id: Optional[str] = None) -> List[Dict]:
        """Get questions from database (legacy method for backwards compatibility)"""
        try:
            if pool_id:
                # Check if pool_id is in format "level_level_id"
                if '_' in pool_id and self.cache_manager:
                    parts = pool_id.split('_', 1)
                    if len(parts) == 2:
                        level, level_id = parts
                        return self.get_questions_from_external(level, level_id)

                # Fetch from database (old behavior)
                if self.supabase:
                    questions = self.supabase.get_questions_by_pool(pool_id)

                    # Optionally cache in Redis for faster access
                    if self.redis and questions:
                        for question in questions:
                            self.redis.cache_question(question['id'], question)

                    return questions
            else:
                # Return default questions if no pool specified
                return self._get_default_questions()
        except Exception as e:
            logger.error(f"Error getting questions: {str(e)}")
            return []

    def get_question_by_id(self, question_id: str) -> Optional[Dict]:
        """Get single question by ID (check Redis cache first)"""
        try:
            # Try Redis cache first
            if self.redis:
                cached = self.redis.get_cached_question(question_id)
                if cached:
                    logger.debug(f"Cache hit for question {question_id}")
                    return cached

            # Fetch from database
            question = self.supabase.get_question_by_id(question_id)

            # Cache for future requests
            if self.redis and question:
                self.redis.cache_question(question_id, question)

            return question

        except Exception as e:
            logger.error(f"Error getting question {question_id}: {str(e)}")
            return None
    
    def create_q_matrix(self, questions: List[Dict]) -> Dict[str, List[int]]:
        """Create Q-matrix from questions"""
        q_matrix = {}
        for question in questions:
            q_matrix[question['id']] = question.get('concepts', [1, 0, 0, 0, 0])
        return q_matrix
    
    def _validate_questions(self, questions: List[Dict]) -> Dict:
        """Validate question format"""
        required_fields = ['id', 'content', 'options', 'correct_answer']
        
        for i, question in enumerate(questions):
            # Check required fields
            for field in required_fields:
                if field not in question:
                    return {
                        'valid': False,
                        'error': f'Question {i+1} missing required field: {field}'
                    }
            
            # Validate concepts array
            concepts = question.get('concepts', [])
            if not isinstance(concepts, list):
                return {
                    'valid': False,
                    'error': f'Question {i+1} has invalid concepts format'
                }
            
            # Validate difficulty
            difficulty = question.get('difficulty')
            if difficulty is not None:
                try:
                    float(difficulty)
                except (ValueError, TypeError):
                    return {
                        'valid': False,
                        'error': f'Question {i+1} has invalid difficulty value'
                    }
        
        return {'valid': True}
    
    def _get_default_questions(self) -> List[Dict]:
        """Get default questions for testing"""
        return [
            {
                "id": "q1",
                "content": "What is 15 + 27?",
                "options": ["40", "42", "44", "46"],
                "correct_answer": "42",
                "concepts": [1, 0, 0, 0, 0],
                "difficulty": 0.3,
                "discrimination": 1.2
            },
            {
                "id": "q2",
                "content": "Solve for x: 2x + 5 = 15",
                "options": ["3", "5", "7", "10"],
                "correct_answer": "5",
                "concepts": [1, 1, 0, 0, 0],
                "difficulty": 0.6,
                "discrimination": 1.5
            },
            {
                "id": "q3",
                "content": "What is the derivative of x²?",
                "options": ["x", "2x", "x²", "2x²"],
                "correct_answer": "2x",
                "concepts": [1, 1, 1, 0, 0],
                "difficulty": 0.8,
                "discrimination": 1.8
            }
        ]


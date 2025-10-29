import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from supabase import create_client, Client

from config import Config

logger = logging.getLogger(__name__)

class SupabaseService:
    """Service for interacting with Supabase database"""
    
    def __init__(self):
        self.supabase_url = Config.SUPABASE_URL
        self.supabase_key = Config.SUPABASE_ANON_KEY
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase URL and key must be provided in environment variables")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        logger.info("Initialized Supabase service")
    
    def test_connection(self) -> bool:
        """Test the connection to Supabase"""
        try:
            # Simple query to test connection
            result = self.client.table('students').select('count').execute()
            return True
        except Exception as e:
            logger.error(f"Supabase connection test failed: {str(e)}")
            return False
    
    # Student Management Methods
    def get_or_create_student(self, student_id: str, concept_names: List[str]) -> Dict:
        """Get existing student or create new one"""
        try:
            # Try to get existing student
            result = self.client.table('students').select('*').eq('id', student_id).execute()
            
            if result.data:
                return result.data[0]
            
            # Create new student
            student_data = {
                'id': student_id,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            result = self.client.table('students').insert(student_data).execute()
            
            # Initialize proficiency for all concepts
            self.create_user_proficiency(student_id, [0.5] * len(concept_names), concept_names)
            
            logger.info(f"Created new student: {student_id}")
            return result.data[0] if result.data else {}
            
        except Exception as e:
            logger.error(f"Error creating/getting student: {str(e)}")
            raise
    
    def get_student(self, student_id: str) -> Optional[Dict]:
        """Get student by ID"""
        try:
            result = self.client.table('students').select('*').eq('id', student_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting student: {str(e)}")
            return None
    
    # User Proficiency Methods
    def create_user_proficiency(self, student_id: str, proficiency: List[float], 
                               concept_names: List[str]) -> bool:
        """Create initial user proficiency record"""
        try:
            # Create individual records for each concept
            proficiency_records = []
            for i, concept_name in enumerate(concept_names):
                proficiency_records.append({
                    'student_id': student_id,
                    'concept_name': concept_name,
                    'proficiency_value': proficiency[i] if i < len(proficiency) else 0.5,
                    'confidence': 0.0,  # Low initial confidence
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                })
            
            result = self.client.table('student_proficiencies').insert(proficiency_records).execute()
            logger.info(f"Created proficiency records for student {student_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating user proficiency: {str(e)}")
            return False
    
    def get_current_proficiency(self, student_id: str) -> List[float]:
        """Get current user proficiency"""
        try:
            result = self.client.table('student_proficiencies').select('*').eq('student_id', student_id).order('concept_name').execute()
            
            if result.data:
                return [record['proficiency_value'] for record in result.data]
            return []
            
        except Exception as e:
            logger.error(f"Error getting user proficiency: {str(e)}")
            return []
    
    def get_concept_names(self, student_id: str) -> List[str]:
        """Get concept names for student"""
        try:
            result = self.client.table('student_proficiencies').select('concept_name').eq('student_id', student_id).order('concept_name').execute()
            
            if result.data:
                return [record['concept_name'] for record in result.data]
            return ['Math', 'Algebra', 'Geometry', 'Statistics', 'Calculus']
            
        except Exception as e:
            logger.error(f"Error getting concept names: {str(e)}")
            return ['Math', 'Algebra', 'Geometry', 'Statistics', 'Calculus']
    
    def update_user_proficiency(self, student_id: str, proficiency: List[float]) -> bool:
        """Update user proficiency"""
        try:
            # Get existing proficiency records
            result = self.client.table('student_proficiencies').select('*').eq('student_id', student_id).order('concept_name').execute()
            
            if not result.data or len(result.data) != len(proficiency):
                logger.error(f"Proficiency length mismatch for {student_id}")
                return False
            
            # Update each proficiency record
            for i, record in enumerate(result.data):
                update_data = {
                    'proficiency_value': proficiency[i],
                    'updated_at': datetime.now().isoformat()
                }
                
                self.client.table('student_proficiencies').update(update_data).eq('id', record['id']).execute()
            
            logger.info(f"Updated proficiency for student {student_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating user proficiency: {str(e)}")
            return False
    
    # Response Data Methods
    def store_response(self, student_id: str, session_id: str, question_id: str, 
                      response: int, proficiency_before: List[float], 
                      proficiency_after: List[float]) -> bool:
        """Store user response and proficiency changes"""
        try:
            data = {
                'student_id': student_id,
                'session_id': session_id,
                'question_id': question_id,
                'response': response,
                'is_correct': response,  # Assuming response is 0/1
                'proficiency_before': proficiency_before,
                'proficiency_after': proficiency_after,
                'timestamp': datetime.now().isoformat()
            }
            
            result = self.client.table('test_responses').insert(data).execute()
            logger.info(f"Stored response for student {student_id}, question {question_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing response: {str(e)}")
            return False
    
    def get_user_responses(self, student_id: str, session_id: Optional[str] = None) -> List[Dict]:
        """Get user response history"""
        try:
            query = self.client.table('test_responses').select('*').eq('student_id', student_id)
            
            if session_id:
                query = query.eq('session_id', session_id)
            
            result = query.order('timestamp').execute()
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting user responses: {str(e)}")
            return []
    
    # Test Summary Methods
    def store_test_summary(self, student_id: str, session_id: str, test_summary: Dict) -> bool:
        """Store test session summary"""
        try:
            data = {
                'id': session_id,
                'student_id': student_id,
                'initial_proficiency': test_summary.get('initial_proficiency'),
                'final_proficiency': test_summary.get('final_proficiency'),
                'total_questions': test_summary.get('total_questions', 0),
                'correct_responses': test_summary.get('correct_responses', 0),
                'accuracy': test_summary.get('accuracy', 0.0),
                'learning_gain': test_summary.get('learning_gain', 0.0),
                'test_efficiency': test_summary.get('test_efficiency', 0.0),
                'status': 'completed',
                'started_at': datetime.now().isoformat(),
                'completed_at': datetime.now().isoformat()
            }
            
            # Upsert test session data
            result = self.client.table('test_sessions').upsert(data).execute()
            logger.info(f"Stored test summary for student {student_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing test summary: {str(e)}")
            return False
    
    def get_test_history(self, student_id: str) -> List[Dict]:
        """Get test history for a student"""
        try:
            result = self.client.table('test_sessions').select('*').eq('student_id', student_id).order('completed_at', desc=True).execute()
            
            history = []
            for session in result.data:
                history.append({
                    'session_id': session['id'],
                    'started_at': session.get('started_at'),
                    'completed_at': session.get('completed_at'),
                    'total_questions': session.get('total_questions', 0),
                    'accuracy': session.get('accuracy', 0.0),
                    'status': session.get('status', 'completed'),
                    'learning_gain': session.get('learning_gain', 0.0),
                    'final_proficiency': session.get('final_proficiency', [])
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting test history: {str(e)}")
            return []
    
    def get_learning_progress(self, student_id: str) -> Dict:
        """Get student's learning progress over time"""
        try:
            # Get all completed test sessions
            result = self.client.table('test_sessions').select('*').eq('student_id', student_id).eq('status', 'completed').order('completed_at').execute()

            sessions = result.data
            if not sessions:
                return {'progress_timeline': [], 'concept_progress': {}}

            # Build timeline
            timeline = []
            for session in sessions:
                timeline.append({
                    'date': session.get('completed_at'),
                    'proficiency': session.get('final_proficiency', []),
                    'accuracy': session.get('accuracy', 0.0),
                    'questions_answered': session.get('total_questions', 0)
                })

            # Calculate concept-specific progress
            concept_names = self.get_concept_names(student_id)
            concept_progress = {}

            for i, concept in enumerate(concept_names):
                concept_values = []
                for session in sessions:
                    final_prof = session.get('final_proficiency', [])
                    if final_prof and i < len(final_prof):
                        concept_values.append({
                            'date': session.get('completed_at'),
                            'value': final_prof[i]
                        })

                concept_progress[concept] = {
                    'timeline': concept_values,
                    'improvement': concept_values[-1]['value'] - concept_values[0]['value'] if len(concept_values) > 1 else 0,
                    'current_level': concept_values[-1]['value'] if concept_values else 0.5
                }

            return {
                'progress_timeline': timeline,
                'concept_progress': concept_progress,
                'total_sessions': len(sessions),
                'avg_accuracy': sum(s.get('accuracy', 0) for s in sessions) / len(sessions)
            }

        except Exception as e:
            logger.error(f"Error getting learning progress for {student_id}: {str(e)}")
            return {'progress_timeline': [], 'concept_progress': {}}

    # Question Pool Management Methods (Tier 2 Cache)
    def cache_question_pool(self, pool_id: str, pool_data: Dict) -> bool:
        """
        Cache question pool in Supabase (Tier 2)
        Stores both metadata and questions
        """
        try:
            # Store pool metadata in question_pools table
            pool_metadata = {
                'id': pool_id,
                'level': pool_data.get('level'),
                'level_id': pool_data.get('level_id'),
                'attribute_count': pool_data.get('attribute_count', 0),
                'attributes': pool_data.get('attributes', []),
                'total_questions': pool_data.get('total_questions', 0),
                'metadata': pool_data.get('metadata', {}),
                'cached_at': datetime.now().isoformat(),
                'expires_at': (datetime.now().timestamp() + Config.SUPABASE_CACHE_EXPIRY).__str__()
            }

            # Upsert pool metadata
            self.client.table('question_pools').upsert(pool_metadata).execute()

            # Store individual questions
            questions = pool_data.get('questions', [])
            if questions:
                question_records = []
                for question in questions:
                    question_records.append({
                        'id': question['id'],
                        'pool_id': pool_id,
                        'content': question['content'],
                        'options': question.get('options', []),
                        'correct_answer': question['correct_answer'],
                        'concepts': question.get('concepts', [1, 0, 0, 0, 0]),
                        'difficulty': question.get('difficulty', 0.5),
                        'discrimination': question.get('discrimination', 1.0),
                        'guessing': question.get('guessing', 0.25),
                        'topic_id': question.get('topic_id'),
                        'chapter_id': question.get('chapter_id'),
                        'subject_id': question.get('subject_id'),
                        'class_id': question.get('class_id'),
                        'exam_id': question.get('exam_id'),
                        'created_at': datetime.now().isoformat()
                    })

                # Upsert questions (update if exists, insert if not)
                self.client.table('questions').upsert(question_records).execute()

            logger.info(f"Cached question pool {pool_id} in Supabase (Tier 2) with {len(questions)} questions")
            return True

        except Exception as e:
            logger.error(f"Error caching question pool in Supabase: {str(e)}")
            return False

    def get_cached_question_pool(self, pool_id: str) -> Optional[Dict]:
        """
        Get cached question pool from Supabase (Tier 2)
        Returns None if not found or expired
        """
        try:
            # Get pool metadata
            pool_result = self.client.table('question_pools').select('*').eq('id', pool_id).execute()

            if not pool_result.data:
                logger.info(f"Cache MISS (Supabase): pool {pool_id}")
                return None

            pool_meta = pool_result.data[0]

            # Check if cache expired
            expires_at = float(pool_meta.get('expires_at', 0))
            if expires_at < datetime.now().timestamp():
                logger.info(f"Cache EXPIRED (Supabase): pool {pool_id}")
                # Optionally delete expired cache
                self.invalidate_question_pool(pool_id)
                return None

            # Get questions for this pool
            questions_result = self.client.table('questions').select('*').eq('pool_id', pool_id).execute()

            questions = []
            for row in questions_result.data:
                questions.append({
                    'id': row['id'],
                    'content': row['content'],
                    'options': row['options'],
                    'correct_answer': row['correct_answer'],
                    'concepts': row.get('concepts', [1, 0, 0, 0, 0]),
                    'difficulty': row.get('difficulty', 0.5),
                    'discrimination': row.get('discrimination', 1.0),
                    'guessing': row.get('guessing', 0.25),
                    'topic_id': row.get('topic_id'),
                    'chapter_id': row.get('chapter_id'),
                    'subject_id': row.get('subject_id'),
                    'class_id': row.get('class_id'),
                    'exam_id': row.get('exam_id')
                })

            # Reconstruct pool data
            pool_data = {
                'pool_id': pool_id,
                'level': pool_meta.get('level'),
                'level_id': pool_meta.get('level_id'),
                'attribute_count': pool_meta.get('attribute_count', 0),
                'attributes': pool_meta.get('attributes', []),
                'questions': questions,
                'total_questions': len(questions),
                'metadata': pool_meta.get('metadata', {}),
                'cache_tier': 'supabase',
                'cached_at': pool_meta.get('cached_at')
            }

            logger.info(f"Cache HIT (Supabase): pool {pool_id} with {len(questions)} questions")
            return pool_data

        except Exception as e:
            logger.error(f"Error getting cached pool from Supabase: {str(e)}")
            return None

    def invalidate_question_pool(self, pool_id: str) -> bool:
        """Invalidate/delete question pool from Supabase cache"""
        try:
            # Delete questions
            self.client.table('questions').delete().eq('pool_id', pool_id).execute()
            # Delete pool metadata
            self.client.table('question_pools').delete().eq('id', pool_id).execute()

            logger.info(f"Invalidated question pool {pool_id} from Supabase")
            return True

        except Exception as e:
            logger.error(f"Error invalidating pool from Supabase: {str(e)}")
            return False

    def store_questions(self, pool_id: str, questions: List[Dict]) -> bool:
        """Store question pool in database (legacy method for backwards compatibility)"""
        try:
            # Prepare question records
            question_records = []
            for question in questions:
                question_records.append({
                    'id': question['id'],
                    'pool_id': pool_id,
                    'content': question['content'],
                    'options': question.get('options', []),
                    'correct_answer': question['correct_answer'],
                    'concepts': question.get('concepts', [1, 0, 0, 0, 0]),
                    'difficulty': question.get('difficulty', 0.5),
                    'discrimination': question.get('discrimination', 1.0),
                    'created_at': datetime.now().isoformat()
                })

            # Insert questions into database
            result = self.client.table('questions').insert(question_records).execute()
            logger.info(f"Stored {len(questions)} questions in pool {pool_id}")
            return True

        except Exception as e:
            logger.error(f"Error storing questions: {str(e)}")
            return False

    def get_questions_by_pool(self, pool_id: str) -> List[Dict]:
        """Get all questions from a specific pool"""
        try:
            result = self.client.table('questions').select('*').eq('pool_id', pool_id).execute()

            questions = []
            for row in result.data:
                questions.append({
                    'id': row['id'],
                    'content': row['content'],
                    'options': row['options'],
                    'correct_answer': row['correct_answer'],
                    'concepts': row['concepts'],
                    'difficulty': row.get('difficulty', 0.5),
                    'discrimination': row.get('discrimination', 1.0)
                })

            return questions

        except Exception as e:
            logger.error(f"Error getting questions from pool {pool_id}: {str(e)}")
            return []

    def get_question_by_id(self, question_id: str) -> Optional[Dict]:
        """Get a specific question by ID"""
        try:
            result = self.client.table('questions').select('*').eq('id', question_id).execute()

            if result.data:
                row = result.data[0]
                return {
                    'id': row['id'],
                    'content': row['content'],
                    'options': row['options'],
                    'correct_answer': row['correct_answer'],
                    'concepts': row['concepts'],
                    'difficulty': row.get('difficulty', 0.5),
                    'discrimination': row.get('discrimination', 1.0)
                }

            return None

        except Exception as e:
            logger.error(f"Error getting question {question_id}: {str(e)}")
            return None

    # Session Management Methods (Database)
    def create_session(self, session_id: str, student_id: str, question_pool_id: str,
                      initial_proficiency: List[float]) -> bool:
        """Create a new test session record in database"""
        try:
            session_data = {
                'id': session_id,
                'student_id': student_id,
                'question_pool_id': question_pool_id,
                'status': 'active',
                'initial_proficiency': initial_proficiency,
                'total_questions': 0,
                'correct_responses': 0,
                'started_at': datetime.now().isoformat(),
                'last_activity': datetime.now().isoformat()
            }

            result = self.client.table('test_sessions').insert(session_data).execute()
            logger.info(f"Created session {session_id} for student {student_id}")
            return True

        except Exception as e:
            logger.error(f"Error creating session: {str(e)}")
            return False

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session from database"""
        try:
            result = self.client.table('test_sessions').select('*').eq('id', session_id).execute()
            return result.data[0] if result.data else None

        except Exception as e:
            logger.error(f"Error getting session {session_id}: {str(e)}")
            return None

    def update_session_activity(self, session_id: str) -> bool:
        """Update last activity timestamp for session"""
        try:
            update_data = {
                'last_activity': datetime.now().isoformat()
            }

            self.client.table('test_sessions').update(update_data).eq('id', session_id).execute()
            return True

        except Exception as e:
            logger.error(f"Error updating session activity: {str(e)}")
            return False

    def complete_session(self, session_id: str, final_proficiency: List[float],
                        total_questions: int, correct_responses: int) -> bool:
        """Mark session as completed with final results"""
        try:
            accuracy = correct_responses / total_questions if total_questions > 0 else 0.0

            update_data = {
                'status': 'completed',
                'final_proficiency': final_proficiency,
                'total_questions': total_questions,
                'correct_responses': correct_responses,
                'accuracy': accuracy,
                'completed_at': datetime.now().isoformat()
            }

            self.client.table('test_sessions').update(update_data).eq('id', session_id).execute()
            logger.info(f"Completed session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error completing session: {str(e)}")
            return False
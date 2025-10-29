from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import uuid
from datetime import datetime

from services.redis_service import RedisService
from services.question_service import QuestionService
from services.supabase_service import SupabaseService
from services.external_api_service import ExternalAPIService
from services.cache_manager import CacheManager
from services.scheduler import SessionCleanupScheduler
from models.adaptive_engine import AdaptiveEngine
from config import Config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialize base services
redis_service = RedisService()
supabase_service = SupabaseService()
external_api_service = ExternalAPIService()

# Initialize 3-tier cache manager
cache_manager = CacheManager(
    redis_service=redis_service,
    supabase_service=supabase_service,
    external_api_service=external_api_service
)

# Initialize question service with cache manager
question_service = QuestionService(
    cache_manager=cache_manager,
    supabase_service=supabase_service,
    redis_service=redis_service
)

adaptive_engine = AdaptiveEngine()

# Initialize and start session cleanup scheduler
cleanup_scheduler = SessionCleanupScheduler(
    redis_service=redis_service,
    interval_minutes=10,  # Run cleanup every 10 minutes
    inactivity_threshold=30  # Remove sessions inactive for 30 minutes
)
cleanup_scheduler.start()

logger.info("✅ Adaptive Testing System initialized with 3-tier caching")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint with 3-tier cache status"""
    return jsonify({
        'status': 'healthy',
        'version': Config.VERSION,
        'timestamp': datetime.now().isoformat(),
        'architecture': '3-tier-cache',
        'services': {
            'tier1_redis': redis_service.test_connection(),
            'tier2_supabase': supabase_service.test_connection(),
            'tier3_external_api': external_api_service.test_connection()
        },
        'cache_stats': cache_manager.get_cache_stats()
    })
@app.route('/', methods=['GET'])
def root_health_check():
    """Lightweight root availability probe."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/questions/upload', methods=['POST'])
def upload_questions():
    """Upload questions for testing"""
    try:
        data = request.get_json()
        questions = data.get('questions', [])
        
        if not questions:
            return jsonify({'error': 'No questions provided'}), 400
        
        # Validate and store questions
        result = question_service.store_questions(questions)
        if not result['success']:
            return jsonify({'error': result['message']}), 400
            
        return jsonify({
            'message': 'Questions uploaded successfully',
            'count': len(questions),
            'question_pool_id': result['question_pool_id']
        })
        
    except Exception as e:
        logger.error(f"Error uploading questions: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/test/start', methods=['POST'])
def start_test():
    """Start a new adaptive test session (NEW ARCHITECTURE: DB + Redis hot data)"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        question_pool_id = data.get('question_pool_id')
        concept_names = data.get('concept_names', ['Math', 'Algebra', 'Geometry', 'Statistics', 'Calculus'])
        end_criteria = data.get('end_criteria', {
            'type': 'fixed_length',
            'max_questions': 20,
            'min_questions': 5,
            'precision_threshold': 0.3
        })

        if not student_id:
            return jsonify({'error': 'student_id is required'}), 400

        # Create new session
        session_id = str(uuid.uuid4())

        # Get questions from DATABASE (not Redis)
        questions = question_service.get_questions(question_pool_id)
        if not questions:
            return jsonify({'error': 'No questions available'}), 404

        q_matrix = question_service.create_q_matrix(questions)

        # Get or create student proficiency
        student = supabase_service.get_or_create_student(student_id, concept_names)
        initial_proficiency = supabase_service.get_current_proficiency(student_id)

        if not initial_proficiency:
            # Initialize with neutral proficiency for new student
            initial_proficiency = [0.5] * len(concept_names)
            supabase_service.create_user_proficiency(student_id, initial_proficiency, concept_names)

        # Create session in DATABASE
        supabase_service.create_session(session_id, student_id, question_pool_id, initial_proficiency)

        # Select first question
        next_question = adaptive_engine.select_next_question(
            questions, q_matrix, initial_proficiency, []
        )

        # Store ONLY hot data in Redis (minimal state)
        redis_state = {
            'student_id': student_id,
            'question_pool_id': question_pool_id,
            'current_proficiency': initial_proficiency,
            'next_question_id': next_question['id'],
            'status': 'active',
            'questions_answered': 0,
            'correct_count': 0,
            'end_criteria': end_criteria
        }
        redis_service.store_session_state(session_id, redis_state)

        return jsonify({
            'session_id': session_id,
            'student_id': student_id,
            'initial_proficiency': initial_proficiency,
            'concept_names': concept_names,
            'next_question': next_question,
            'status': 'started'
        })

    except Exception as e:
        logger.error(f"Error starting test: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/test/submit', methods=['POST'])
def submit_response():
    """Submit response and get next question (NEW ARCHITECTURE: Submission locks + minimal Redis)"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        question_id = data.get('question_id')
        response = data.get('response')  # 0 or 1

        if not all([session_id, question_id is not None, response is not None]):
            return jsonify({'error': 'session_id, question_id, and response are required'}), 400

        # PREVENT DOUBLE SUBMISSION with Redis lock
        if not redis_service.acquire_submission_lock(session_id, question_id):
            return jsonify({'error': 'This question has already been submitted'}), 409

        try:
            # Get session state from Redis (hot data)
            session_state = redis_service.get_session_state(session_id)
            if not session_state:
                return jsonify({'error': 'Session not found or expired'}), 404

            if session_state['status'] != 'active':
                return jsonify({'error': 'Session is not active'}), 400

            student_id = session_state['student_id']
            current_proficiency = session_state['current_proficiency']
            question_pool_id = session_state['question_pool_id']

            # Get question from database (with cache)
            question = question_service.get_question_by_id(question_id)
            if not question:
                return jsonify({'error': 'Question not found'}), 404

            # Get all questions for Q-matrix
            questions = question_service.get_questions(question_pool_id)
            q_matrix = question_service.create_q_matrix(questions)

            # Update proficiency using adaptive engine
            new_proficiency = adaptive_engine.update_ability(
                current_proficiency, question, response, q_matrix
            )

            # Update counters
            questions_answered = session_state['questions_answered'] + 1
            correct_count = session_state['correct_count'] + (1 if response == 1 else 0)

            # SAVE TO DATABASE (permanent record)
            supabase_service.update_user_proficiency(student_id, new_proficiency)
            supabase_service.store_response(
                student_id, session_id, question_id, response,
                current_proficiency, new_proficiency
            )
            supabase_service.update_session_activity(session_id)

            # Build response list for end criteria check
            responses = supabase_service.get_user_responses(student_id, session_id)

            # Check end criteria
            should_continue = adaptive_engine.should_continue(
                responses, new_proficiency, session_state['end_criteria']
            )

            if should_continue:
                # Select next question
                next_question = adaptive_engine.select_next_question(
                    questions, q_matrix, new_proficiency, responses
                )

                # UPDATE REDIS (hot data only)
                redis_service.update_session_proficiency(
                    session_id, new_proficiency, questions_answered
                )

                # Update next question in state
                session_state['next_question_id'] = next_question['id']
                session_state['correct_count'] = correct_count
                redis_service.store_session_state(session_id, session_state)

                return jsonify({
                    'status': 'continue',
                    'current_proficiency': new_proficiency,
                    'next_question': next_question,
                    'questions_answered': questions_answered
                })
            else:
                # End test - save final results to DATABASE
                supabase_service.complete_session(
                    session_id, new_proficiency, questions_answered, correct_count
                )

                # CLEANUP Redis (remove hot data)
                redis_service.delete_session_state(session_id)

                return jsonify({
                    'status': 'completed',
                    'final_proficiency': new_proficiency,
                    'total_questions': questions_answered,
                    'accuracy': correct_count / questions_answered if questions_answered > 0 else 0
                })

        finally:
            # Always release the lock
            redis_service.release_submission_lock(session_id, question_id)

    except Exception as e:
        logger.error(f"Error submitting response: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/test/status/<session_id>', methods=['GET'])
def get_test_status(session_id):
    """Get current test status (NEW ARCHITECTURE: Redis + Database)"""
    try:
        # Try to get from Redis first (active sessions)
        session_state = redis_service.get_session_state(session_id)

        if session_state:
            # Active session - data in Redis
            return jsonify({
                'session_id': session_id,
                'status': session_state['status'],
                'current_proficiency': session_state['current_proficiency'],
                'questions_answered': session_state['questions_answered'],
                'is_active': True
            })
        else:
            # Check database for completed/expired sessions
            session_data = supabase_service.get_session(session_id)
            if not session_data:
                return jsonify({'error': 'Session not found'}), 404

            return jsonify({
                'session_id': session_id,
                'status': session_data.get('status', 'expired'),
                'current_proficiency': session_data.get('final_proficiency', session_data.get('initial_proficiency', [])),
                'questions_answered': session_data.get('total_questions', 0),
                'is_active': False,
                'started_at': session_data.get('started_at'),
                'completed_at': session_data.get('completed_at')
            })

    except Exception as e:
        logger.error(f"Error getting test status: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/student/<student_id>/proficiency', methods=['GET'])
def get_student_proficiency(student_id):
    """Get student's current proficiency"""
    try:
        student = supabase_service.get_student(student_id)
        if not student:
            return jsonify({'error': 'Student not found'}), 404
            
        proficiency = supabase_service.get_current_proficiency(student_id)
        concept_names = supabase_service.get_concept_names(student_id)
        
        return jsonify({
            'student_id': student_id,
            'proficiency': proficiency,
            'concept_names': concept_names,
            'last_updated': student.get('updated_at') if student else None
        })
        
    except Exception as e:
        logger.error(f"Error getting student proficiency: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/student/<student_id>/history', methods=['GET'])
def get_student_history(student_id):
    """Get student's test history"""
    try:
        history = supabase_service.get_test_history(student_id)
        
        return jsonify({
            'student_id': student_id,
            'test_sessions': history
        })
        
    except Exception as e:
        logger.error(f"Error getting student history: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/student/<student_id>/progress', methods=['GET'])
def get_student_progress(student_id):
    """Get student's learning progress over time"""
    try:
        progress = supabase_service.get_learning_progress(student_id)
        
        return jsonify({
            'student_id': student_id,
            'progress_data': progress
        })
        
    except Exception as e:
        logger.error(f"Error getting student progress: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/test/end/<session_id>', methods=['POST'])
def end_test(session_id):
    """Manually end a test session (NEW ARCHITECTURE)"""
    try:
        # Get session state from Redis
        session_state = redis_service.get_session_state(session_id)

        if session_state:
            # Active session in Redis
            student_id = session_state['student_id']
            current_proficiency = session_state['current_proficiency']
            questions_answered = session_state['questions_answered']
            correct_count = session_state.get('correct_count', 0)

            # Save final results to DATABASE
            supabase_service.complete_session(
                session_id, current_proficiency, questions_answered, correct_count
            )

            # Cleanup Redis
            redis_service.delete_session_state(session_id)

            return jsonify({
                'status': 'ended',
                'final_proficiency': current_proficiency,
                'total_questions': questions_answered,
                'accuracy': correct_count / questions_answered if questions_answered > 0 else 0
            })
        else:
            # Check if already in database
            session_data = supabase_service.get_session(session_id)
            if not session_data:
                return jsonify({'error': 'Session not found'}), 404

            return jsonify({
                'status': session_data.get('status', 'already_ended'),
                'final_proficiency': session_data.get('final_proficiency', []),
                'total_questions': session_data.get('total_questions', 0),
                'accuracy': session_data.get('accuracy', 0)
            })

    except Exception as e:
        logger.error(f"Error ending test: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/sessions/cleanup', methods=['POST'])
def cleanup_sessions():
    """Manually trigger cleanup of inactive sessions"""
    try:
        inactivity_minutes = request.get_json().get('inactivity_minutes', 30) if request.is_json else 30

        cleanup_count = redis_service.cleanup_inactive_sessions(inactivity_minutes)

        return jsonify({
            'message': f'Cleanup completed',
            'sessions_removed': cleanup_count,
            'inactivity_threshold_minutes': inactivity_minutes
        })

    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/debug/redis/stats', methods=['GET'])
def get_redis_stats():
    """Get Redis statistics for monitoring"""
    try:
        stats = redis_service.get_stats()

        return jsonify({
            'redis_stats': stats,
            'architecture': '3-tier-cache',
            'description': 'Tier 1: Redis (hot cache), stores active session state and question pools'
        })

    except Exception as e:
        logger.error(f"Error getting Redis stats: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# ===== 3-TIER CACHE ENDPOINTS =====

@app.route('/api/cache/question-pool/<level>/<level_id>', methods=['GET'])
def get_question_pool_cached(level, level_id):
    """
    Get question pool with 3-tier caching

    Query params:
        - fetch_all_pages: bool (default: true)
    """
    try:
        fetch_all_pages = request.args.get('fetch_all_pages', 'true').lower() == 'true'

        pool_data = question_service.get_question_pool(level, level_id, fetch_all_pages)

        if not pool_data:
            return jsonify({'error': 'Question pool not found'}), 404

        return jsonify({
            'pool_data': pool_data,
            'cache_tier': pool_data.get('cache_tier', 'unknown'),
            'cached_at': pool_data.get('cached_at')
        })

    except Exception as e:
        logger.error(f"Error getting question pool: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/cache/question-pool/<level>/<level_id>/invalidate', methods=['POST'])
def invalidate_question_pool(level, level_id):
    """Invalidate question pool from all cache tiers"""
    try:
        success = cache_manager.invalidate_question_pool(level, level_id)

        return jsonify({
            'message': 'Question pool invalidated from all cache tiers',
            'pool_id': f"{level}_{level_id}",
            'success': success
        })

    except Exception as e:
        logger.error(f"Error invalidating question pool: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/cache/question-pool/<level>/<level_id>/refresh', methods=['POST'])
def refresh_question_pool(level, level_id):
    """Force refresh question pool from external API"""
    try:
        pool_data = cache_manager.refresh_question_pool(level, level_id)

        if not pool_data:
            return jsonify({'error': 'Failed to refresh question pool'}), 500

        return jsonify({
            'message': 'Question pool refreshed successfully',
            'pool_id': pool_data.get('pool_id'),
            'total_questions': pool_data.get('total_questions'),
            'cache_tier': 'external_api'
        })

    except Exception as e:
        logger.error(f"Error refreshing question pool: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/cache/stats', methods=['GET'])
def get_cache_stats():
    """Get detailed cache statistics"""
    try:
        stats = cache_manager.get_cache_stats()

        return jsonify({
            'cache_stats': stats,
            'description': {
                'tier1': 'Redis (~1ms latency, 24h TTL)',
                'tier2': 'Supabase (~50ms latency, 7d TTL)',
                'tier3': 'External API (~500ms latency, source of truth)'
            }
        })

    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/cache/stats/reset', methods=['POST'])
def reset_cache_stats():
    """Reset cache statistics"""
    try:
        cache_manager.reset_cache_stats()

        return jsonify({
            'message': 'Cache statistics reset successfully'
        })

    except Exception as e:
        logger.error(f"Error resetting cache stats: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/cache/warmup', methods=['POST'])
def warmup_cache():
    """
    Pre-warm cache with commonly used question pools

    Body:
        {
            "pools": [
                {"level": "topic", "level_id": "uuid"},
                {"level": "chapter", "level_id": "uuid"}
            ]
        }
    """
    try:
        data = request.get_json()
        pools_data = data.get('pools', [])

        if not pools_data:
            return jsonify({'error': 'No pools provided'}), 400

        # Convert to list of tuples
        pools = [(p['level'], p['level_id']) for p in pools_data]

        results = cache_manager.warmup_cache(pools)

        return jsonify({
            'message': 'Cache warmup completed',
            'results': results
        })

    except Exception as e:
        logger.error(f"Error warming up cache: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=Config.DEBUG)

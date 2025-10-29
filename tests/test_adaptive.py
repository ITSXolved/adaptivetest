import pytest
import json
from app.main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_check(client):
    """Test health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'

def test_upload_questions(client):
    """Test question upload"""
    questions = [
        {
            "id": "test_q1",
            "content": "What is 2 + 2?",
            "options": ["3", "4", "5", "6"],
            "correct_answer": "4",
            "concepts": [1, 0, 0, 0, 0],
            "difficulty": 0.2
        }
    ]
    
    response = client.post('/api/questions/upload', 
                          data=json.dumps({'questions': questions}),
                          content_type='application/json')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'question_pool_id' in data

def test_start_test(client):
    """Test starting adaptive test"""
    # First upload questions
    questions = [
        {
            "id": "test_q1",
            "content": "What is 2 + 2?",
            "options": ["3", "4", "5", "6"],
            "correct_answer": "4",
            "concepts": [1, 0, 0, 0, 0],
            "difficulty": 0.2
        }
    ]
    
    upload_response = client.post('/api/questions/upload',
                                 data=json.dumps({'questions': questions}),
                                 content_type='application/json')
    
    upload_data = json.loads(upload_response.data)
    pool_id = upload_data['question_pool_id']
    
    # Start test
    test_data = {
        'student_id': 'test_student_123',
        'question_pool_id': pool_id,
        'concept_names': ['Math', 'Algebra', 'Geometry', 'Statistics', 'Calculus']
    }
    
    response = client.post('/api/test/start',
                          data=json.dumps(test_data),
                          content_type='application/json')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'session_id' in data
    assert 'next_question' in data
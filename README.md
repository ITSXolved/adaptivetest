
A comprehensive adaptive testing system using Flask, Supabase, Redis, and Docker with persistent student proficiency tracking.

## Features

- **Question Upload**: Upload questions in JSON format
- **Adaptive Testing**: Uses multidimensional IRT with Q-matrix
- **Student Proficiency Tracking**: Persistent storage of student progress in Supabase
- **Multiple End Criteria**: Fixed length, precision-based, classification-based
- **Session Management**: Redis-based session storage
- **Progress Analytics**: Track learning progress over time
- **Supabase Integration**: Cloud database for persistent data
- **Docker Support**: Easy deployment with docker-compose

## Supabase Database Schema

You need to create these tables in your Supabase database:

### 1. Students Table
```sql
CREATE TABLE students (
  id TEXT PRIMARY KEY,
  name TEXT,
  email TEXT,
  grade_level TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2. Student Proficiencies Table
```sql
CREATE TABLE student_proficiencies (
  id SERIAL PRIMARY KEY,
  student_id TEXT REFERENCES students(id) ON DELETE CASCADE,
  concept_name TEXT NOT NULL,
  proficiency_value FLOAT NOT NULL,
  confidence FLOAT DEFAULT 0.5,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3. Test Sessions Table
```sql
CREATE TABLE test_sessions (
  id TEXT PRIMARY KEY,
  student_id TEXT REFERENCES students(id) ON DELETE CASCADE,
  initial_proficiency JSONB,
  final_proficiency JSONB,
  total_questions INTEGER DEFAULT 0,
  correct_responses INTEGER DEFAULT 0,
  accuracy FLOAT,
  learning_gain FLOAT,
  test_efficiency FLOAT,
  status TEXT DEFAULT 'active',
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);
```

### 4. Test Responses Table
```sql
CREATE TABLE test_responses (
  id SERIAL PRIMARY KEY,
  student_id TEXT REFERENCES students(id) ON DELETE CASCADE,
  session_id TEXT REFERENCES test_sessions(id) ON DELETE CASCADE,
  question_id TEXT NOT NULL,
  response INTEGER NOT NULL,
  is_correct INTEGER NOT NULL,
  response_time_ms INTEGER,
  proficiency_before JSONB,
  proficiency_after JSONB,
  question_difficulty FLOAT,
  question_concepts JSONB,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);
```

## Quick Start

1. **Setup Supabase:**
   - Create a new project at [supabase.com](https://supabase.com)
   - Run the SQL commands above to create tables
   - Get your Project URL and API keys

2. **Environment Setup:**
   Create a `.env` file:
   ```bash
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_ANON_KEY=your-anon-key
   SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
   ```

3. **Run with Docker:**
   ```bash
   git clone <repository>
   cd adaptive-test
   docker-compose up --build
   ```

4. **Upload questions:**
   ```bash
   curl -X POST http://localhost:5000/api/questions/upload \
     -H "Content-Type: application/json" \
     -d '{
       "questions": [
         {
           "id": "q1",
           "content": "What is 2 + 2?",
           "options": ["3", "4", "5", "6"],
           "correct_answer": "4",
           "concepts": [1, 0, 0, 0, 0],
           "difficulty": 0.2,
           "discrimination": 1.0
         }
       ]
     }'
   ```

5. **Start test:**
   ```bash
   curl -X POST http://localhost:5000/api/test/start \
     -H "Content-Type: application/json" \
     -d '{
       "student_id": "student_123",
       "question_pool_id": "<pool_id_from_upload>",
       "concept_names": ["Math", "Algebra", "Geometry", "Statistics", "Calculus"],
       "end_criteria": {
         "type": "fixed_length",
         "max_questions": 10,
         "min_questions": 3
       }
     }'
   ```

6. **Submit responses:**
   ```bash
   curl -X POST http://localhost:5000/api/test/submit \
     -H "Content-Type: application/json" \
     -d '{
       "session_id": "<session_id>",
       "question_id": "q1",
       "response": 1
     }'
   ```

7. **Get student proficiency:**
   ```bash
   curl http://localhost:5000/api/student/student_123/proficiency
   ```

8. **Get learning progress:**
   ```bash
   curl http://localhost:5000/api/student/student_123/progress
   ```

## Question Format

```json
{
  "id": "unique_question_id",
  "content": "Question text",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "correct_answer": "Option B",
  "concepts": [1, 0, 1, 0, 0],  // Q-matrix row
  "difficulty": 0.5,            // Optional: -3.0 to 3.0
  "discrimination": 1.2         // Optional: > 0
}
```

## End Criteria Types

- **fixed_length**: Stop after max_questions
- **precision**: Stop when proficiency precision threshold reached
- **classification**: Stop when classification confidence reached

## API Endpoints

### Testing Endpoints
- `GET /health` - Health check
- `POST /api/questions/upload` - Upload questions
- `POST /api/test/start` - Start adaptive test
- `POST /api/test/submit` - Submit response
- `GET /api/test/status/<session_id>` - Get test status
- `POST /api/test/end/<session_id>` - End test manually

### Student Management Endpoints
- `GET /api/student/<student_id>/proficiency` - Get current proficiency
- `GET /api/student/<student_id>/history` - Get test history
- `GET /api/student/<student_id>/progress` - Get learning progress over time

## Student Proficiency Response Format

```json
{
  "student_id": "student_123",
  "proficiency": [0.8, 0.6, 0.4, 0.7, 0.5],
  "concept_names": ["Math", "Algebra", "Geometry", "Statistics", "Calculus"],
  "last_updated": "2023-12-01T10:30:00"
}
```

## Learning Progress Response Format

```json
{
  "student_id": "student_123",
  "progress_data": {
    "progress_timeline": [
      {
        "date": "2023-12-01T10:00:00",
        "proficiency": [0.5, 0.5, 0.5, 0.5, 0.5],
        "accuracy": 0.6,
        "questions_answered": 10
      }
    ],
    "concept_progress": {
      "Math": {
        "timeline": [{"date": "2023-12-01", "value": 0.8}],
        "improvement": 0.3,
        "current_level": 0.8
      }
    },
    "total_sessions": 5,
    "avg_accuracy": 0.75
  }
}
```

## Configuration

Environment variables:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_HOST` - Redis hostname (default: localhost)
- `REDIS_PORT` - Redis port (default: 6379)
- `DEBUG` - Enable debug mode (default: false)
- `SESSION_TIMEOUT` - Session timeout in seconds (default: 3600)

## Database Setup

The system uses PostgreSQL for persistent storage and automatically creates tables on startup. In production, set the `DATABASE_URL` environment variable:

```bash
DATABASE_URL=postgresql://username:password@host:port/database_name
```

## Testing

```bash
pip install pytest
pytest tests/
```

## Environment Variables

Create a `.env` file in the project root:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here

# Redis Configuration (optional for local development)
REDIS_HOST=localhost
REDIS_PORT=6379

# Flask Configuration
DEBUG=true
SECRET_KEY=your-secret-key-for-production
```

## Supabase Setup Guide

1. **Create Supabase Project:**
   - Visit [supabase.com](https://supabase.com)
   - Create new project
   - Note your Project URL and API keys

2. **Create Database Tables:**
   - Go to SQL Editor in Supabase dashboard
   - Run the SQL commands provided in the schema section above

3. **Configure Row Level Security (Optional):**
   ```sql
   -- Enable RLS on tables
   ALTER TABLE students ENABLE ROW LEVEL SECURITY;
   ALTER TABLE student_proficiencies ENABLE ROW LEVEL SECURITY;
   ALTER TABLE test_sessions ENABLE ROW LEVEL SECURITY;
   ALTER TABLE test_responses ENABLE ROW LEVEL SECURITY;
   
   -- Add policies as needed for your use case
   ```

4. **Get API Keys:**
   - Go to Settings > API
   - Copy the Project URL and anon/service_role keys
   - Add them to your `.env` file

## Development

For local development without Docker:

1. Install PostgreSQL and Redis
2. Create a database: `createdb adaptive_test`
3. Set environment variables:
   ```bash
   export DATABASE_URL=postgresql://localhost/adaptive_test
   export REDIS_HOST=localhost
   ```
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python app/main.py`

## Complete Workflow Example

Here's a complete example showing how student proficiency is tracked:

```bash
# 1. Upload questions
curl -X POST http://localhost:5000/api/questions/upload \
  -H "Content-Type: application/json" \
  -d '{
    "questions": [
      {
        "id": "math_q1",
        "content": "What is 15 + 27?",
        "options": ["40", "42", "44", "46"],
        "correct_answer": "42",
        "concepts": [1, 0, 0, 0, 0],
        "difficulty": 0.3,
        "discrimination": 1.2
      },
      {
        "id": "algebra_q1", 
        "content": "Solve: 2x + 5 = 15",
        "options": ["3", "5", "7", "10"],
        "correct_answer": "5",
        "concepts": [1, 1, 0, 0, 0],
        "difficulty": 0.6,
        "discrimination": 1.5
      }
    ]
  }'

# Response: {"question_pool_id": "abc-123", "count": 2}

# 2. Start test for new student
curl -X POST http://localhost:5000/api/test/start \
  -H "Content-Type: application/json" \
  -d '{
    "student_id": "alice_2024",
    "question_pool_id": "abc-123",
    "concept_names": ["Math", "Algebra", "Geometry", "Statistics", "Calculus"],
    "end_criteria": {"type": "fixed_length", "max_questions": 5}
  }'

# Response: {
#   "session_id": "session-456",
#   "initial_proficiency": [0.5, 0.5, 0.5, 0.5, 0.5],
#   "next_question": {"id": "math_q1", "content": "What is 15 + 27?", ...}
# }

# 3. Submit response (correct answer)
curl -X POST http://localhost:5000/api/test/submit \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-456",
    "question_id": "math_q1", 
    "response": 1
  }'

# Response: {
#   "status": "continue",
#   "current_proficiency": [0.65, 0.52, 0.5, 0.5, 0.5],  // Math improved!
#   "next_question": {"id": "algebra_q1", ...}
# }

# 4. Check student's current proficiency
curl http://localhost:5000/api/student/alice_2024/proficiency

# Response: {
#   "student_id": "alice_2024",
#   "proficiency": [0.65, 0.52, 0.5, 0.5, 0.5],
#   "concept_names": ["Math", "Algebra", "Geometry", "Statistics", "Calculus"],
#   "last_updated": "2023-12-01T10:15:30"
# }

# 5. Later, start another test session - proficiency persists!
curl -X POST http://localhost:5000/api/test/start \
  -H "Content-Type: application/json" \
  -d '{
    "student_id": "alice_2024",
    "question_pool_id": "abc-123",
    "concept_names": ["Math", "Algebra", "Geometry", "Statistics", "Calculus"]
  }'

# Response: {
#   "initial_proficiency": [0.65, 0.52, 0.5, 0.5, 0.5],  // Starts from previous level!
#   ...
# }

# 6. View learning progress over time
curl http://localhost:5000/api/student/alice_2024/progress

# Response: Shows improvement across multiple test sessions
```

## Key Benefits

✅ **Persistent Learning**: Student proficiency is saved and continues between sessions  
✅ **Concept Tracking**: Individual tracking for Math, Algebra, Geometry, etc.  
✅ **Progress Analytics**: View learning improvement over time  
✅ **Adaptive Selection**: Questions chosen based on current skill level  
✅ **Database Storage**: All data persisted in PostgreSQL  
✅ **Session Management**: Temporary test state in Redis for performance
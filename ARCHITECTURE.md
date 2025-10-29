# 🎯 Minimal Redis Approach - Architecture Guide

## Overview
This architecture stores only hot, frequently-accessed data in Redis, while keeping everything else in the database (Supabase).

---

## 📊 Data Split Strategy

### Redis: Hot Data (Fast Access Required)

| Data Type | Key Format | TTL | Purpose |
|-----------|-----------|-----|---------|
| **Active Session State** | `session:{session_id}:state` | 30 min | Current proficiency, status, next question ID |
| **Submission Lock** | `lock:{session_id}:{question_id}` | 5 sec | Prevent double-submission |
| **Question Cache** | `question:{question_id}` | 1 hour | Frequently accessed questions |

**Example Redis Data Structure:**
```json
// session:{session_id}:state
{
  "student_id": "student_123",
  "current_proficiency": [0.6, 0.5, 0.7, 0.4, 0.8],
  "next_question_id": "q42",
  "status": "active",
  "questions_answered": 5,
  "last_activity": "2025-01-15T10:30:00"
}
```

### Database (Supabase): Cold Data (Permanent Record)

| Table | Purpose | Accessed When |
|-------|---------|---------------|
| **test_sessions** | Session metadata | Start, end, history queries |
| **test_responses** | All student answers | After each submission, analytics |
| **questions** | Question pool | Test start, admin upload |
| **student_proficiencies** | Long-term proficiency | Profile view, test start |
| **students** | Student profiles | Login, registration |

---

## 🔄 Data Flow

### 1. Start Test
```
Frontend → POST /api/test/start
  ↓
Database: Create session record, fetch questions
  ↓
Redis: Store active state (proficiency, status)
  ↓
Response: { session_id, next_question }
```

### 2. Submit Answer
```
Frontend → POST /api/test/submit
  ↓
Redis: Check submission lock
  ↓
Redis: Get current proficiency
  ↓
Compute: Update proficiency (adaptive engine)
  ↓
Database: Store response permanently
  ↓
Redis: Update proficiency in cache
  ↓
Response: { next_question, updated_proficiency }
```

### 3. End Test
```
Frontend → POST /api/test/end
  ↓
Redis: Get final state
  ↓
Database: Update session with final results
  ↓
Database: Update student long-term proficiency
  ↓
Redis: Delete session state (cleanup)
  ↓
Response: { final_proficiency, summary }
```

---

## 💾 Database Schema

### test_sessions
```sql
CREATE TABLE test_sessions (
  id UUID PRIMARY KEY,
  student_id VARCHAR NOT NULL,
  question_pool_id UUID,
  status VARCHAR DEFAULT 'active',
  initial_proficiency JSONB,
  final_proficiency JSONB,
  total_questions INT DEFAULT 0,
  correct_responses INT DEFAULT 0,
  accuracy DECIMAL,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  last_activity TIMESTAMP
);
```

### questions
```sql
CREATE TABLE questions (
  id VARCHAR PRIMARY KEY,
  pool_id UUID NOT NULL,
  content TEXT NOT NULL,
  options JSONB NOT NULL,
  correct_answer VARCHAR NOT NULL,
  concepts JSONB NOT NULL,
  difficulty DECIMAL,
  discrimination DECIMAL,
  created_at TIMESTAMP
);
```

### test_responses
```sql
CREATE TABLE test_responses (
  id UUID PRIMARY KEY,
  student_id VARCHAR NOT NULL,
  session_id UUID NOT NULL,
  question_id VARCHAR NOT NULL,
  response INT NOT NULL,
  is_correct BOOLEAN,
  proficiency_before JSONB,
  proficiency_after JSONB,
  timestamp TIMESTAMP
);
```

---

## 🚀 Benefits

### Performance
- ✅ **Fast reads**: Active session data in Redis (sub-ms latency)
- ✅ **Reduced DB load**: Only write operations hit database
- ✅ **Scalable**: Redis handles 100k+ ops/sec

### Cost
- ✅ **Minimal Redis usage**: Only active sessions (~1-5KB each)
- ✅ **Lower memory**: 1000 active sessions ≈ 5MB Redis
- ✅ **Auto cleanup**: 30-min TTL removes inactive sessions

### Reliability
- ✅ **Data persistence**: All important data in database
- ✅ **Session recovery**: Can rebuild from database if Redis fails
- ✅ **Audit trail**: Complete response history preserved

---

## 🔧 Implementation Guidelines

### When to Use Redis
```python
# ✅ Good: Frequently accessed, temporary data
redis_service.get_session_state(session_id)
redis_service.update_proficiency(session_id, new_values)

# ❌ Bad: Permanent data, infrequent access
redis_service.store_student_profile(student_id, profile)  # Use DB instead
```

### When to Use Database
```python
# ✅ Good: Permanent records, analytics, history
supabase_service.store_response(student_id, response_data)
supabase_service.get_test_history(student_id)

# ❌ Bad: Real-time session state during active test
supabase_service.update_proficiency_every_question()  # Too slow, use Redis
```

### Data Synchronization Pattern
```python
def submit_answer(session_id, question_id, response):
    # 1. Get hot data from Redis
    state = redis_service.get_session_state(session_id)

    # 2. Process update
    new_proficiency = adaptive_engine.update(state['proficiency'], response)

    # 3. Update Redis (fast, temporary)
    redis_service.update_session_state(session_id, {
        'current_proficiency': new_proficiency,
        'questions_answered': state['questions_answered'] + 1
    })

    # 4. Store in Database (permanent record)
    supabase_service.store_response(student_id, session_id, {
        'question_id': question_id,
        'response': response,
        'proficiency_after': new_proficiency
    })
```

---

## 🎯 Migration Checklist

- [ ] Create database tables for questions and sessions
- [ ] Refactor `redis_service.py` to only handle hot data
- [ ] Update `supabase_service.py` with question storage methods
- [ ] Modify `/api/test/start` to fetch questions from DB
- [ ] Add submission locking with Redis
- [ ] Update cleanup scheduler for minimal data
- [ ] Add session recovery mechanism
- [ ] Update tests to verify data split

---

## 📈 Expected Performance

| Metric | Before | After (Minimal Redis) |
|--------|--------|----------------------|
| Redis Memory (1000 sessions) | ~50MB | ~5MB |
| Session Start Latency | 50ms | 80ms (DB fetch) |
| Submit Answer Latency | 20ms | 25ms |
| Database Writes | Low | Medium |
| Data Durability | Risky | High |

---

## 🔒 Security Considerations

1. **Submission Prevention**: Redis locks prevent duplicate answers
2. **Session Hijacking**: Session state includes student_id validation
3. **Data Tampering**: All answers stored in DB (immutable audit trail)
4. **Question Leaking**: Don't cache correct answers in Redis

---

## 🛠️ Monitoring & Debugging

### Key Metrics to Track
```python
# Redis metrics
- Active sessions count: redis.dbsize()
- Memory usage: redis.info('memory')
- Hit/miss ratio for question cache

# Database metrics
- Average write latency (test_responses)
- Question pool size
- Session completion rate
```

### Debug Endpoints
```
GET /api/debug/session/{session_id}  # Show Redis + DB state
GET /api/debug/redis/stats            # Redis memory and keys
POST /api/debug/sync/{session_id}     # Force DB sync
```

---

## 📝 Notes

- **Cache Invalidation**: Question cache refreshes every 1 hour
- **Session Recovery**: If Redis fails, rebuild from last DB state
- **Cleanup Strategy**: 30-min inactivity = auto-delete from Redis
- **Scaling**: Consider Redis Cluster for >10K concurrent sessions

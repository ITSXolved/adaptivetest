import numpy as np
import logging
from typing import Dict, List, Optional
from scipy.special import expit

logger = logging.getLogger(__name__)

class AdaptiveEngine:
    """Adaptive testing engine using IRT and Q-matrix"""
    
    def __init__(self, learning_rate: float = 0.1):
        self.learning_rate = learning_rate
    
    def select_next_question(self, questions: List[Dict], q_matrix: Dict, 
                           proficiency: List[float], responses: List[Dict]) -> Dict:
        """Select next most informative question"""
        try:
            used_questions = {r['question_id'] for r in responses}
            available_questions = [q for q in questions if q['id'] not in used_questions]
            
            if not available_questions:
                return {}
            
            # Calculate information for each available question
            max_info = -1
            best_question = available_questions[0]
            
            for question in available_questions:
                info = self._calculate_information(question, proficiency, q_matrix)
                if info > max_info:
                    max_info = info
                    best_question = question
            
            return best_question
            
        except Exception as e:
            logger.error(f"Error selecting next question: {str(e)}")
            return questions[0] if questions else {}
    
    def update_ability(self, current_proficiency: List[float], question: Dict, 
                      response: int, q_matrix: Dict) -> List[float]:
        """Update proficiency estimate based on response"""
        try:
            proficiency = np.array(current_proficiency)
            question_id = question['id']
            
            # Get Q-matrix row for this question
            q_vector = np.array(q_matrix.get(question_id, [1] * len(proficiency)))
            
            # Calculate current probability
            prob = self._calculate_probability(proficiency, question, q_matrix)
            
            # Calculate error
            error = response - prob
            
            # Update proficiency using gradient ascent
            discrimination = question.get('discrimination', 1.0)
            gradient = error * prob * (1 - prob) * discrimination * q_vector
            
            new_proficiency = proficiency + self.learning_rate * gradient
            
            # Keep proficiency in reasonable bounds
            new_proficiency = np.clip(new_proficiency, -3.0, 3.0)
            
            return new_proficiency.tolist()
            
        except Exception as e:
            logger.error(f"Error updating proficiency: {str(e)}")
            return current_proficiency
    
    def should_continue(self, responses: List[Dict], proficiency: List[float], 
                       end_criteria: Dict) -> bool:
        """Determine if test should continue based on end criteria"""
        try:
            num_responses = len(responses)
            criteria_type = end_criteria.get('type', 'fixed_length')
            
            # Check minimum questions
            min_questions = end_criteria.get('min_questions', 5)
            if num_responses < min_questions:
                return True
            
            # Check maximum questions
            max_questions = end_criteria.get('max_questions', 20)
            if num_responses >= max_questions:
                return False
            
            if criteria_type == 'fixed_length':
                return num_responses < max_questions
            
            elif criteria_type == 'precision':
                # Stop when precision threshold is reached
                precision_threshold = end_criteria.get('precision_threshold', 0.3)
                current_precision = self._estimate_precision(responses, proficiency)
                return current_precision > precision_threshold
            
            elif criteria_type == 'classification':
                # Stop when confident about classification
                classification_threshold = end_criteria.get('classification_threshold', 0.8)
                confidence = self._estimate_classification_confidence(proficiency)
                return confidence < classification_threshold
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking end criteria: {str(e)}")
            return False
    
    def generate_summary(self, session_data: Dict) -> Dict:
        """Generate test summary"""
        try:
            responses = session_data.get('responses', [])
            final_proficiency = session_data.get('current_proficiency', [])
            initial_proficiency = session_data.get('initial_proficiency', [])
            
            total_questions = len(responses)
            correct_responses = sum(1 for r in responses if r['response'] == 1)
            accuracy = correct_responses / total_questions if total_questions > 0 else 0
            
            # Calculate proficiency change
            proficiency_change = np.array(final_proficiency) - np.array(initial_proficiency)
            learning_gain = float(np.mean(np.abs(proficiency_change)))
            
            return {
                'total_questions': total_questions,
                'correct_responses': correct_responses,
                'accuracy': accuracy,
                'initial_proficiency': initial_proficiency,
                'final_proficiency': final_proficiency,
                'proficiency_change': proficiency_change.tolist(),
                'learning_gain': learning_gain,
                'test_efficiency': self._calculate_efficiency(responses)
            }
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            return {'error': 'Failed to generate summary'}
    
    def _calculate_information(self, question: Dict, proficiency: List[float], 
                             q_matrix: Dict) -> float:
        """Calculate Fisher information for question"""
        try:
            prob = self._calculate_probability(proficiency, question, q_matrix)
            discrimination = question.get('discrimination', 1.0)
            
            # Fisher information
            info = discrimination ** 2 * prob * (1 - prob)
            
            return info
            
        except Exception:
            return 0.0
    
    def _calculate_probability(self, proficiency: List[float], question: Dict, 
                             q_matrix: Dict) -> float:
        """Calculate probability of correct response using multidimensional IRT"""
        try:
            proficiency_array = np.array(proficiency)
            question_id = question['id']
            
            # Get Q-matrix row
            q_vector = np.array(q_matrix.get(question_id, [1] * len(proficiency)))
            
            # Calculate linear combination
            discrimination = question.get('discrimination', 1.0)
            difficulty = question.get('difficulty', 0.0)
            
            linear_term = discrimination * np.dot(q_vector, proficiency_array) - difficulty
            
            # Apply logistic function
            prob = expit(linear_term)
            
            return float(np.clip(prob, 0.01, 0.99))
            
        except Exception:
            return 0.5
    
    def _estimate_precision(self, responses: List[Dict], proficiency: List[float]) -> float:
        """Estimate current precision of proficiency estimate"""
        if len(responses) < 2:
            return 1.0  # Low precision with few responses
        
        # Simple precision estimate based on recent stability
        recent_proficiencies = [r['proficiency_after'] for r in responses[-5:]]
        if len(recent_proficiencies) < 2:
            return 1.0
        
        # Calculate variance in recent proficiency estimates
        variances = []
        for i in range(len(proficiency)):
            concept_proficiencies = [p[i] for p in recent_proficiencies]
            if len(concept_proficiencies) > 1:
                variances.append(np.var(concept_proficiencies))
        
        avg_variance = np.mean(variances) if variances else 1.0
        precision = 1.0 / (1.0 + avg_variance)
        
        return precision
    
    def _estimate_classification_confidence(self, proficiency: List[float]) -> float:
        """Estimate confidence in proficiency classification"""
        # Simple confidence based on distance from neutral (0.0)
        distances = [abs(p) for p in proficiency]
        avg_distance = np.mean(distances)
        confidence = min(avg_distance / 2.0, 1.0)  # Normalize to [0, 1]
        
        return confidence
    
    def _calculate_efficiency(self, responses: List[Dict]) -> float:
        """Calculate test efficiency metric"""
        if not responses:
            return 0.0
        
        # Simple efficiency: information gained per question
        total_questions = len(responses)
        
        # Estimate total information (simplified)
        proficiency_changes = []
        for response in responses:
            before = response.get('proficiency_before', [])
            after = response.get('proficiency_after', [])
            if before and after:
                change = np.linalg.norm(np.array(after) - np.array(before))
                proficiency_changes.append(change)
        
        avg_change = np.mean(proficiency_changes) if proficiency_changes else 0.0
        efficiency = avg_change / total_questions if total_questions > 0 else 0.0
        
        return float(efficiency)


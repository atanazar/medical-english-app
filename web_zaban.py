import streamlit as st
import random
from google import genai
from pydantic import BaseModel, Field

# ==========================================
# 1. SETUP & SECRETS
# ==========================================
# Pull the API key from Streamlit's secure vault
API_KEY = st.secrets["GEMINI_API_KEY"]

st.set_page_config(page_title="Medical English Mastery", page_icon="⚕️", layout="centered")

class Question(BaseModel):
    question_text: str = Field(description="The question text. Use HTML <u> tags for target words.")
    option_A: str
    option_B: str
    option_C: str
    option_D: str
    correct_answer: str = Field(description="A, B, C, or D")
    explanation: str = Field(description="Explain the correct answer and all distractors.")

class QuizBatch(BaseModel):
    questions: list[Question]

# ==========================================
# 2. SESSION STATE
# ==========================================
if 'questions' not in st.session_state:
    st.session_state.questions = []
if 'current_q' not in st.session_state:
    st.session_state.current_q = 0
if 'score' not in st.session_state:
    st.session_state.score = 0
if 'answered' not in st.session_state:
    st.session_state.answered = False

# ==========================================
# 3. AI GENERATION FUNCTION
# ==========================================
def generate_batch(category):
    # Pass the secure API key to the client
    client = genai.Client(api_key=API_KEY)
    seed = random.randint(1000, 9999)
    
    prompt = f"""
    Generate 20 advanced multiple-choice questions testing English {category}. 
    Focus on B2, C1, C2 CEFR levels (TOEFL/IELTS). Context: GENERAL medical/healthcare.
    ID: {seed}. Do not repeat previous questions. 
    Format: Use <u> tags for target words. If synonym/antonym, explicitly ask for it at the end.
    Explain the correct answer AND explicitly explain why all three incorrect options are wrong.
    """
    
    with st.spinner(f"Crafting your 20 {category} questions... Please wait."):
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": QuizBatch,
                "temperature": 1.3,
            },
        )
        data = QuizBatch.model_validate_json(response.text)
        st.session_state.questions = data.questions
        st.session_state.current_q = 0
        st.session_state.score = 0
        st.session_state.answered = False

# ==========================================
# 4. USER INTERFACE
# ==========================================
st.title("⚕️ Medical English Mastery")

if not st.session_state.questions:
    st.write("Generate your daily 20-question batch to start studying.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Generate Vocabulary Quiz", use_container_width=True):
            generate_batch("vocabulary")
            st.rerun()
    with col2:
        if st.button("Generate Grammar Quiz", use_container_width=True):
            generate_batch("grammar")
            st.rerun()

else:
    q_idx = st.session_state.current_q
    
    if q_idx >= len(st.session_state.questions):
        st.success(f"🎉 Batch Complete! Your Score: {st.session_state.score} / 20")
        if st.button("Start a New Batch"):
            st.session_state.questions = []
            st.rerun()
            
    else:
        q = st.session_state.questions[q_idx]
        st.caption(f"Question {q_idx + 1} of 20 | Score: {st.session_state.score}")
        st.markdown(f"### {q.question_text}", unsafe_allow_html=True)
        
        options = [f"A) {q.option_A}", f"B) {q.option_B}", f"C) {q.option_C}", f"D) {q.option_D}"]
        choice = st.radio("Select your answer:", options, index=None, disabled=st.session_state.answered)
        
        if not st.session_state.answered:
            if st.button("Submit Answer", type="primary"):
                if choice:
                    st.session_state.answered = True
                    if choice.startswith(q.correct_answer):
                        st.session_state.score += 1
                    st.rerun()
                else:
                    st.warning("Please select an answer first!")
                    
        if st.session_state.answered:
            if choice.startswith(q.correct_answer):
                st.success("✅ Correct!")
            else:
                st.error(f"❌ Incorrect. The correct answer was **{q.correct_answer}**.")
                
            st.info(f"**Explanation:**\n\n{q.explanation}")
            
            if st.button("Next Question ➔"):
                st.session_state.current_q += 1
                st.session_state.answered = False
                st.rerun()

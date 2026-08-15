import streamlit as st
import sqlite3
import random
import re
from google import genai
from pydantic import BaseModel, Field

# ==========================================
# 1. SETUP & SECRETS
# ==========================================
st.set_page_config(page_title="Medical English Mastery", page_icon="⚕️", layout="wide")

# Retrieve API key from Streamlit Secrets
if "GEMINI_API_KEY" in st.secrets:
    API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    st.error("API Key not found! Please set GEMINI_API_KEY in Streamlit Advanced Settings -> Secrets.")
    st.stop()

class Question(BaseModel):
    question_text: str = Field(description="The question text. Use HTML <u> tags for target words.")
    option_A: str
    option_B: str
    option_C: str
    option_D: str
    correct_answer: str = Field(description="A, B, C, or D")
    explanation: str = Field(description="Detailed explanation of the answer and all distractors.")

class QuizBatch(BaseModel):
    questions: list[Question]

# ==========================================
# 2. DATABASE MANAGER
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("web_quiz_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            question_text TEXT,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            correct_answer TEXT,
            user_answer TEXT,
            explanation TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    return conn

db_conn = get_db_connection()

def save_to_history(category, q, user_ans, status):
    cursor = db_conn.cursor()
    cursor.execute('''
        INSERT INTO history (category, question_text, option_a, option_b, option_c, option_d, correct_answer, user_answer, explanation, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (category, q.question_text, q.option_A, q.option_B, q.option_C, q.option_D, q.correct_answer, user_ans, q.explanation, status))
    db_conn.commit()

def fetch_history(category):
    cursor = db_conn.cursor()
    cursor.execute('''
        SELECT id, status, question_text, correct_answer, user_answer, explanation, option_a, option_b, option_c, option_d
        FROM history WHERE category = ? ORDER BY id DESC
    ''', (category,))
    return cursor.fetchall()

# ==========================================
# 3. SESSION STATE INITIALIZATION
# ==========================================
for cat in ["Vocabulary", "Grammar"]:
    if f"{cat}_questions" not in st.session_state:
        st.session_state[f"{cat}_questions"] = []
    if f"{cat}_current_q" not in st.session_state:
        st.session_state[f"{cat}_current_q"] = 0
    if f"{cat}_score" not in st.session_state:
        st.session_state[f"{cat}_score"] = 0
    if f"{cat}_states" not in st.session_state:
        st.session_state[f"{cat}_states"] = []

# ==========================================
# 4. ROBUST AI GENERATION WITH FALLBACK
# ==========================================
def generate_batch(category, prompt_text):
    client = genai.Client(api_key=API_KEY)
    seed = random.randint(1000, 9999)
    
    full_prompt = (
        prompt_text + 
        f"\n\nRequest ID #{seed}. Do NOT repeat previously used questions. Select diverse advanced items."
    )
    
    # List of models to try in order of preference
    models_to_try = ['gemini-3.5-flash', 'gemini-2.5-flash', 'gemini-flash-latest']
    
    with st.spinner(f"Crafting your 20 {category} questions..."):
        success = False
        last_err = ""
        
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=full_prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": QuizBatch,
                        "temperature": 1.3,
                    },
                )
                data = QuizBatch.model_validate_json(response.text)
                st.session_state[f"{category}_questions"] = data.questions
                st.session_state[f"{category}_current_q"] = 0
                st.session_state[f"{category}_score"] = 0
                st.session_state[f"{category}_states"] = [
                    {'answered': False, 'user_ans': '', 'status': ''} for _ in data.questions
                ]
                success = True
                break
            except Exception as e:
                last_err = str(e)
                continue
                
        if not success:
            st.error(f"Generation failed due to high server traffic. Please retry in 30 seconds.\nDetails: {last_err}")

# ==========================================
# 5. UI COMPONENTS: QUIZ TAB & HISTORY TAB
# ==========================================
def render_quiz_tab(category, base_prompt):
    st.subheader(f"{category} Quiz")
    
    questions = st.session_state[f"{category}_questions"]
    current_idx = st.session_state[f"{category}_current_q"]
    
    if not questions:
        st.write(f"Generate your daily batch of 20 {category.lower()} questions.")
        if st.button(f"Generate 20 {category} Questions", type="primary", use_container_width=True):
            generate_batch(category, base_prompt)
            st.rerun()
        return

    # Check if batch completed
    if current_idx >= len(questions):
        score = st.session_state[f"{category}_score"]
        pct = (score / len(questions)) * 100
        st.success(f"🎉 Batch Finished! Final Score: **{score} / {len(questions)} ({pct:.1f}%)**")
        st.info("Check the History tab to review all questions and explanations.")
        if st.button(f"Start New {category} Batch", type="primary"):
            st.session_state[f"{category}_questions"] = []
            st.rerun()
        return

    q = questions[current_idx]
    state = st.session_state[f"{category}_states"][current_idx]
    
    st.progress((current_idx + 1) / len(questions))
    st.caption(f"Question {current_idx + 1} of {len(questions)} | Score: {st.session_state[f'{category}_score']}")
    
    # Display Question
    st.markdown(f"#### {q.question_text}", unsafe_allow_html=True)
    
    options = [f"A) {q.option_A}", f"B) {q.option_B}", f"C) {q.option_C}", f"D) {q.option_D}"]
    
    # If already answered, lock the choice
    default_index = None
    if state['answered'] and state['user_ans'] in ["A", "B", "C", "D"]:
        default_index = ["A", "B", "C", "D"].index(state['user_ans'])
        
    choice = st.radio(
        "Choose the correct option:",
        options,
        index=default_index,
        disabled=state['answered'],
        key=f"{category}_radio_{current_idx}"
    )
    
    col_btn1, col_btn2 = st.columns([1, 1])
    
    if not state['answered']:
        with col_btn1:
            if st.button("Submit Answer", type="primary", use_container_width=True):
                if choice:
                    user_letter = choice[0]
                    is_correct = (user_letter == q.correct_answer)
                    status = "Correct" if is_correct else "Incorrect"
                    if is_correct:
                        st.session_state[f"{category}_score"] += 1
                        
                    st.session_state[f"{category}_states"][current_idx] = {
                        'answered': True,
                        'user_ans': user_letter,
                        'status': status
                    }
                    save_to_history(category, q, user_letter, status)
                    st.rerun()
                else:
                    st.warning("Please select an option first!")
        with col_btn2:
            if st.button("Skip", use_container_width=True):
                st.session_state[f"{category}_states"][current_idx] = {
                    'answered': True,
                    'user_ans': 'Skipped',
                    'status': 'Not Answered'
                }
                save_to_history(category, q, "Skipped", "Not Answered")
                st.rerun()
                
    else:
        # Display Result & Explanation
        if state['status'] == "Correct":
            st.success("✅ **Correct!**")
        elif state['status'] == "Incorrect":
            st.error(f"❌ **Incorrect.** Correct answer is **{q.correct_answer}**.")
        else:
            st.warning(f"⚠️ **Skipped.** Correct answer is **{q.correct_answer}**.")
            
        st.markdown(f"**Explanation:**\n\n{q.explanation}", unsafe_allow_html=True)
        
        # Navigation Buttons
        col_nav1, col_nav2 = st.columns([1, 1])
        with col_nav1:
            if current_idx > 0:
                if st.button("⬅ Previous", use_container_width=True):
                    st.session_state[f"{category}_current_q"] -= 1
                    st.rerun()
        with col_nav2:
            btn_label = "Finish Batch ➔" if current_idx == len(questions) - 1 else "Next Question ➔"
            if st.button(btn_label, type="primary", use_container_width=True):
                st.session_state[f"{category}_current_q"] += 1
                st.rerun()

def render_history_tab(category):
    st.subheader(f"{category} History & Review")
    records = fetch_history(category)
    
    if not records:
        st.info(f"No {category.lower()} history recorded yet. Complete a quiz to view past questions!")
        return

    st.caption(f"Total questions recorded: {len(records)}")
    
    for row in records:
        q_id, status, q_text, correct, user_ans, expl, opt_a, opt_b, opt_c, opt_d = row
        
        # Badge styling
        badge = "🟢 Correct" if status == "Correct" else ("🔴 Incorrect" if status == "Incorrect" else "🟠 Skipped")
        
        # Clean text snippet for expander header
        clean_header = re.sub(r'</?[biu]>', '', q_text)
        snippet = (clean_header[:70] + "...") if len(clean_header) > 70 else clean_header
        
        with st.expander(f"#{q_id} | {badge} | {snippet}"):
            st.markdown(f"**Question:**\n{q_text}", unsafe_allow_html=True)
            st.write(f"• A) {opt_a}\n• B) {opt_b}\n• C) {opt_c}\n• D) {opt_d}")
            st.write(f"**Your Answer:** `{user_ans}` | **Correct Answer:** `{correct}`")
            st.markdown(f"**Explanation:**\n\n{expl}", unsafe_allow_html=True)

# ==========================================
# 6. APP SHELL & NAVIGATION
# ==========================================
st.title("⚕️ Medical English Mastery")

vocab_prompt = (
    "Generate 20 advanced multiple-choice questions testing English vocabulary. "
    "CRITICAL INSTRUCTION: Randomize heavily from the '504 Absolutely Essential Words' and TOEFL/IELTS lists. "
    "CRITICAL FORMATTING INSTRUCTION: Provide a diverse mix of formats (fill-in-the-blanks with '______', synonym/antonym queries). "
    "Use HTML <u> tags for target words. If synonym/antonym, explicitly state the instruction at the end. "
    "Contextualize in broad healthcare, hospital, and patient care settings. "
    "CRITICAL EXPLANATION INSTRUCTION: Define the correct answer AND explicitly define/explain all three incorrect options."
)

grammar_prompt = (
    "Generate 20 advanced multiple-choice questions testing complex English grammar specifically "
    "at B2, C1, and C2 CEFR levels (TOEFL/IELTS). "
    "CRITICAL FORMATTING INSTRUCTION: Provide fill-in-the-blanks and Error Identification questions. "
    "For error identification, underline 4 parts labeled A, B, C, D using HTML <u> tags. "
    "Explicitly state the question at the end. Contextualize in medical and healthcare scenarios. "
    "CRITICAL EXPLANATION INSTRUCTION: Explain why the correct option is right AND explain why each distractor is grammatically wrong."
)

tabs = st.tabs(["📖 Vocab Quiz", "✍️ Grammar Quiz", "📚 Vocab History", "🏛️ Grammar History"])

with tabs[0]:
    render_quiz_tab("Vocabulary", vocab_prompt)

with tabs[1]:
    render_quiz_tab("Grammar", grammar_prompt)

with tabs[2]:
    render_history_tab("Vocabulary")

with tabs[3]:
    render_history_tab("Grammar")

import streamlit as st
import requests
import json
import os
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    CouldNotRetrieveTranscript,
)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
import re
from dotenv import load_dotenv
import PyPDF2
from docx import Document

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI Quiz Generator from YouTube Videos",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #1f77b4;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 2rem;
    }
    .section-header {
        color: #2c3e50;
        font-size: 1.5rem;
        font-weight: bold;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid #3498db;
        padding-bottom: 0.5rem;
    }
    .question-box {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #3498db;
        margin-bottom: 0.5rem;
    }
    .flashcard {
        background-color: #e8f4fd;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #b3d9ff;
        margin-bottom: 0.5rem;
    }
    .correct-answer {
        background-color: #d4edda;
        color: #155724;
        padding: 0.5rem;
        border-radius: 5px;
        font-weight: bold;
    }
    .export-button {
        background-color: #28a745;
        color: white;
        padding: 0.5rem 1rem;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-size: 1rem;
    }
</style>
""", unsafe_allow_html=True)

def extract_video_id(url):
    """Extract YouTube video ID from various URL formats"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/watch\?.*v=([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def process_document(uploaded_file):
    """Process uploaded document and extract text"""
    try:
        file_type = uploaded_file.type
        
        if file_type == "application/pdf":
            # Process PDF
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text.strip(), None
            
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            # Process DOCX
            doc = Document(uploaded_file)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip(), None
            
        elif file_type == "text/plain":
            # Process TXT
            text = str(uploaded_file.read(), "utf-8")
            return text.strip(), None
            
        else:
            return None, f"Unsupported file type: {file_type}. Please upload PDF, DOCX, or TXT files."
            
    except Exception as e:
        return None, f"Error processing document: {str(e)}"

def get_transcript(video_id):
    """Fetch transcript from YouTube video with robust fallbacks and language handling"""
    try:
        # Use the API method that matches your installed version (1.2.2)
        transcript_list = YouTubeTranscriptApi().list(video_id).find_transcript(['en']).fetch()
        
        # Join pieces, skipping empty and noise tokens
        text_chunks = [
            e.text.strip()
            for e in transcript_list
            if hasattr(e, 'text') and e.text and e.text not in {"[Music]", "[Applause]", "[Laughter]"}
        ]
        transcript_text = " ".join(text_chunks)
        if not transcript_text:
            raise NoTranscriptFound("Transcript fetched but empty after cleaning.")

        return transcript_text, None

    except TranscriptsDisabled:
        return None, "Captions are disabled for this video."
    except VideoUnavailable:
        return None, "The video is unavailable."
    except NoTranscriptFound as e:
        return None, f"No transcript found: {str(e)}"
    except CouldNotRetrieveTranscript as e:
        return None, f"Could not retrieve transcript: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error while fetching transcript: {str(e)}"

def generate_quiz_with_deepseek(transcript_text):
    """Generate quiz using DeepSeek API"""
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        return None, "DeepSeek API key not found. Please set DEEPSEEK_API_KEY environment variable."
    
    url = "https://api.deepseek.com/v1/chat/completions"
    
    prompt = f"""You are a quiz generator for teachers.
Input: {transcript_text}
Task: Create 5 multiple-choice questions (4 options each, mark the correct answer).
Output in valid JSON format:
{{
  "quiz": [
    {{"question": "...", "options": ["A", "B", "C", "D"], "answer": "B"}}
  ]
}}"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    try:
        # Use timeout from config
        from config import API_TIMEOUT
        response = requests.post(url, headers=headers, json=data, timeout=API_TIMEOUT)
        response.raise_for_status()
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        # Try to extract JSON from the response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            parsed_result = json.loads(json_str)
            return parsed_result, None
        else:
            return None, "Failed to parse JSON response from API"
            
    except requests.exceptions.Timeout:
        return None, f"API request timed out after {API_TIMEOUT} seconds. Try with a shorter transcript or check your internet connection."
    except requests.exceptions.ConnectionError:
        return None, "Connection error. Please check your internet connection and try again."
    except requests.exceptions.RequestException as e:
        return None, f"API request failed: {str(e)}"
    except json.JSONDecodeError as e:
        return None, f"Failed to parse JSON: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error: {str(e)}"

def create_pdf_report(data, filename):
    """Create PDF report using reportlab"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1  # Center alignment
    )
    story.append(Paragraph("AI Quiz Generator Report", title_style))
    story.append(Spacer(1, 20))
    
    # Quiz
    story.append(Paragraph("Quiz Questions", styles['Heading2']))
    for i, question_data in enumerate(data['quiz'], 1):
        story.append(Paragraph(f"Question {i}: {question_data['question']}", styles['Normal']))
        for j, option in enumerate(['A', 'B', 'C', 'D']):
            option_text = f"{option}. {question_data['options'][j]}"
            if option == question_data['answer']:
                option_text += " (Correct Answer)"
            story.append(Paragraph(option_text, styles['Normal']))
        story.append(Spacer(1, 10))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def main():
    # Main header
    st.markdown('<h1 class="main-header">🎯 AI Quiz Generator</h1>', unsafe_allow_html=True)
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        st.info("Make sure to set your DEEPSEEK_API_KEY environment variable")
        
        # Add some helpful information
        st.markdown("### How to use:")
        st.markdown("**From YouTube Video:**")
        st.markdown("1. Choose 'YouTube Video' option")
        st.markdown("2. Paste a YouTube URL")
        st.markdown("3. Click 'Generate Quiz from Video'")
        
        st.markdown("**From Document:**")
        st.markdown("1. Choose 'Upload Document' option")
        st.markdown("2. Upload PDF, DOCX, or TXT file")
        st.markdown("3. Click 'Generate Quiz from Document'")
        
        st.markdown("**Export:**")
        st.markdown("4. Download quiz as JSON or PDF")
    
    # Main content area
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Input method selection
        input_method = st.radio(
            "Choose input method:",
            ["📺 YouTube Video", "📄 Upload Document"],
            horizontal=True
        )
        
        if input_method == "📺 YouTube Video":
            # YouTube URL input
            youtube_url = st.text_input(
                "📺 Enter YouTube URL:",
                placeholder="https://www.youtube.com/watch?v=...",
                help="Paste any YouTube video URL here"
            )
            
            # Generate button for YouTube
            if st.button("🚀 Generate Quiz from Video", type="primary", use_container_width=True):
                if not youtube_url:
                    st.error("Please enter a YouTube URL")
                else:
                    # Extract video ID
                    video_id = extract_video_id(youtube_url)
                    if not video_id:
                        st.error("Invalid YouTube URL. Please check the format.")
                    else:
                        # Show loading spinner
                        with st.spinner("🔄 Processing... This may take a few moments."):
                            # Get transcript
                            transcript, transcript_error = get_transcript(video_id)
                            
                            if transcript_error:
                                st.error(f"❌ Failed to get transcript: {transcript_error}")
                                st.info("💡 Tip: Make sure the video has captions/subtitles enabled")
                            else:
                                # Check transcript length to prevent timeout issues
                                transcript_length = len(transcript)
                                if transcript_length > 10000:  # More than 10k characters
                                    st.warning(f"⚠️ Long transcript detected ({transcript_length} characters). This may take longer to process.")
                                    st.info("💡 Consider using a shorter video for faster results.")
                                
                                st.success(f"✅ Transcript extracted successfully! ({transcript_length} characters)")
                                
                                # Generate quiz with progress indicator
                                with st.spinner("🧠 Generating quiz with AI... This may take up to 1 minute for long transcripts."):
                                    quiz_data, quiz_error = generate_quiz_with_deepseek(transcript)
                                
                                if quiz_error:
                                    st.error(f"❌ Failed to generate quiz: {quiz_error}")
                                else:
                                    st.success("🎉 Quiz generated successfully!")
                                    
                                    # Store data in session state for export
                                    st.session_state.quiz_data = quiz_data
                                    st.session_state.transcript = transcript
                                    
                                    # Display results
                                    display_results(quiz_data)
                                    
                                    # Export buttons
                                    display_export_buttons(quiz_data)
        
        else:
            # Document upload
            uploaded_file = st.file_uploader(
                "📄 Upload a document",
                type=['pdf', 'docx', 'txt'],
                help="Upload PDF, DOCX, or TXT files"
            )
            
            # Generate button for document
            if uploaded_file and st.button("🚀 Generate Quiz from Document", type="primary", use_container_width=True):
                # Show loading spinner
                with st.spinner("🔄 Processing document... This may take a few moments."):
                    # Process document
                    document_text, doc_error = process_document(uploaded_file)
                    
                    if doc_error:
                        st.error(f"❌ Failed to process document: {doc_error}")
                    else:
                        # Check document length
                        doc_length = len(document_text)
                        if doc_length > 10000:  # More than 10k characters
                            st.warning(f"⚠️ Long document detected ({doc_length} characters). This may take longer to process.")
                            st.info("💡 Consider using a shorter document for faster results.")
                        
                        st.success(f"✅ Document processed successfully! ({doc_length} characters)")
                        
                        # Generate quiz with progress indicator
                        with st.spinner("🧠 Generating quiz with AI... This may take up to 1 minute for long documents."):
                            quiz_data, quiz_error = generate_quiz_with_deepseek(document_text)
                        
                        if quiz_error:
                            st.error(f"❌ Failed to generate quiz: {quiz_error}")
                        else:
                            st.success("🎉 Quiz generated successfully!")
                            
                            # Store data in session state for export
                            st.session_state.quiz_data = quiz_data
                            st.session_state.document_text = document_text
                            
                            # Display results
                            display_results(quiz_data)
                            
                            # Export buttons
                            display_export_buttons(quiz_data)

def display_results(data):
    """Display the generated quiz results"""
    
    # Quiz section
    st.markdown('<h2 class="section-header">❓ Quiz Questions</h2>', unsafe_allow_html=True)
    
    for i, question_data in enumerate(data['quiz'], 1):
        st.markdown(f'<div class="question-box">', unsafe_allow_html=True)
        st.markdown(f"**Question {i}:** {question_data['question']}")
        
        # Display options
        options = question_data['options']
        correct_answer = question_data['answer']
        
        for j, option in enumerate(['A', 'B', 'C', 'D']):
            option_text = f"{option}. {options[j]}"
            if option == correct_answer:
                st.markdown(f'<div class="correct-answer">✅ {option_text}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f"❌ {option_text}")
        
        st.markdown('</div>', unsafe_allow_html=True)

def display_export_buttons(data):
    """Display export buttons for the generated content"""
    st.markdown('<h2 class="section-header">📤 Export Results</h2>', unsafe_allow_html=True)
    
    # Full data export
    st.markdown("**📋 Complete Package:**")
    col1, col2 = st.columns(2)
    
    with col1:
        # JSON export
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        st.download_button(
            label="📄 Download Complete JSON",
            data=json_str,
            file_name="quiz_data.json",
            mime="application/json",
            use_container_width=True,
            key="dl_full_json"
        )
    
    with col2:
        # PDF export - generate and provide direct download button
        try:
            pdf_buffer = create_pdf_report(data, "quiz_report.pdf")
            st.download_button(
                label="📊 Download Complete PDF",
                data=pdf_buffer.getvalue(),
                file_name="quiz_report.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="dl_full_pdf"
            )
        except Exception as e:
            st.error(f"Failed to create PDF: {str(e)}")
    
    # Quiz download
    st.markdown("**🎯 Quiz Download:**")
    col3 = st.columns(1)[0]
    
    with col3:
        # Quiz only export
        quiz_only = {
            "quiz": data['quiz']
        }
        quiz_json = json.dumps(quiz_only, indent=2, ensure_ascii=False)
        st.download_button(
            label="❓ Download Quiz (JSON)",
            data=quiz_json,
            file_name="quiz_questions.json",
            mime="application/json",
            use_container_width=True,
            key="dl_quiz_json"
        )

if __name__ == "__main__":
    main() 
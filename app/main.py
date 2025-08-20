import os
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .services.youtube import extract_video_id, fetch_transcript, fetch_title
from .services.quiz import generate_quiz_from_transcript, generate_quiz_with_openai


class GenerateQuizRequest(BaseModel):
    url: str = Field(..., description="Full YouTube video URL")
    num_questions: int = Field(5, ge=1, le=20, description="Number of questions to generate")
    method: Literal["heuristic", "openai"] = Field("heuristic")
    languages: Optional[List[str]] = Field(
        default_factory=lambda: ["en", "en-US", "en-GB"],
        description="Preferred transcript languages in order",
    )


class QuizQuestion(BaseModel):
    question: str
    answer: str
    type: Literal["cloze", "short_answer"] = "cloze"


class GenerateQuizResponse(BaseModel):
    title: str
    questions: List[QuizQuestion]
    transcript_chars: int
    method: str


app = FastAPI(title="AI Quiz Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/generate_quiz", response_model=GenerateQuizResponse)
async def generate_quiz(payload: GenerateQuizRequest):
    try:
        video_id = extract_video_id(payload.url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL")

        transcript_text = fetch_transcript(video_id, payload.languages)
        if not transcript_text or transcript_text.strip() == "":
            raise HTTPException(status_code=404, detail="Transcript not available for this video")

        video_title = fetch_title(video_id) or "YouTube Video"

        if payload.method == "openai":
            questions = generate_quiz_with_openai(transcript_text, payload.num_questions)
        else:
            questions = generate_quiz_from_transcript(transcript_text, payload.num_questions)

        return GenerateQuizResponse(
            title=video_title,
            questions=questions,
            transcript_chars=len(transcript_text),
            method=payload.method,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
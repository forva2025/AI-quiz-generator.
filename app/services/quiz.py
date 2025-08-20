import os
import math
import re
from collections import Counter
from typing import Dict, List

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

STOPWORDS = set([
    "the","and","is","in","to","of","a","that","it","for","on","as","with","are","this","by","an","be","or","from","at","was","we","you","your","our","have","has","not","can","will","they","their","but","what","which","who","when","where","how","why","about","into","more","most","other","some","such","no","nor","too","very","just","than","also","so","if","out","up","over","after","before","between","within","without","because","been","being","does","did","doing","these","those","through"
])


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_into_sentences(text: str) -> List[str]:
    text = normalize_text(text)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [s.strip() for s in sentences if len(s.strip()) > 0]


def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z']{2,}", text.lower())


def score_sentences(sentences: List[str]) -> Dict[int, float]:
    all_tokens = []
    for sentence in sentences:
        all_tokens.extend([t for t in tokenize(sentence) if t not in STOPWORDS])
    freq = Counter(all_tokens)
    max_freq = max(freq.values()) if freq else 1
    for token in list(freq.keys()):
        freq[token] = freq[token] / max_freq
    scores: Dict[int, float] = {}
    for idx, sentence in enumerate(sentences):
        tokens = [t for t in tokenize(sentence) if t not in STOPWORDS]
        if not tokens:
            scores[idx] = 0.0
            continue
        scores[idx] = sum(freq.get(t, 0) for t in tokens) / math.sqrt(len(tokens))
    return scores


def make_cloze_question(sentence: str) -> Dict[str, str]:
    tokens = tokenize(sentence)
    candidates = [t for t in tokens if t not in STOPWORDS and len(t) >= 5]
    if not candidates:
        candidates = [t for t in tokens if len(t) >= 4]
    if not candidates:
        return {
            "question": f"What is the main point of this statement: '{sentence[:160]}...' ?",
            "answer": sentence,
            "type": "short_answer",
        }
    blank_word = sorted(candidates, key=lambda t: (-tokens.count(t), -len(t)))[0]
    pattern = re.compile(re.escape(blank_word), re.IGNORECASE)
    blanked = pattern.sub("_____", sentence, count=1)
    return {
        "question": f"Fill in the blank: {blanked}",
        "answer": blank_word,
        "type": "cloze",
    }


def generate_quiz_from_transcript(transcript_text: str, num_questions: int) -> List[Dict[str, str]]:
    sentences = split_into_sentences(transcript_text)
    if not sentences:
        return [{
            "question": "What is the video about?",
            "answer": "No transcript available to derive an answer.",
            "type": "short_answer",
        }]
    scores = score_sentences(sentences)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    selected: List[str] = []
    for idx, _ in ranked:
        if len(selected) >= num_questions:
            break
        s = sentences[idx]
        if len(s) < 50:
            continue
        is_duplicate = any(
            len(set(tokenize(s)).intersection(set(tokenize(prev)))) / max(1, len(set(tokenize(s)))) > 0.6
            for prev in selected
        )
        if is_duplicate:
            continue
        selected.append(s)
    if not selected:
        selected = sentences[: min(num_questions, len(sentences))]
    questions = [make_cloze_question(s) for s in selected]
    return questions


def generate_quiz_with_openai(transcript_text: str, num_questions: int) -> List[Dict[str, str]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return generate_quiz_from_transcript(transcript_text, num_questions)
    client = OpenAI(api_key=api_key)
    trimmed = transcript_text.strip()
    max_chars = 8000
    if len(trimmed) > max_chars:
        trimmed = trimmed[:max_chars]
    system_prompt = (
        "You are a helpful assistant that creates concise cloze (fill-in-the-blank) questions from transcripts. "
        "Return strictly a JSON object with an array 'questions' of objects {question, answer, type}. Keep questions clear and unambiguous."
    )
    user_prompt = (
        f"Create {num_questions} cloze questions based on this transcript. Prefer key facts and definitions.\n\nTranscript:\n" + trimmed
    )
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        import json
        try:
            data = json.loads(content)
        except Exception:
            data = {"questions": []}
        items = data.get("questions", [])
        results: List[Dict[str, str]] = []
        for item in items:
            q = str(item.get("question", "")).strip()
            a = str(item.get("answer", "")).strip()
            t = str(item.get("type", "cloze")).strip() or "cloze"
            if q and a:
                results.append({"question": q, "answer": a, "type": t})
        if not results:
            return generate_quiz_from_transcript(transcript_text, num_questions)
        return results[:num_questions]
    except Exception:
        return generate_quiz_from_transcript(transcript_text, num_questions)
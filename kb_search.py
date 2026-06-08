import re
from pathlib import Path

KB_PATH = Path("knowledge_base.md")


def normalize_text(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def split_knowledge_base():
    if not KB_PATH.exists():
        return []
    content = KB_PATH.read_text(encoding="utf-8")
    sections = []
    current_title = "General"
    current_lines = []
    for line in content.splitlines():
        if line.startswith("#"):
            if current_lines:
                sections.append({"title": current_title, "text": "\n".join(current_lines).strip()})
                current_lines = []
            current_title = line.replace("#", "").strip() or "General"
        else:
            current_lines.append(line)
    if current_lines:
        sections.append({"title": current_title, "text": "\n".join(current_lines).strip()})
    return [section for section in sections if section["text"]]


def keyword_score(query, text):
    query_words = set(re.findall(r"[a-zA-ZąćęłńóśźżА-Яа-яІіЇїЄєҐґ0-9]+", normalize_text(query)))
    text_norm = normalize_text(text)
    score = 0
    for word in query_words:
        if len(word) < 3:
            continue
        if word in text_norm:
            score += 2
    return score


def search_kb(query, limit=4):
    sections = split_knowledge_base()
    scored = []
    for section in sections:
        combined = f"{section['title']}\n{section['text']}"
        scored.append({**section, "score": keyword_score(query, combined)})
    scored.sort(key=lambda item: item["score"], reverse=True)
    results = [item for item in scored if item["score"] > 0][:limit]
    return results or sections[:2]


def build_kb_context(chunks):
    if not chunks:
        return "No relevant knowledge base sections found."
    return "\n\n".join(f"## {chunk['title']}\n{chunk['text']}" for chunk in chunks)

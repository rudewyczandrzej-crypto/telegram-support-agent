import os
import json
from groq import Groq

MODEL_NAME = "llama-3.3-70b-versatile"


def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY не знайдено у Railway Variables")
    return Groq(api_key=api_key)


def clean_json_text(text):
    text = text.strip()
    if text.startswith("```json"):
        text = text.replace("```json", "", 1).strip()
    if text.startswith("```"):
        text = text.replace("```", "", 1).strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def answer_support_question(user_message, kb_context):
    system_prompt = '''You are an AI customer support agent.
Rules:
1. Answer ONLY using the provided knowledge base context.
2. If the knowledge base does not contain enough information, do not guess.
3. If you cannot answer confidently, set should_create_ticket to true.
4. Be concise, friendly, and practical.
5. Return only valid JSON.
6. category must be one of: delivery, returns, refund, warranty, payment, tracking, complaint, pricing, technical, other.
7. confidence must be one of: high, medium, low.
8. priority must be one of: low, normal, high, urgent.
JSON format:
{"answer":"message to customer","category":"delivery|returns|refund|warranty|payment|tracking|complaint|pricing|technical|other","confidence":"high|medium|low","should_create_ticket":true,"priority":"low|normal|high|urgent","ai_summary":"short summary or null"}'''
    user_prompt = f"User question:\n{user_message}\n\nKnowledge base context:\n{kb_context}"
    client = get_groq_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    raw_text = clean_json_text(response.choices[0].message.content)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "answer": "Не зміг коректно сформувати відповідь. Я створю ticket для менеджера.",
            "category": "other",
            "confidence": "low",
            "should_create_ticket": True,
            "priority": "normal",
            "ai_summary": raw_text[:500],
        }
    return {
        "answer": data.get("answer") or "Не знайшов точну відповідь у базі знань.",
        "category": data.get("category") or "other",
        "confidence": data.get("confidence") or "low",
        "should_create_ticket": bool(data.get("should_create_ticket")),
        "priority": data.get("priority") or "normal",
        "ai_summary": data.get("ai_summary"),
    }


def generate_ticket_reply(ticket):
    system_prompt = '''You are a customer support specialist.
Generate a polite draft reply for a human support agent based on the ticket.
Return only valid JSON.
JSON format: {"subject":"short subject","body":"reply body"}'''
    user_prompt = f"""Ticket:
ID: {ticket.get('id')}
Question: {ticket.get('user_message')}
Category: {ticket.get('category')}
Priority: {ticket.get('priority')}
AI summary: {ticket.get('ai_summary')}
Status: {ticket.get('status')}
"""
    client = get_groq_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )
    raw_text = clean_json_text(response.choices[0].message.content)
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"subject": "Support request", "body": raw_text}

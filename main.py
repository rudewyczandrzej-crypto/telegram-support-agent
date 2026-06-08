import os
import csv
import io
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from database import (
    init_db, save_message, create_ticket, list_tickets, get_ticket,
    update_ticket_status, list_messages, get_report, clear_all,
)
from kb_search import search_kb, build_kb_context
from ai_service import answer_support_question, generate_ticket_reply

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_IDS_RAW = os.getenv("ALLOWED_CHAT_IDS", "")
VALID_TICKET_STATUSES = ["open", "in_progress", "resolved", "closed"]


def get_allowed_chat_ids():
    allowed_ids = set()
    for item in ALLOWED_CHAT_IDS_RAW.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            allowed_ids.add(int(item))
        except ValueError:
            continue
    return allowed_ids


def is_allowed_chat(telegram_chat_id):
    allowed_ids = get_allowed_chat_ids()
    if not allowed_ids:
        return True
    return telegram_chat_id in allowed_ids


async def deny_if_not_allowed(update):
    chat_id = update.effective_chat.id
    if is_allowed_chat(chat_id):
        return False
    if update.message:
        await update.message.reply_text("Доступ закритий 🔒\n\nЦей бот приватний.")
    if update.callback_query:
        await update.callback_query.answer("Доступ закритий", show_alert=True)
    return True


def build_main_keyboard():
    keyboard = [["🎫 Tickets", "📊 Report"], ["📚 Knowledge", "🧾 History"], ["➕ Help"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Напиши питання клієнта")


def build_ticket_keyboard(ticket_id):
    keyboard = [
        [InlineKeyboardButton("✍️ Draft reply", callback_data=f"draft:{ticket_id}"), InlineKeyboardButton("👁 View", callback_data=f"view_ticket:{ticket_id}")],
        [InlineKeyboardButton("🔄 In progress", callback_data=f"ticket_status:{ticket_id}:in_progress"), InlineKeyboardButton("✅ Resolved", callback_data=f"ticket_status:{ticket_id}:resolved")],
        [InlineKeyboardButton("📁 Closed", callback_data=f"ticket_status:{ticket_id}:closed")],
    ]
    return InlineKeyboardMarkup(keyboard)


def short(text, limit=700):
    if not text:
        return "—"
    text = str(text).strip()
    return text if len(text) <= limit else text[:limit] + "..."


def format_ticket(ticket):
    return (
        f"Ticket #{ticket['id']}\n\n"
        f"Status: {ticket.get('status') or '—'}\n"
        f"Category: {ticket.get('category') or '—'}\n"
        f"Priority: {ticket.get('priority') or '—'}\n\n"
        f"Question:\n{short(ticket.get('user_message'), 900)}\n\n"
        f"AI summary:\n{short(ticket.get('ai_summary'), 900)}"
    )


def format_tickets_list(tickets):
    if not tickets:
        return "Tickets поки немає."
    lines = ["Tickets 🎫\n"]
    for ticket in tickets:
        lines.append(
            f"{ticket['id']}. {ticket['status']} | {ticket.get('category') or 'other'} | {ticket.get('priority') or 'normal'}\n"
            f"   {short(ticket.get('user_message'), 120)}"
        )
    return "\n\n".join(lines)


def build_help_text():
    return (
        "AI Support Agent with Knowledge Base 🤖\n\n"
        "Як працює:\n"
        "1. Користувач пише питання.\n"
        "2. Бот шукає відповідь у knowledge_base.md.\n"
        "3. Якщо знає — відповідає.\n"
        "4. Якщо не знає — створює ticket для людини.\n\n"
        "Команди:\n"
        "/ask question — задати питання\n"
        "/tickets — список tickets\n"
        "/ticket ID — відкрити ticket\n"
        "/status ID status — змінити статус ticket\n"
        "/draft ID — згенерувати draft-відповідь\n"
        "/history — історія питань\n"
        "/report — статистика\n"
        "/export — CSV export tickets\n"
        "/clear — очистити історію і tickets\n"
        "/myid — показати chat_id\n\n"
        "Статуси: open, in_progress, resolved, closed\n\n"
        "Можна просто написати питання без /ask."
    )


async def start(update, context):
    if await deny_if_not_allowed(update):
        return
    await update.message.reply_text(
        "Привіт! Це AI Support Agent з базою знань 🤖\n\n"
        "Напиши питання клієнта, а я спробую відповісти тільки на основі knowledge base. "
        "Якщо відповіді немає — створю ticket для людини.\n\n" + build_help_text(),
        reply_markup=build_main_keyboard(),
    )


async def help_command(update, context):
    if await deny_if_not_allowed(update):
        return
    await update.message.reply_text(build_help_text(), reply_markup=build_main_keyboard())


async def myid_command(update, context):
    await update.message.reply_text(f"Твій chat_id:\n{update.effective_chat.id}")


async def process_question(update, user_message):
    chat_id = update.effective_chat.id
    thinking_message = await update.effective_message.reply_text("Шукаю відповідь у базі знань... 🔎")
    chunks = search_kb(user_message)
    kb_context = build_kb_context(chunks)
    result = answer_support_question(user_message, kb_context)

    answer = result["answer"]
    category = result["category"]
    confidence = result["confidence"]
    should_create_ticket = result["should_create_ticket"]
    priority = result["priority"]
    ai_summary = result.get("ai_summary")
    ticket_id = None

    if should_create_ticket or confidence == "low":
        ticket_id = create_ticket(chat_id, user_message, category, priority, ai_summary or answer)
        answer += f"\n\n🎫 Я створив ticket для менеджера.\nTicket ID: {ticket_id}"

    save_message(chat_id, user_message, answer, category, confidence, not should_create_ticket, ticket_id)
    used_sections = "\n".join(f"- {chunk['title']}" for chunk in chunks)
    reply = f"{answer}\n\nCategory: {category}\nConfidence: {confidence}\nKB sections used:\n{used_sections or '—'}"

    if ticket_id:
        await thinking_message.edit_text(reply, reply_markup=build_ticket_keyboard(ticket_id))
    else:
        await thinking_message.edit_text(reply)


async def ask_command(update, context):
    if await deny_if_not_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Формат: /ask your question")
        return
    await process_question(update, " ".join(context.args).strip())


async def tickets_command(update, context):
    if await deny_if_not_allowed(update):
        return
    await update.message.reply_text(format_tickets_list(list_tickets(update.effective_chat.id)))


async def ticket_command(update, context):
    if await deny_if_not_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Формат: /ticket ID")
        return
    try:
        ticket_id = int(context.args[0])
        ticket = get_ticket(ticket_id, update.effective_chat.id)
        if not ticket:
            await update.message.reply_text(f"Ticket {ticket_id} не знайдено.")
            return
        await update.message.reply_text(format_ticket(ticket), reply_markup=build_ticket_keyboard(ticket_id))
    except ValueError:
        await update.message.reply_text("ID має бути числом.")


async def status_command(update, context):
    if await deny_if_not_allowed(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Формат: /status ID status")
        return
    try:
        ticket_id = int(context.args[0])
        status = context.args[1].strip().lower()
        if status not in VALID_TICKET_STATUSES:
            await update.message.reply_text("Невідомий статус. Доступні:\n" + ", ".join(VALID_TICKET_STATUSES))
            return
        updated = update_ticket_status(ticket_id, update.effective_chat.id, status)
        await update.message.reply_text(f"Ticket {ticket_id} змінено на {status} ✅" if updated else f"Ticket {ticket_id} не знайдено.")
    except ValueError:
        await update.message.reply_text("ID має бути числом.")


async def draft_command(update, context):
    if await deny_if_not_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Формат: /draft ID")
        return
    try:
        ticket_id = int(context.args[0])
        ticket = get_ticket(ticket_id, update.effective_chat.id)
        if not ticket:
            await update.message.reply_text(f"Ticket {ticket_id} не знайдено.")
            return
        draft = generate_ticket_reply(ticket)
        await update.message.reply_text(f"Draft reply ✍️\n\nSubject:\n{draft.get('subject')}\n\nBody:\n{draft.get('body')}")
    except ValueError:
        await update.message.reply_text("ID має бути числом.")


async def history_command(update, context):
    if await deny_if_not_allowed(update):
        return
    messages = list_messages(update.effective_chat.id)
    if not messages:
        await update.message.reply_text("Історії поки немає.")
        return
    lines = ["History 🧾\n"]
    for msg in messages:
        lines.append(
            f"{msg['id']}. {msg.get('category') or 'other'} | {msg.get('confidence') or '—'}\n"
            f"Q: {short(msg.get('user_message'), 120)}\n"
            f"A: {short(msg.get('ai_answer'), 160)}"
        )
    await update.message.reply_text("\n\n".join(lines))


async def report_command(update, context):
    if await deny_if_not_allowed(update):
        return
    report = get_report(update.effective_chat.id)
    lines = ["Support report 📊\n", f"Total messages: {report['total_messages']}\n", "Tickets by status:"]
    if report["tickets_by_status"]:
        for row in report["tickets_by_status"]:
            lines.append(f"- {row['status']}: {row['count']}")
    else:
        lines.append("- no tickets")
    lines.append("\nMessages by category:")
    if report["messages_by_category"]:
        for row in report["messages_by_category"]:
            lines.append(f"- {row['category'] or 'other'}: {row['count']}")
    else:
        lines.append("- no messages")
    await update.message.reply_text("\n".join(lines))


async def export_command(update, context):
    if await deny_if_not_allowed(update):
        return
    tickets = list_tickets(update.effective_chat.id, limit=1000)
    if not tickets:
        await update.message.reply_text("Немає tickets для export.")
        return
    output = io.StringIO()
    fieldnames = ["id", "status", "category", "priority", "user_message", "ai_summary", "created_at", "updated_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for ticket in tickets:
        writer.writerow({field: ticket.get(field) for field in fieldnames})
    csv_bytes = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    csv_bytes.name = "support_tickets.csv"
    await update.message.reply_document(document=InputFile(csv_bytes, filename="support_tickets.csv"), caption="Export готовий ✅")


async def clear_command(update, context):
    if await deny_if_not_allowed(update):
        return
    clear_all(update.effective_chat.id)
    await update.message.reply_text("Історію і tickets очищено ✅")


async def knowledge_command(update, context):
    if await deny_if_not_allowed(update):
        return
    await update.message.reply_text("База знань зараз зберігається у файлі knowledge_base.md у GitHub repo. Щоб змінити відповіді агента, відредагуй knowledge_base.md і зроби redeploy.")


async def handle_keyboard_text(update):
    text = update.message.text
    if text == "🎫 Tickets":
        await update.message.reply_text(format_tickets_list(list_tickets(update.effective_chat.id)))
        return True
    if text == "📊 Report":
        await report_command(update, None)
        return True
    if text == "📚 Knowledge":
        await knowledge_command(update, None)
        return True
    if text == "🧾 History":
        await history_command(update, None)
        return True
    if text == "➕ Help":
        await update.message.reply_text(build_help_text())
        return True
    return False


async def handle_message(update, context):
    if await deny_if_not_allowed(update):
        return
    if await handle_keyboard_text(update):
        return
    user_message = update.message.text.strip()
    if user_message:
        await process_question(update, user_message)


async def button_handler(update, context):
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
        chat_id = query.message.chat_id
        data = query.data
        if not is_allowed_chat(chat_id):
            await query.message.reply_text("Доступ закритий 🔒")
            return
        parts = data.split(":")
        action = parts[0]
        ticket_id = int(parts[1])
        if action == "view_ticket":
            ticket = get_ticket(ticket_id, chat_id)
            if not ticket:
                await query.message.reply_text(f"Ticket {ticket_id} не знайдено.")
                return
            await query.message.reply_text(format_ticket(ticket), reply_markup=build_ticket_keyboard(ticket_id))
            return
        if action == "draft":
            ticket = get_ticket(ticket_id, chat_id)
            if not ticket:
                await query.message.reply_text(f"Ticket {ticket_id} не знайдено.")
                return
            draft = generate_ticket_reply(ticket)
            await query.message.reply_text(f"Draft reply ✍️\n\nSubject:\n{draft.get('subject')}\n\nBody:\n{draft.get('body')}")
            return
        if action == "ticket_status":
            if len(parts) < 3:
                await query.message.reply_text("Не передано статус.")
                return
            status = parts[2]
            if status not in VALID_TICKET_STATUSES:
                await query.message.reply_text("Невідомий статус.")
                return
            updated = update_ticket_status(ticket_id, chat_id, status)
            await query.message.reply_text(f"Ticket {ticket_id} змінено на {status} ✅" if updated else f"Ticket {ticket_id} не знайдено.")
            return
        await query.message.reply_text("Невідома дія кнопки.")
    except Exception as error:
        logging.exception("Error while handling button")
        try:
            await query.message.reply_text(f"Сталася помилка при обробці кнопки 😕\n\nТехнічна помилка:\n{type(error).__name__}: {error}")
        except Exception:
            pass


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Не знайдено TELEGRAM_BOT_TOKEN у Railway Variables.")
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("tickets", tickets_command))
    app.add_handler(CommandHandler("ticket", ticket_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("draft", draft_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("knowledge", knowledge_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Support Agent is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

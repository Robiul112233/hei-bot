import telebot
import sqlite3
import time
from telebot import types
from datetime import datetime

# --- কনফিগারেশন ---
API_TOKEN = '8749315873:AAF3S4bgWFq19TCIXBAwH1x-rX5oYjM9pSE'
#   MongoDB Connection String  
MONGO_URL = "mongodb+srv://robiul159358:robiul159358@cluster0.6vuiitm.mongodb.net/?appName=Cluster0"
ADMIN_ID = 6864515052
CHANNEL_ID = '@hiddenearningidea' 
CHANNEL_LINK = 'https://t.me/hiddenearningidea'

bot = telebot.TeleBot(API_TOKEN)
user_states = {} 
user_cooldowns = {}

# --- ডাটাবেস ফাংশন ---
def get_db_connection():
    return sqlite3.connect('numbers_bot.db', check_same_thread=False, timeout=20)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # স্টক টেবিল
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock 
                      (id INTEGER PRIMARY KEY, service TEXT, country TEXT, phone_number TEXT, status TEXT)''')
    # ইউজার টেবিল (ডেট সহ)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, join_date TEXT)''')
    # সেলস রেকর্ড টেবিল
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT, country TEXT, sale_date TEXT)''')
    conn.commit()
    conn.close()

# --- এনালাইটিক্স (Dashboard) ---
def get_analytics():
    conn = get_db_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE join_date=?", (today,))
    new_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sales WHERE sale_date=?", (today,))
    total_sales_today = cursor.fetchone()[0]
    
    cursor.execute("SELECT country, COUNT(country) as cnt FROM sales GROUP BY country ORDER BY cnt DESC LIMIT 1")
    top_country_raw = cursor.fetchone()
    top_country = top_country_raw[0] if top_country_raw else "N/A"
    
    conn.close()
    return new_users, total_sales_today, top_country

def is_subscribed(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return False

def get_available_countries(service):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT country FROM stock WHERE service=? AND status='Available'", (service,))
    countries = [row[0] for row in cursor.fetchall()]
    conn.close()
    return countries

# --- এডমিন মেনু ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id == ADMIN_ID:
        u, s, c = get_analytics()
        report = (
            f"📊 **HEI ADMIN DASHBOARD**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 আজ নতুন ইউজার: `{u}` জন\n"
            f"📱 আজ নম্বর সেল: `{s}` টি\n"
            f"🌍 টপ সেলিং দেশ: `{c}`\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Add Number", callback_data="admin_add"),
            types.InlineKeyboardButton("🗑 Delete Country", callback_data="admin_del"),
            types.InlineKeyboardButton("📊 Check Stock", callback_data="admin_stock"),
            types.InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")
        )
        bot.send_message(message.chat.id, report, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    if call.data == "admin_refresh":
        u, s, c = get_analytics()
        report = f"📊 **HEI ADMIN DASHBOARD**\n━━━━━━━━━━━━━━━━━━━━\n👤 আজ নতুন ইউজার: `{u}`\n📱 আজ নম্বর সেল: `{s}`\n🌍 টপ সেলিং দেশ: `{c}`\n━━━━━━━━━━━━━━━━━━━━"
        try: bot.edit_message_text(report, call.message.chat.id, call.message.message_id, reply_markup=call.message.reply_markup, parse_mode="Markdown")
        except: pass

    elif call.data == "admin_add":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔵 FB", callback_data="adm_set_srv_FB"),
                   types.InlineKeyboardButton("✈️ TG", callback_data="adm_set_srv_TG"),
                   types.InlineKeyboardButton("🟢 WA", callback_data="adm_set_srv_WA"))
        bot.edit_message_text("সার্ভিস সিলেক্ট করুন (Add):", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_del":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔵 FB", callback_data="adm_del_srv_FB"),
                   types.InlineKeyboardButton("✈️ TG", callback_data="adm_del_srv_TG"),
                   types.InlineKeyboardButton("🟢 WA", callback_data="adm_del_srv_WA"))
        bot.edit_message_text("সার্ভিস সিলেক্ট করুন (Delete):", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_stock":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT service, country, COUNT(*) FROM stock WHERE status='Available' GROUP BY service, country")
        rows = cursor.fetchall()
        report = "📊 **Current Stock:**\n\n"
        for s, c, count in rows: report += f"{s} ({c}): {count} pcs\n"
        bot.send_message(call.message.chat.id, report if rows else "স্টক খালি!", parse_mode="Markdown")
        conn.close()

# --- এডমিন ইনপুট হ্যান্ডলার (Add/Delete) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_set_srv_"))
def admin_start_add(call):
    service = call.data.split("_")[3]
    user_states[call.from_user.id] = {'service': service, 'step': 'waiting_country'}
    bot.edit_message_text(f"📍 সার্ভিস: **{service}**\nএখন দেশের নাম টাইপ করুন:", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_del_srv_"))
def admin_del_country_select(call):
    service = call.data.split("_")[3]
    countries = get_available_countries(service)
    if not countries:
        bot.answer_callback_query(call.id, "নম্বর নেই!", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    for c in countries:
        markup.add(types.InlineKeyboardButton(c, callback_data=f"conf_del_{service}_{c}"))
    bot.edit_message_text(f"🗑 {service} এর কোন দেশের সব নম্বর ডিলিট করবেন?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("conf_del_"))
def admin_final_delete(call):
    _, _, srv, cnt = call.data.split("_")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stock WHERE service=? AND country=?", (srv, cnt))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, f"✅ {cnt} ({srv}) ডিলিট হয়েছে!", show_alert=True)
    admin_panel(call.message)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.from_user.id in user_states)
def handle_admin_inputs(message):
    state = user_states[message.from_user.id]
    if state['step'] == 'waiting_country':
        user_states[message.from_user.id]['country'] = message.text
        user_states[message.from_user.id]['step'] = 'waiting_numbers'
        bot.reply_to(message, f"✅ দেশ: **{message.text}**\nএখন নম্বরগুলো পেস্ট করুন।")
    elif state['step'] == 'waiting_numbers':
        data = user_states[message.from_user.id]
        numbers = message.text.split()
        conn = get_db_connection()
        cursor = conn.cursor()
        for num in numbers: cursor.execute("INSERT INTO stock (service, country, phone_number, status) VALUES (?, ?, ?, 'Available')", (data['service'], data['country'], num))
        conn.commit()
        conn.close()
        del user_states[message.from_user.id]
        bot.reply_to(message, f"✅ {len(numbers)}টি নম্বর যোগ হয়েছে!")

# --- ইউজার সাইড ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, join_date) VALUES (?, ?)", (user_id, today))
    conn.commit()
    conn.close()

    if is_subscribed(user_id):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        markup.add(types.KeyboardButton("📱 Get Numbers"))
        bot.send_message(message.chat.id, "✨ **WELCOME TO HEI BOT** ✨", reply_markup=markup, parse_mode="Markdown")
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        markup.add(types.InlineKeyboardButton("🔄 I Have Joined", callback_data="check_sub"))
        bot.send_message(message.chat.id, "⚠️ **Access Denied!**\nচ্যানেলে জয়েন করে নিচের বাটনে ক্লিক করুন।", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub_cb(call):
    if is_subscribed(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        start(call.message)
    else: bot.answer_callback_query(call.id, "❌ আপনি এখনো জয়েন করেননি!", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "📱 Get Numbers")
def select_service_menu(message):
    if not is_subscribed(message.from_user.id): return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for name, code in [("🔵 Facebook", "FB"), ("✈️ Telegram", "TG"), ("🟢 WhatsApp", "WA")]:
        if get_available_countries(code): markup.add(types.InlineKeyboardButton(name, callback_data=f"usr_srv_{code}"))
    if markup.keyboard: bot.send_message(message.chat.id, "🌍 **সার্ভিস সিলেক্ট করুন:**", reply_markup=markup, parse_mode="Markdown")
    else: bot.send_message(message.chat.id, "😔 বর্তমানে সব স্টক খালি!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("usr_srv_"))
def select_country(call):
    service = call.data.split("_")[2]
    countries = get_available_countries(service)
    markup = types.InlineKeyboardMarkup(row_width=2)
    for c in countries: markup.add(types.InlineKeyboardButton(c, callback_data=f"get_{service}_{c}"))
    bot.edit_message_text(f"📍 **{service} দেশ সিলেক্ট করুন:**", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("get_"))
def deliver_numbers(call):
    data = call.data.split("_")
    service, country = data[1], data[2]
    today = datetime.now().strftime('%Y-%m-%d')
    
    if call.from_user.id in user_cooldowns and time.time() - user_cooldowns[call.from_user.id] < 15:
        bot.answer_callback_query(call.id, "⏳ ১৫ সেকেন্ড অপেক্ষা করুন!", show_alert=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, phone_number FROM stock WHERE service=? AND country=? AND status='Available' LIMIT 3", (service, country))
    rows = cursor.fetchall()
    
    if rows:
        user_cooldowns[call.from_user.id] = time.time()
        num_text = "\n".join([f"🔹 `{r[1]}`" for r in rows])
        for r in rows:
            cursor.execute("UPDATE stock SET status='Sold' WHERE id=?", (r[0],))
            cursor.execute("INSERT INTO sales (service, country, sale_date) VALUES (?, ?, ?)", (service, country, today))
        conn.commit()
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        cursor.execute("SELECT 1 FROM stock WHERE service=? AND country=? AND status='Available' LIMIT 1", (service, country))
        if cursor.fetchone(): markup.add(types.InlineKeyboardButton("🔄 Change Number", callback_data=f"get_{service}_{country}"))
        markup.add(types.InlineKeyboardButton("👥 OTP GROUP", url="https://t.me/mrsotpgroup"))
        bot.edit_message_text(f"✅ **আপনার {country} নম্বর:**\n\n{num_text}", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    else: bot.answer_callback_query(call.id, "😔 স্টক শেষ!", show_alert=True)
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Advanced HEI Bot is Running...")
    bot.infinity_polling()
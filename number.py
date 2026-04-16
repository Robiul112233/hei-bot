import telebot
import sqlite3
import time
import os
from telebot import types
from datetime import datetime
from dotenv import load_dotenv

# ====================== CONFIG ======================
load_dotenv()
API_TOKEN = os.getenv('API_TOKEN', '8749315873:AAF3S4bgWFq19TCIXBAwH1x-rX5oYjM9pSE')
ADMIN_ID = 6864515052
CHANNEL_ID = '@hiddenearningidea'
CHANNEL_LINK = 'https://t.me/mrsotpgroup'
OTP_GROUP_ID = -1003717990729

bot = telebot.TeleBot(API_TOKEN)
user_states = {}
user_cooldowns = {}
change_num_cooldowns = {}

# ====================== DATABASE ======================
def get_db_connection():
    return sqlite3.connect('numbers_bot.db', check_same_thread=False, timeout=30)

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS stock
                          (id INTEGER PRIMARY KEY, service TEXT, country TEXT, phone_number TEXT, status TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS users
                          (user_id INTEGER PRIMARY KEY, join_date TEXT, total_bought INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS sales
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                           service TEXT, country TEXT, phone_number TEXT, sale_time REAL)''')
        conn.commit()

# ====================== HELPERS ======================
def is_subscribed(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except:
        return False

def check_cooldown(user_id, cooldown_seconds=25):
    now = time.time()
    if user_id in user_cooldowns and now - user_cooldowns[user_id] < cooldown_seconds:
        return False
    user_cooldowns[user_id] = now
    return True

def get_available_services():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT service FROM stock WHERE status='Available'")
        return [row[0] for row in cursor.fetchall()]

def get_available_countries_for_service(service):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT country FROM stock WHERE service=? AND status='Available'", (service,))
        return [row[0] for row in cursor.fetchall()]

# ====================== OTP FORWARDING ======================
@bot.message_handler(func=lambda m: m.chat.id == OTP_GROUP_ID)
def handle_incoming_group_otp(message):
    if not message.text: return
    otp_text = message.text.lower().strip()
    now = time.time()
    
    with get_db_connection() as conn:
        conn.execute("DELETE FROM sales WHERE (? - sale_time) > 600", (now,))
        active_sales = conn.execute("SELECT user_id, phone_number, service FROM sales ORDER BY sale_time DESC").fetchall()

    for user_id, full_phone, service in active_sales:
        phone_str = str(full_phone).strip()
        phone_clean = phone_str.replace("+", "").replace(" ", "").replace("-", "")
        if (phone_str in otp_text or phone_clean in otp_text or 
            (len(phone_clean) >= 4 and phone_clean[-4:] in otp_text)):
            try:
                msg = (f"🔔 𝗡𝗘𝗪 𝗢𝗧𝗣 𝗥𝗘𝗦𝗘𝗜𝗩𝗘\n━━━━━━━━━━━━━━━━━━━━\n"
                       f"📱 𝗡: `{phone_str}`\n🔹\n`{message.text}`")
                bot.send_message(user_id, msg, parse_mode="Markdown")
                break
            except: pass

# ====================== ADMIN PANEL ======================
def get_analytics():
    with get_db_connection() as conn:
        u = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        s = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        top = conn.execute("SELECT country, COUNT(*) as cnt FROM sales GROUP BY country ORDER BY cnt DESC LIMIT 1").fetchone()
        return u, s, (top[0] if top else "N/A")

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    u, s, c = get_analytics()
    report = (f"📊 **ADMIN DASHBOARD**\n━━━━━━━━━━━━━━━━━━━━\n"
              f"👥 মোট ইউজার: `{u}`\n📱 মোট সেল: `{s}`\n🌍 টপ দেশ: `{c}`\n━━━━━━━━━━━━━━━━━━━━")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add Stock", callback_data="admin_add"),
        types.InlineKeyboardButton("🗑 Delete Stock", callback_data="admin_delete"),
        types.InlineKeyboardButton("📊 View Stock", callback_data="admin_stock"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
    )
    bot.send_message(message.chat.id, report, reply_markup=markup, parse_mode="Markdown")

# --- ADMIN CALLBACKS (ORDER MATTERS) ---

@bot.callback_query_handler(func=lambda call: call.data == "admin_delete")
def admin_delete_service(call):
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("🔵 FB", callback_data="adm_del_srv_FB"),
        types.InlineKeyboardButton("✈️ TG", callback_data="adm_del_srv_TG"),
        types.InlineKeyboardButton("🟢 WA", callback_data="adm_del_srv_WA"),
        types.InlineKeyboardButton("🔙 Back", callback_data="admin_back_to_panel")
    )
    bot.edit_message_text("🗑 **কোন সার্ভিস থেকে নম্বর মুছবেন?**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_step(call):
    if call.from_user.id != ADMIN_ID: return
    user_states[ADMIN_ID] = {'step': 'waiting_broadcast'}
    bot.edit_message_text("📢 **ব্রডকাস্ট মেসেজটি লিখুন:**\n\n(আপনি যা লিখবেন তা সকল ইউজারের কাছে চলে যাবে।)", 
                          call.message.chat.id, call.message.message_id, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_del_srv_"))
def admin_delete_country_list(call):
    service = call.data.split("_")[3]
    countries = get_available_countries_for_service(service)
    if not countries:
        bot.answer_callback_query(call.id, "❌ এই সার্ভিসে কোনো নম্বর নেই!", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    for c in countries:
        markup.add(types.InlineKeyboardButton(f"🗑 {c}", callback_data=f"fdel_{service}_{c}"))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_delete"))
    bot.edit_message_text(f"🗑 **{service} - কোন দেশের সব নম্বর মুছবেন?**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("fdel_"))
def final_delete_stock(call):
    _, service, country = call.data.split("_")
    with get_db_connection() as conn:
        conn.execute("DELETE FROM stock WHERE service=? AND country=? AND status='Available'", (service, country))
        conn.commit()
    bot.answer_callback_query(call.id, f"✅ {country} ({service}) মুছে ফেলা হয়েছে!", show_alert=True)
    admin_panel(call.message)
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_back_to_panel")
def back_to_admin(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    admin_panel(call.message)

# অন্যান্য অ্যাডমিন কলব্যাক
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_general_callbacks(call):
    if call.data == "admin_add":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("FB", callback_data="adm_srv_FB"),
                   types.InlineKeyboardButton("TG", callback_data="adm_srv_TG"),
                   types.InlineKeyboardButton("WA", callback_data="adm_srv_WA"))
        bot.edit_message_text("কোন সার্ভিসে নম্বর যোগ করবেন?", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data == "admin_stock":
        with get_db_connection() as conn:
            # সার্ভিস এবং কান্ট্রি অনুযায়ী স্টক গণনা করা
            query = """
                SELECT service, country, COUNT(*) 
                FROM stock 
                WHERE status='Available' 
                GROUP BY service, country 
                ORDER BY service ASC
            """
            rows = conn.execute(query).fetchall()

        if not rows:
            bot.send_message(call.message.chat.id, "❌ **স্টক বর্তমানে সম্পূর্ণ খালি!**")
            return

        # মেসেজ ফরম্যাটিং
        msg = "📂 **বিস্তারিত বর্তমান স্টক রিপোর্ট**\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        
        current_service = ""
        total_in_bot = 0
        
        service_icons = {"FB": "🔶", "TG": "✈️", "WA": "🟢"}
        
        for srv, cntry, count in rows:
            icon = service_icons.get(srv, "🔹")
            
            # সার্ভিস হেডার তৈরি (যদি নতুন সার্ভিস শুরু হয়)
            if srv != current_service:
                msg += f"\n{icon} **{srv} SERVICES:**\n"
                current_service = srv
            
            msg += f"   ├── {cntry}: `{count}` টি\n"
            total_in_bot += count
            
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📊 **সর্বমোট নম্বর এভেলেবল:** `{total_in_bot}` টি\n"
        msg += f"⏰ আপডেট টাইম: {datetime.now().strftime('%H:%M:%S')}"

        # ইনলাইন বাটন (Refresh করার জন্য)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Refresh Stock", callback_data="admin_stock"))
        markup.add(types.InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back_to_panel"))

        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
# ====================== USER ACTIONS ======================
@bot.message_handler(func=lambda m: m.text == "📱 Get Numbers")
def show_services_btn(message):
    show_services(message)

def show_services(message):
    if not is_subscribed(message.from_user.id):
        start(message)
        return
    available_services = get_available_services()
    if not available_services:
        bot.send_message(message.chat.id, "😔 𝗦𝗧𝗢𝗖𝗞 𝗢𝗨𝗧")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    service_names = {"FB": "🔶 𝗙𝗔𝗖𝗘𝗕𝗢𝗢𝗞", "TG": "✈️ 𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠", "WA": "🟢 𝗪𝗛𝗔𝗧𝗦𝗔𝗣𝗣"}
    for srv in available_services:
        markup.add(types.InlineKeyboardButton(service_names.get(srv, srv), callback_data=f"select_srv_{srv}"))
    bot.send_message(message.chat.id, "🌍 𝗦𝗘𝗟𝗘𝗖𝗧 𝗦𝗘𝗥𝗩𝗜𝗖𝗘", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_srv_"))
def user_select_srv(call):
    service = call.data.split("_")[2]
    countries = get_available_countries_for_service(service)
    if not countries:
        bot.answer_callback_query(call.id, "𝗦𝗧𝗢𝗖𝗞 𝗢𝗨𝗧", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    for c in countries:
        markup.add(types.InlineKeyboardButton(c, callback_data=f"buy_{service}_{c}"))
    bot.edit_message_text(f"📍 **{service}** 𝗦𝗘𝗟𝗘𝗖𝗧 𝗖𝗢𝗨𝗡𝗧𝗥𝗬", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def final_buy_number(call):
    user_id = call.from_user.id
    now = time.time()

    # কুলডাউন চেক (৫ সেকেন্ড)
    if user_id in change_num_cooldowns and now - change_num_cooldowns[user_id] < 7:
        bot.answer_callback_query(call.id, "⏳ 7 সেকেন্ড অপেক্ষা করুন!", show_alert=True)
        return

    # কলব্যাক ডেটা থেকে সার্ভিস এবং দেশ আলাদা করা
    try:
        _, service, country = call.data.split("_")
    except ValueError:
        bot.answer_callback_query(call.id, "❌ ডেটা ফরম্যাট ভুল!", show_alert=True)
        return

    with get_db_connection() as conn:
        cursor = conn.cursor()
        # স্টক চেক (২টি নম্বর)
        cursor.execute("SELECT id, phone_number FROM stock WHERE service=? AND country=? AND status='Available' LIMIT 2", 
                       (service, country))
        rows = cursor.fetchall()

        if not rows:
            bot.answer_callback_query(call.id, "😔 𝗦𝗧𝗢𝗖𝗞 𝗢𝗨𝗧", show_alert=True)
            return

        numbers_display = ""
        for num_id, phone in rows:
            # স্ট্যাটাস আপডেট
            cursor.execute("UPDATE stock SET status='Sold' WHERE id=?", (num_id,))
            # সেলস টেবিলে ইনসার্ট (OTP Forwarding এর জন্য জরুরি)
            cursor.execute("INSERT INTO sales (user_id, service, country, phone_number, sale_time) VALUES (?, ?, ?, ?, ?)",
                           (user_id, service, country, phone, now))
            numbers_display += f"📱 𝗡: `{phone}`\n"

        # ইউজারের টোটাল কেনাকাটা আপডেট
        cursor.execute("UPDATE users SET total_bought = total_bought + ? WHERE user_id=?", (len(rows), user_id))
        conn.commit()

    # কুলডাউন সেট করা
    change_num_cooldowns[user_id] = now

    # বাটনগুলো তৈরি
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔄 𝐂𝐇𝐀𝐍𝐆𝐄", callback_data=f"buy_{service}_{country}"),
        types.InlineKeyboardButton("🔔 𝐎𝐓𝐏 𝐆𝐑𝐎𝐔𝐏", url=CHANNEL_LINK)
    )
    markup.add(types.InlineKeyboardButton("🔙 Back to Services", callback_data=f"select_srv_{service}"))

    # প্রিমিয়াম ডিজাইন মেসেজ
    success_msg = (
        f"   ✨ 𝗬𝗢𝗨𝗥 𝗡𝗨𝗠𝗕𝗘𝗥 ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"┣ S: `{service}`\n"
        f"┣ C: `{country.upper()}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{numbers_display}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 𝖶𝖺𝗂𝗍𝗂𝗇𝗀 𝖥𝗈𝗋 𝖮tp.............."
    )

    try:
        bot.edit_message_text(
            success_msg, 
            call.message.chat.id, 
            call.message.message_id, 
            reply_markup=markup, 
            parse_mode="Markdown"
        )
    except Exception as e:
        # যদি কোনো কারণে মেসেজ এডিট না হয় (যেমন একই মেসেজ বারবার এডিট করা)
        print(f"Edit error: {e}")
# ====================== HANDLERS ======================
@bot.message_handler(commands=['start'])
def start(message):
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, join_date) VALUES (?, ?)", (message.from_user.id, datetime.now().strftime('%Y-%m-%d')))
        conn.commit()
    if is_subscribed(message.from_user.id):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("📱 Get Numbers", "👤 My Profile")
        bot.send_message(message.chat.id, "✨ 𝗪𝗘𝗟𝗟𝗖𝗢𝗠𝗘> 𝗠𝗥𝗦 𝗕𝗢𝗧", reply_markup=markup)
    else:
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        bot.send_message(message.chat.id, "চ্যানেলে জয়েন করে আবার /start দিন।", reply_markup=markup)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.from_user.id in user_states)
def admin_inputs(message):
    state = user_states[ADMIN_ID]
    step = state.get('step')

    if step == 'waiting_country':
        user_states[ADMIN_ID].update({'country': message.text.strip(), 'step': 'waiting_numbers'})
        bot.reply_to(message, "📍 এখন নম্বরগুলো পেস্ট করুন (Space দিয়ে দিয়ে):")

    elif step == 'waiting_numbers':
        service = state['service']
        country = state['country']
        nums = [n.strip() for n in message.text.split() if n.strip()]
        
        with get_db_connection() as conn:
            for n in nums: 
                conn.execute("INSERT INTO stock (service, country, phone_number, status) VALUES (?,?,?,'Available')", 
                             (service, country, n))
            conn.commit()
        
        bot.reply_to(message, f"✅ {len(nums)}টি নম্বর {service} ({country}) এ যোগ হয়েছে!")
        del user_states[ADMIN_ID]

    # ব্রডকাস্ট প্রসেসিং লজিক (এটিই আপনার কোডে মিসিং বা কাজ করছিল না)
    elif step == 'waiting_broadcast':
        with get_db_connection() as conn:
            users = [row[0] for row in conn.execute("SELECT user_id FROM users").fetchall()]
        
        bot.reply_to(message, f"📤 ব্রডকাস্ট শুরু হয়েছে... (মোট ইউজার: {len(users)})")
        
        success = 0
        failed = 0
        for uid in users:
            try:
                # মেসেজটি সবাইকে পাঠানো হচ্ছে
                bot.send_message(uid, message.text, parse_mode="Markdown")
                success += 1
                time.sleep(0.05) # রেট লিমিট এড়াতে সামান্য বিরতি
            except:
                failed += 1
                
        bot.send_message(message.chat.id, f"✅ ব্রডকাস্ট সম্পন্ন!\n\n🚀 সফল: {success}\n❌ ব্যর্থ: {failed}")
        del user_states[ADMIN_ID]

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_srv_"))
def admin_add_srv(call):
    user_states[ADMIN_ID] = {'service': call.data.split("_")[2], 'step': 'waiting_country'}
    bot.edit_message_text("📍 এখন দেশের নাম লিখুন:", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text == "👤 My Profile")
def my_profile(message):
    with get_db_connection() as conn:
        res = conn.execute("SELECT join_date, total_bought FROM users WHERE user_id=?", (message.from_user.id,)).fetchone()
    if res: bot.send_message(message.chat.id, f"📅 **জয়েন:** {res[0]}\n🛒 **মোট কেনা:** {res[1]} টি")

if __name__ == "__main__":
    init_db()
    print("🚀 HEI BOT V2 - Fixed & Running...")
    bot.infinity_polling()

import telebot
import sqlite3
import pandas as pd
import io
import time
from telebot import types

# --- কনফিগারেশন ---
API_TOKEN = '8630229964:AAHD_-5i34IQyZlUr4CCqQnRBiNZ-V4Njw0'
ADMIN_IDS = [6864515052, 8705862954]
DB_FILE = "bot_database.db"

bot = telebot.TeleBot(API_TOKEN)


user_cooldown = {}

# --- ডাটাবেস সেটআপ ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS numbers (
                        id INTEGER PRIMARY KEY, 
                        service_name TEXT, 
                        country TEXT, 
                        value TEXT)''')
    # নতুন লাইন: ইউজার আইডি সেভ করার জন্য
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()


# এডমিনের ডেটা সাময়িকভাবে রাখার জন্য ডিকশনারি
admin_data = {}

# --- কিবোর্ডস ---
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📱 Get Number', '🆘 Support')
    
    # আইডিটি এডমিন লিস্টে আছে কি না চেক
    if user_id in ADMIN_IDS:
        markup.row('⚙️ Admin Control')
    return markup


def cancel_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add('❌ Cancel')
    return markup


# --- কমান্ড হ্যান্ডলার ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # ইউজার আইডি ডাটাবেসে সেভ করা
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit(); conn.close()
    
    bot.send_message(message.chat.id, "বটে স্বাগতম!", reply_markup=main_menu(message.from_user.id))


# --- ইউজার সেকশন (Get Number) ---
@bot.message_handler(func=lambda message: message.text == '📱 Get Number')
def user_get_number(message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # শুধুমাত্র যে সার্ভিসে নম্বর আছে সেগুলো দেখাবে
    cursor.execute("SELECT DISTINCT service_name FROM numbers")
    services = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not services:
        bot.reply_to(message, "বর্তমানে কোনো নম্বর এভেলেবল নেই।")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for s in services:
        markup.add(types.InlineKeyboardButton(s, callback_data=f"u_serv_{s}"))
    bot.send_message(message.chat.id, "সার্ভিস বেছে নিন:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('u_serv_'))
def user_select_country(call):
    service = call.data.replace("u_serv_", "")
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT country FROM numbers WHERE service_name = ?", (service,))
    countries = [row[0] for row in cursor.fetchall()]
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=2)
    for c in countries:
        markup.add(types.InlineKeyboardButton(c, callback_data=f"u_get_{service}_{c}"))
    
    # ব্যাক বাটন যোগ করা হয়েছে
    markup.row(types.InlineKeyboardButton("🔙 Back Service", callback_data="back_to_services"))
    
    bot.edit_message_text(f"📌 সার্ভিস: {service}\nদেশ বেছে নিন:", call.message.chat.id, call.message.message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "back_to_services")
def back_to_services_handler(call):
    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT service_name FROM numbers")
    services = [row[0] for row in cursor.fetchall()]
    conn.close()

    markup = types.InlineKeyboardMarkup(row_width=2)
    for s in services:
        markup.add(types.InlineKeyboardButton(s, callback_data=f"u_serv_{s}"))
    
    bot.edit_message_text("সার্ভিস বেছে নিন:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)



@bot.callback_query_handler(func=lambda call: call.data.startswith('u_get_'))
def deliver_numbers(call):
    user_id = call.from_user.id
    current_time = time.time()

    # ১০ সেকেন্ড কোoldown চেক
    if user_id in user_cooldown:
        if current_time - user_cooldown[user_id] < 10:
            remaining = int(10 - (current_time - user_cooldown[user_id]))
            bot.answer_callback_query(call.id, f"দয়া করে {remaining} সেকেন্ড অপেক্ষা করুন।", show_alert=True)
            return

    parts = call.data.split('_')
    service, country = parts[2], parts[3]

    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("SELECT id, value FROM numbers WHERE service_name = ? AND country = ? LIMIT 2", (service, country))
    rows = cursor.fetchall()

    if len(rows) < 2:
        bot.answer_callback_query(call.id, f"দুঃখিত, পর্যাপ্ত নম্বর নেই।", show_alert=True)
        conn.close(); return

    ids = [r[0] for r in rows]; nums = [r[1] for r in rows]
    cursor.execute(f"DELETE FROM numbers WHERE id IN ({','.join(map(str, ids))})")
    conn.commit(); conn.close()

    user_cooldown[user_id] = current_time # সময় সেভ

    # বাটন সেটআপ (Change Number-এ u_change_ ডাটা দেওয়া হয়েছে)
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔄 Change Number", callback_data=f"u_change_{service}_{country}")
    btn2 = types.InlineKeyboardButton("👥 OTP Group", url="https://t.me/nrnumberotp") 
    btn3 = types.InlineKeyboardButton("🔙 Back Country", callback_data=f"u_serv_{service}")
    markup.add(btn1, btn2)
    markup.row(btn3)

    msg_text = (
        f"✅ **Number Successfully Reserved!**\n"
        f"🏳️ **Country:** {country}\n"
        f"📞 **Service:** {service}\n\n"
        f"**NUM-1:** `{nums[0]}`\n"
        f"**NUM-2:** `{nums[1]}`\n\n"
        f"⏳ **Waiting for SMS...**"
    )

    bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('u_change_'))
def change_number_handler(call):
    user_id = call.from_user.id
    current_time = time.time()

    if user_id in user_cooldown:
        if current_time - user_cooldown[user_id] < 10:
            remaining = int(10 - (current_time - user_cooldown[user_id]))
            bot.answer_callback_query(call.id, f"দয়া করে {remaining} সেকেন্ড অপেক্ষা করুন।", show_alert=True)
            return

    parts = call.data.split('_')
    service, country = parts[2], parts[3]

    conn = sqlite3.connect(DB_FILE); cursor = conn.cursor()
    cursor.execute("SELECT id, value FROM numbers WHERE service_name = ? AND country = ? LIMIT 2", (service, country))
    rows = cursor.fetchall()

    if len(rows) < 2:
        bot.answer_callback_query(call.id, "দুঃখিত, আর কোনো নতুন নম্বর নেই।", show_alert=True)
        conn.close(); return

    ids = [r[0] for r in rows]; nums = [r[1] for r in rows]
    cursor.execute(f"DELETE FROM numbers WHERE id IN ({','.join(map(str, ids))})")
    conn.commit(); conn.close()

    user_cooldown[user_id] = current_time

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔄 Change Number", callback_data=f"u_change_{service}_{country}")
    btn2 = types.InlineKeyboardButton("👥 OTP Group", url="https://t.me/your_group_link")
    btn3 = types.InlineKeyboardButton("🔙 Back Country", callback_data=f"u_serv_{service}")
    markup.add(btn1, btn2)
    markup.row(btn3)

    msg_text = (
        f"✅ **Number Successfully Changed!**\n"
        f"🏳️ **Country:** {country}\n"
        f"📞 **Service:** {service}\n\n"
        f"**NUM-1:** `{nums[0]}`\n"
        f"**NUM-2:** `{nums[1]}`\n\n"
        f"⏳ **Waiting for SMS...**"
    )

    bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id, "নম্বর পরিবর্তন করা হয়েছে!")



# সার্ভিস যোগ করা
@bot.callback_query_handler(func=lambda call: call.data == "add_ser")
def add_service_start(call):
    msg = bot.send_message(call.message.chat.id, "নতুন সার্ভিসের নাম লিখুন:", reply_markup=cancel_menu())
    bot.register_next_step_handler(msg, save_service)


def save_service(message):
    if message.text == '❌ Cancel':
        bot.send_message(message.chat.id, "❌ অপারেশন বাতিল করা হয়েছে।", reply_markup=main_menu(ADMIN_IDS))
        return

    name = message.text.strip()
    try:
        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        c.execute("INSERT INTO services (name) VALUES (?)", (name,))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, f"✅ সার্ভিস '{name}' সেভ হয়েছে।", reply_markup=main_menu(ADMIN_IDS))
    except:
        bot.send_message(message.chat.id, "এরর: এই সার্ভিসটি আগে থেকেই আছে।", reply_markup=main_menu(ADMIN_IDS))


# নম্বর যোগ করা (ধাপে ধাপে)
@bot.callback_query_handler(func=lambda call: call.data == "add_num")
def add_number_start(call):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT name FROM services"); services = [row[0] for row in c.fetchall()]
    conn.close()

    if not services:
        bot.send_message(call.message.chat.id, "আগে সার্ভিস যোগ করুন।")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for s in services: markup.add(s)
    msg = bot.send_message(call.message.chat.id, "সার্ভিস সিলেক্ট করুন:", reply_markup=markup)
    bot.register_next_step_handler(msg, get_country_step)

def get_country_step(message):
    if message.text == '❌ Cancel':
        bot.send_message(message.chat.id, "❌ অপারেশন বাতিল করা হয়েছে।", reply_markup=main_menu(ADMIN_IDS))
        return
        
    admin_data[message.from_user.id] = {'service': message.text}
    msg = bot.send_message(message.chat.id, "দেশের নাম লিখুন:", reply_markup=cancel_menu())
    bot.register_next_step_handler(msg, get_numbers_step)


def get_numbers_step(message):
    if message.text == '❌ Cancel':
        bot.send_message(message.chat.id, "❌ অপারেশন বাতিল করা হয়েছে।", reply_markup=main_menu(ADMIN_IDS))
        return

    admin_data[message.from_user.id]['country'] = message.text
    msg = bot.send_message(message.chat.id, "এখন নম্বরগুলো দিন বা ফাইল আপলোড করুন:", reply_markup=cancel_menu())
    bot.register_next_step_handler(msg, final_process_numbers)


def final_process_numbers(message):
    if message.text == '❌ Cancel':
        bot.send_message(message.chat.id, "❌ বাতিল করা হয়েছে।", reply_markup=main_menu(ADMIN_IDS))
        return
    # বাকি আগের প্রসেসিং কোড...
    user_id = message.from_user.id
    service = admin_data[user_id]['service']
    country = admin_data[user_id]['country']
    new_nums = []

    try:
        if message.content_type == 'document':
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            if message.document.file_name.endswith('.xlsx'):
                df = pd.read_excel(io.BytesIO(downloaded_file))
                new_nums = df.iloc[:, 0].astype(str).tolist()
            else: # txt
                new_nums = downloaded_file.decode('utf-8').splitlines()
        elif message.text:
            new_nums = message.text.splitlines()

        conn = sqlite3.connect(DB_FILE); c = conn.cursor()
        for n in new_nums:
            if n.strip():
                c.execute("INSERT INTO numbers (service_name, country, value) VALUES (?, ?, ?)", (service, country, n.strip()))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, f"✅ সফলভাবে {len(new_nums)}টি নম্বর যোগ করা হয়েছে।", reply_markup=main_menu(ADMIN_IDS))
    except Exception as e:
        bot.send_message(message.chat.id, f"ভুল হয়েছে: {e}")

# --- ১. এডমিন কন্ট্রোল মেনু হ্যান্ডলার (রিপ্লাই কিবোর্ড থেকে ইনলাইন মেনু ওপেন করবে) ---
@bot.message_handler(func=lambda message: message.text == '⚙️ Admin Control' and message.from_user.id in ADMIN_IDS)
def admin_control_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("➕ Add Service", callback_data="add_ser")
    btn2 = types.InlineKeyboardButton("🔢 Add Number", callback_data="add_num")
    btn3 = types.InlineKeyboardButton("📊 View Stock", callback_data="view_stk")
    btn4 = types.InlineKeyboardButton("🗑 Delete Number", callback_data="adm_del_n")
    # নতুন ব্রডকাস্ট বাটন
    btn5 = types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_brd")
    
    markup.add(btn1, btn2, btn3, btn4, btn5)
    bot.send_message(message.chat.id, "🛠 **এডমিন কন্ট্রোল প্যানেল:**", reply_markup=markup, parse_mode="Markdown")


# ধাপ ১: ডিলিট করার জন্য সার্ভিস সিলেক্ট
@bot.callback_query_handler(func=lambda call: call.data == "adm_del_n")
def delete_number_start(call):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT DISTINCT service_name FROM numbers")
    services = [row[0] for row in c.fetchall()]; conn.close()
    
    if not services:
        bot.answer_callback_query(call.id, "ডিলিট করার মতো কোনো নম্বর নেই।", show_alert=True)
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for s in services:
        markup.add(types.InlineKeyboardButton(s, callback_data=f"del_serv_{s}"))
    markup.row(types.InlineKeyboardButton("❌ Cancel", callback_data="back_to_admin"))
    
    bot.edit_message_text("🗑 কোন সার্ভিসের নম্বর ডিলিট করতে চান?", call.message.chat.id, call.message.message_id, reply_markup=markup)

# ধাপ ২: সার্ভিস সিলেক্টের পর কান্ট্রি সিলেক্ট
@bot.callback_query_handler(func=lambda call: call.data.startswith('del_serv_'))
def delete_select_country(call):
    service = call.data.replace("del_serv_", "")
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT DISTINCT country FROM numbers WHERE service_name = ?", (service,))
    countries = [row[0] for row in c.fetchall()]; conn.close()

    markup = types.InlineKeyboardMarkup(row_width=2)
    for c in countries:
        markup.add(types.InlineKeyboardButton(c, callback_data=f"del_fin_{service}_{c}"))
    markup.row(types.InlineKeyboardButton("🔙 Back", callback_data="adm_del_n"))
    
    bot.edit_message_text(f"🌍 সার্ভিস: {service}\nকোন দেশের নম্বর ডিলিট করবেন?", call.message.chat.id, call.message.message_id, reply_markup=markup)

# ধাপ ৩: কনফার্মেশন এবং ডিলিট অপারেশন
@bot.callback_query_handler(func=lambda call: call.data.startswith('del_fin_'))
def delete_confirm(call):
    parts = call.data.split('_')
    service, country = parts[2], parts[3]
    
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("DELETE FROM numbers WHERE service_name = ? AND country = ?", (service, country))
    deleted_count = c.rowcount
    conn.commit(); conn.close()
    
    bot.answer_callback_query(call.id, f"সফলভাবে {deleted_count}টি নম্বর ডিলিট হয়েছে।", show_alert=True)
    # কাজ শেষে আবার স্টক দেখাবে
    view_stock(call)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_admin")
def back_to_admin_handler(call):
    # ইনলাইন মেসেজটি ডিলিট করে নতুন করে এডমিন মেনু পাঠাবে
    bot.delete_message(call.message.chat.id, call.message.message_id)
    admin_control_menu(call.message)


# --- ২. সাপোর্ট বাটন হ্যান্ডলার ---
@bot.message_handler(func=lambda message: message.text == '🆘 Support')
def support_message(message):
    support_text = (
        "🆘 **সাপোর্ট সেন্টার**\n\n"
        "আপনার কোনো সমস্যা হলে আমাদের এডমিনের সাথে যোগাযোগ করুন।\n"
        "এডমিন আইডি: @nrrifat15170"
    )
    bot.send_message(message.chat.id, support_text, parse_mode="Markdown")



@bot.callback_query_handler(func=lambda call: call.data == "view_stk")
def view_stock(call):
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT service_name, country, COUNT(*) FROM numbers GROUP BY service_name, country")
    rows = c.fetchall(); conn.close()
    
    res = "📊 **বর্তমান স্টক:**\n"
    if not rows: res += "খালি।"
    else:
        for r in rows: res += f"- {r[0]} ({r[1]}): {r[2]} টি\n"
    bot.send_message(call.message.chat.id, res, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "adm_brd")
def broadcast_start(call):
    msg = bot.send_message(call.message.chat.id, "📢 আপনার মেসেজটি লিখুন যা সকল ইউজারকে পাঠাতে চান:", reply_markup=cancel_menu())
    bot.register_next_step_handler(msg, send_broadcast_msg)

def send_broadcast_msg(message):
    if message.text == '❌ Cancel':
        bot.send_message(message.chat.id, "❌ ব্রডকাস্ট বাতিল করা হয়েছে।", reply_markup=main_menu(ADMIN_IDS))
        return

    bot.send_message(message.chat.id, "🚀 ব্রডকাস্ট পাঠানো শুরু হচ্ছে...")
    
    conn = sqlite3.connect(DB_FILE); c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall(); conn.close()
    
    success = 0; fail = 0
    for user in users:
        try:
            bot.send_message(user[0], message.text)
            success += 1
            time.sleep(0.05) # বটের স্প্যাম ফিল্টার এড়াতে ছোট বিরতি
        except:
            fail += 1
            
    bot.send_message(message.chat.id, f"✅ ব্রডকাস্ট সম্পন্ন!", reply_markup=main_menu(message.from_user.id))



if __name__ == '__main__':
    init_db()
    bot.infinity_polling()

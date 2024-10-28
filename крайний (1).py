import telebot
import gspread
import re
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from better_profanity import profanity
import sqlite3

scheduler = BackgroundScheduler()
scheduler.start()

# Установка учетных данных для доступа к Google API
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credentials = ServiceAccountCredentials.from_json_keyfile_name('/root/hosting_bot/gugl-428613-22cdedba4515.json', scope)
client = gspread.authorize(credentials)

# Открытие таблицы с четырьмя листами
spreadsheet = client.open('Регистрация')

# Получение листов таблицы по их именам
sheet_teams = spreadsheet.worksheet('Общая таблица команд')
sheet_players = spreadsheet.worksheet('Общая таблица игроков')
sheet_invitations = spreadsheet.worksheet('Приглашения')
sheet_temp = spreadsheet.worksheet('Временная таблица')
sheet_results = spreadsheet.worksheet('Результаты')

# Токен
bot = telebot.TeleBot('7039522673:AAHT3TwC3Y6gdQhKHGYn1H7zsQShLomejKs')

# Глобальные переменные
user_data = {}
registered_users = set()
search_results = {}
confirmation_data = {}

# Функция для загрузки зарегистрированных пользователей из Google Sheets
def load_registered_users():
    registered_users = set()
    # Пропускаем первую строку с заголовками
    for row in sheet_players.get_all_values()[1:]:
        if len(row) > 3:
            registered_users.add(int(row[3]))
    for row in sheet_teams.get_all_values()[1:]:
        if len(row) > 4:
            registered_users.add(int(row[4]))
    return registered_users

# При запуске бота загружаем зарегистрированных пользователей
registered_users = load_registered_users()

# Обработчик команды /start
# Добавление кнопки "Результаты" в главное меню
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    # Проверка наличия анкеты в таблицах игроков или команд
    has_personal_profile = any(len(row) > 3 and row[3] == str(chat_id) for row in sheet_players.get_all_values())
    has_team_profile = any(len(row) > 3 and row[4] == str(chat_id) for row in sheet_teams.get_all_values())

    if not has_personal_profile and not has_team_profile:
        markup.add(KeyboardButton('Регистрация'))
    else:
        markup.add(KeyboardButton('Поиск'), KeyboardButton('Профиль'), KeyboardButton('На площадке'))
        if has_team_profile:
            markup.add(KeyboardButton('Результаты'))

    bot.send_message(chat_id, 'Привет! Добро пожаловать в бот регистрации участников на спортивный турнир.', reply_markup=markup)

# Обработчик команды /register
@bot.message_handler(func=lambda message: message.text == 'Регистрация' and message.chat.id not in registered_users)
def register(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Личная анкета'), KeyboardButton('Командная анкета'))
    bot.reply_to(message, 'Выберите тип регистрации:', reply_markup=markup)

# Обработчик выбора типа регистрации
@bot.message_handler(func=lambda message: message.text in ['Личная анкета', 'Командная анкета'])
def process_registration_type(message):
    if message.text == 'Личная анкета':
        bot.reply_to(message, 'Введите ваше имя:')
        bot.register_next_step_handler(message, process_personal_name)
    elif message.text == 'Командная анкета':
        bot.reply_to(message, 'Введите название команды:')
        bot.register_next_step_handler(message, process_team_name)

def check_profanity(text):
    return profanity.contains_profanity(text)

# Обработка ввода имени для личной анкеты
def process_personal_name(message):
    user_data[message.chat.id] = {'name': message.text}
    bot.reply_to(message, 'Введите ваш возраст:')
    bot.register_next_step_handler(message, process_personal_age)

# Обработка ввода возраста для личной анкеты
def process_personal_age(message):
    if not message.text.isdigit() or int(message.text) > 100:
        bot.reply_to(message, 'Пожалуйста, введите корректный возраст (число до 100).')
        bot.register_next_step_handler(message, process_personal_age)
        return
    user_data[message.chat.id]['age'] = message.text
    bot.reply_to(message, 'Пожалуйста, укажите удобное время для игры в формате hh:mm(например, 09:31), расскажите о себе.')
    bot.register_next_step_handler(message, process_personal_bio)

def process_team_captain_age(message):
    if not message.text.isdigit() or int(message.text) > 100:
        bot.reply_to(message, 'Пожалуйста, введите корректный возраст (число до 100).')
        bot.register_next_step_handler(message, process_team_captain_age)
        return
    user_data[message.chat.id]['captain_age'] = message.text
    bot.reply_to(message, 'Введите количество участников:')
    bot.register_next_step_handler(message, process_team_members)

def process_personal_bio(message):
    bio = message.text
    if not re.search(r'\b\d{2}:\d{2}\b', bio):
        bot.reply_to(message, 'Пожалуйста, укажите удобное время для игры в формате hh:mm.')
        bot.register_next_step_handler(message, process_personal_bio)
        return
    user_data[message.chat.id]['bio'] = bio
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Соперник"), KeyboardButton("Союзник"), KeyboardButton("Мне всё равно"))
    bot.reply_to(message, 'Ищете соперника или союзника?', reply_markup=markup)
    bot.register_next_step_handler(message, process_personal_preference)

def process_personal_preference(message):
    user_data[message.chat.id]['preference'] = message.text
    ask_level(message)

# Обработка ввода названия команды для командной анкеты
def process_team_name(message):
    user_data[message.chat.id] = {'team_name': message.text}
    bot.reply_to(message, 'Введите возраст капитана команды:')
    bot.register_next_step_handler(message, process_team_captain_age)

# Обработка ввода возраста капитана для командной анкеты
def process_team_captain_age(message):
    if not message.text.isdigit() or int(message.text) < 4 or int(message.text) > 99:
        bot.reply_to(message, 'Пожалуйста, введите корректный возраст капитана (от 4 до 99).')
        bot.register_next_step_handler(message, process_team_members)
        return
    user_data[message.chat.id]['captain_age'] = message.text
    bot.reply_to(message, 'Введите количество участников:')
    bot.register_next_step_handler(message, process_team_members)

# Обработка ввода количества участников для командной анкеты
def process_team_members(message):
    if not message.text.isdigit() or int(message.text) < 1 or int(message.text) > 30:
        bot.reply_to(message, 'Пожалуйста, введите корректное количество участников (от 1 до 30).')
        bot.register_next_step_handler(message, process_team_members)
        return
    user_data[message.chat.id]['members'] = message.text
    bot.reply_to(message, 'Расскажите о команде, в какое время удобнее всего играть(например,09:30)? Перечислите состав команды в формате: М20,Ж19,М16')
    bot.register_next_step_handler(message, process_team_bio)

def process_team_bio(message):
    bio = message.text
    if not re.search(r'\b\d{2}:\d{2}\b', bio) or not re.search(r'\b[МЖ]\d{2}\b', bio):
        bot.reply_to(message, 'Пожалуйста, укажите удобное время для игры в формате hh:mm (например,09:30) и состав команды в формате: Мвозраст,Жвозраст.')
        bot.register_next_step_handler(message, process_team_bio)
        return
    user_data[message.chat.id]['bio'] = bio
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Соперник"), KeyboardButton("Союзник"), KeyboardButton("Мне всё равно"))
    bot.reply_to(message, 'Ищете соперников или союзников?', reply_markup=markup)
    bot.register_next_step_handler(message, process_team_preference)

def process_team_preference(message):
    user_data[message.chat.id]['preference'] = message.text
    ask_level(message)

# Спрашиваем уровень игры
def ask_level(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Начинающий"), KeyboardButton("Средний"), KeyboardButton("Продвинутый"))
    bot.reply_to(message, 'Выберите ваш уровень игры:', reply_markup=markup)

# Обработчик выбора уровня игры
@bot.message_handler(func=lambda message: message.text in ['Начинающий', 'Средний', 'Продвинутый'])
def process_level(message):
    user_data[message.chat.id]['level'] = message.text.lower()
    if 'name' in user_data[message.chat.id]:
        process_personal_final(message)
    elif 'team_name' in user_data[message.chat.id]:
        process_team_final(message)

def process_personal_final(message):
    chat_id = message.chat.id
    user_data[chat_id]['tag'] = f"@{message.from_user.username}" if message.from_user.username else f"user{chat_id}"
    bot.reply_to(message, 'Регистрация личной анкеты завершена.')

    cell = sheet_players.find(str(chat_id))
    if cell:
        row_index = cell.row
        sheet_players.update_cell(row_index, 1, user_data[chat_id]['name'])
        sheet_players.update_cell(row_index, 2, user_data[chat_id]['age'])
        sheet_players.update_cell(row_index, 3, user_data[chat_id]['tag'])
        sheet_players.update_cell(row_index, 5, user_data[chat_id]['level'])
        sheet_players.update_cell(row_index, 6, user_data[chat_id]['bio'])
        sheet_players.update_cell(row_index, 7, user_data[chat_id]['preference'])
        sheet_players.update_cell(row_index, 8, 'Активна')  # Обновление статуса анкеты
    else:
        row = [user_data[chat_id]['name'], user_data[chat_id]['age'], user_data[chat_id]['tag'], chat_id, user_data[chat_id]['level'], user_data[chat_id]['bio'], user_data[chat_id]['preference'], 'Активна']
        sheet_players.append_row(row)

    registered_users.add(chat_id)
    start(message)  # Перенаправление в главное меню

# Обработка окончательных данных для командной анкеты
def process_team_final(message):
    chat_id = message.chat.id
    user_data[chat_id]['tag'] = f"@{message.from_user.username}" if message.from_user.username else f"team{chat_id}"
    bot.reply_to(message, 'Регистрация командной анкеты завершена.')

    cell = sheet_teams.find(str(chat_id))
    if cell:
        row_index = cell.row
        sheet_teams.update_cell(row_index, 1, user_data[chat_id]['team_name'])
        sheet_teams.update_cell(row_index, 2, user_data[chat_id]['captain_age'])
        sheet_teams.update_cell(row_index, 3, user_data[chat_id]['members'])
        sheet_teams.update_cell(row_index, 4, user_data[chat_id]['tag'])
        sheet_teams.update_cell(row_index, 6, user_data[chat_id]['level'])
        sheet_teams.update_cell(row_index, 7, user_data[chat_id]['bio'])
        sheet_teams.update_cell(row_index, 8, user_data[chat_id]['preference'])
        sheet_teams.update_cell(row_index, 9, 'Активна')  # Обновление статуса анкеты
    else:
        row = [user_data[chat_id]['team_name'], user_data[chat_id]['captain_age'], user_data[chat_id]['members'], user_data[chat_id]['tag'], chat_id, user_data[chat_id]['level'], user_data[chat_id]['bio'], user_data[chat_id]['preference'], 'Активна']
        sheet_teams.append_row(row)

    registered_users.add(chat_id)
    start(message)  # Перенаправление в главное меню

# Обработка нажатия кнопки "Результаты"
@bot.message_handler(func=lambda message: message.text == 'Результаты')
def results_menu(message):
    chat_id = message.chat.id
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Внести результаты'), KeyboardButton('Топ'), KeyboardButton('Главное меню'))
    bot.send_message(chat_id, 'Выберите действие:', reply_markup=markup)

# Обработка внесения результатов игры
@bot.message_handler(func=lambda message: message.text == 'Внести результаты')
def enter_results(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, 'Введите название команды, с которой играли:')
    bot.register_next_step_handler(message, process_opponent_name)

def process_opponent_name(message):
    chat_id = message.chat.id
    if message.text == 'Главное меню':
        start(message)
        return

    opponent_name = message.text
    if not check_team_exists(opponent_name):
        bot.send_message(chat_id, 'Команды с таким названием нет в таблице. Вернитесь в главное меню.')
        start(message)
        return

    user_data[chat_id] = {'opponent_name': opponent_name}
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Победа'), KeyboardButton('Поражение'))
    bot.send_message(chat_id, 'Результат игры:', reply_markup=markup)
    bot.register_next_step_handler(message, process_game_result)

def process_game_result(message):
    chat_id = message.chat.id
    if message.text == 'Главное меню':
        start(message)
        return

    if message.text not in ['Победа', 'Поражение']:
        bot.send_message(chat_id, 'Пожалуйста, выберите результат игры с помощью кнопок.')
        bot.register_next_step_handler(message, process_game_result)
        return

    user_data[chat_id]['result'] = message.text
    bot.send_message(chat_id, 'Введите счет в формате "число:число" (например, 21:17):')
    bot.register_next_step_handler(message, process_score)

def process_score(message):
    chat_id = message.chat.id
    if message.text == 'Главное меню':
        start(message)
        return

    score = message.text
    if not re.match(r'^\d{1,2}:\d{1,2}$', score) or any(int(part) >= 200 for part in score.split(':')):
        bot.send_message(chat_id, 'Пожалуйста, введите счет в правильном формате "число:число" с числами меньше 200.')
        bot.register_next_step_handler(message, process_score)
        return

    user_data[chat_id]['score'] = score
    team_name = get_team_name_by_chat_id(chat_id)
    if not team_name:
        bot.send_message(chat_id, 'Ваша команда не найдена.')
        return

    opponent_name = user_data[chat_id]['opponent_name']
    if not check_team_exists(opponent_name):
        bot.send_message(chat_id, 'Команды с таким названием нет в таблице.')
        start(message)
        return

    if team_name == opponent_name:
        bot.send_message(chat_id, 'Вы не можете отправить запрос о результатах себе же.')
        start(message)
        return

    opponent_chat_id = get_chat_id_by_team_name(opponent_name)
    if not opponent_chat_id:
        bot.send_message(chat_id, 'Чат-ID команды противника не найден.')
        start(message)
        return

    sheet_results.append_row([team_name, opponent_name, user_data[chat_id]['result'], user_data[chat_id]['score'], 'Ожидание ответа', datetime.now().strftime('%Y-%m-%d'), chat_id, opponent_chat_id])
    send_confirmation_request(chat_id, opponent_chat_id, team_name, opponent_name, user_data[chat_id]['result'], user_data[chat_id]['score'])
    bot.send_message(chat_id, 'Результаты занесены в таблицу. Ожидайте подтверждения от команды противника.')
    start(message)

def send_confirmation_request(sender_chat_id, opponent_chat_id, team_name, opponent_name, result, score):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Смотреть результаты игр'))
    bot.send_message(opponent_chat_id, 'У вас есть новые запросы на подтверждение результатов игр.', reply_markup=markup)

# Обработчик для просмотра результатов игр
@bot.message_handler(func=lambda message: message.text == 'Смотреть результаты игр')
def check_and_send_confirmation_requests(message):
    chat_id = message.chat.id
    results = sheet_results.get_all_values()
    pending_results = [row for row in results if row[7] == str(chat_id) and row[4] == "Ожидание ответа"]
    if not pending_results:
        bot.send_message(chat_id, "У вас нет новых запросов на подтверждение результатов игр.")
        start(message)
        return
    process_result(message, pending_results)

def process_result(message, results):
    chat_id = message.chat.id
    if not results:
        bot.send_message(chat_id, "Все запросы на подтверждение результатов игр обработаны.")
        start(message)
        return
    result = results.pop(0)
    team_name = result[0]
    opponent_name = result[1]
    game_result = result[2]
    score = result[3]
    row_index = find_row_index(result)

    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Подтвердить'), KeyboardButton('Не подтверждать'))
    if game_result == 'Победа':
        bot.send_message(chat_id, f'Команда {team_name} одержала победу над вашей командой. Счет: {score}. Подтвердите результат:', reply_markup=markup)
    else:
        bot.send_message(chat_id, f'Ваша команда одержала победу над командой {team_name}. Счет: {score}. Подтвердите результат:', reply_markup=markup)
    bot.register_next_step_handler(message, handle_confirmation_response, result, results, row_index)

def handle_confirmation_response(message, result, remaining_results, row_index):
    chat_id = message.chat.id
    team_name = result[0]
    opponent_name = result[1]
    game_result = result[2]
    score = result[3]
    sender_chat_id = result[6]

    if message.text == 'Подтвердить':
        update_result_status(row_index, 'Подтверждено')
        bot.send_message(chat_id, 'Результат подтвержден.')
        bot.send_message(sender_chat_id, f'Ваша победа против команды {opponent_name} подтверждена. Счет: {score}.')
    elif message.text == 'Не подтверждать':
        update_result_status(row_index, 'Отказано')
        bot.send_message(chat_id, 'Результат отклонен.')
        bot.send_message(sender_chat_id, f'Ваша победа против команды {opponent_name} отклонена.')

    process_result(message, remaining_results)

def update_result_status(row_index, status):
    sheet_results.update_cell(row_index, 5, status)

def check_team_exists(team_name):
    cell = sheet_teams.find(team_name, in_column=1)
    return cell is not None

def get_chat_id_by_team_name(team_name):
    cell = sheet_teams.find(team_name, in_column=1)
    if cell:
        return sheet_teams.cell(cell.row, 5).value
    return None

def get_team_name_by_chat_id(chat_id):
    if not isinstance(chat_id, str):
        chat_id = str(chat_id)
    cell = sheet_teams.find(chat_id, in_column=5)
    if cell:
        return sheet_teams.cell(cell.row, 1).value
    return None

def find_row_index(result):
    results = sheet_results.get_all_values()
    for i, row in enumerate(results):
        if row == result:
            return i + 1  # Индексация в Google Sheets начинается с 1
    return None

# Отображение топа команд
@bot.message_handler(func=lambda message: message.text == 'Топ')
def top_menu(message):
    chat_id = message.chat.id
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Топ побед'), KeyboardButton('Топ дней'), KeyboardButton('Топ игр'), KeyboardButton('Главное меню'))
    bot.send_message(chat_id, 'Выберите топ:', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ['Топ побед', 'Топ дней', 'Топ игр'])
def show_top(message):
    chat_id = message.chat.id
    if message.text == 'Топ побед':
        top_teams = get_top_wins()
        if top_teams:
            bot.send_message(chat_id, '🏆 Топ команд по количеству побед:\n' + '\n'.join(top_teams))
        else:
            bot.send_message(chat_id, 'Нет данных для отображения.')
    elif message.text == 'Топ дней':
        top_teams = get_top_days()
        if top_teams:
            bot.send_message(chat_id, '📅 Топ команд по количеству дней на площадке:\n' + '\n'.join(top_teams))
        else:
            bot.send_message(chat_id, 'Нет данных для отображения.')
    elif message.text == 'Топ команд по количеству игр на площадке':
        top_teams = get_top_games()
        if top_teams:
            bot.send_message(chat_id, '🎮 Топ игр:\n' + '\n'.join(top_teams))
        else:
            bot.send_message(chat_id, 'Нет данных для отображения.')

def get_top_wins():
    results = sheet_results.get_all_values()
    teams = {}
    for row in results:
        if row[4] == 'Подтверждено':
            if row[2] == 'Победа':
                if row[0] in teams:
                    teams[row[0]] += 1
                else:
                    teams[row[0]] = 1
            elif row[2] == 'Поражение':
                if row[1] in teams:
                    teams[row[1]] += 1
                else:
                    teams[row[1]] = 1
    sorted_teams = sorted(teams.items(), key=lambda x: x[1], reverse=True)
    return [f'{i+1}. {team[0]} - {team[1]} ' for i, team in enumerate(sorted_teams[:10])]

def get_top_days():
    results = sheet_results.get_all_values()
    teams = {}
    for row in results:
        if row[4] == 'Подтверждено':
            date = row[5]
            team1 = row[0]
            team2 = row[1]
            if team1 not in teams:
                teams[team1] = set()
            if team2 not in teams:
                teams[team2] = set()
            teams[team1].add(date)
            teams[team2].add(date)

    sorted_teams = sorted(teams.items(), key=lambda x: len(x[1]), reverse=True)
    return [f'{i+1}. {team[0]} - {len(team[1])} ' for i, team in enumerate(sorted_teams[:10])]

def get_top_games():
    results = sheet_results.get_all_values()
    teams = {}
    for row in results:
        if row[4] == 'Подтверждено':
            if row[0] in teams:
                teams[row[0]] += 1
            else:
                teams[row[0]] = 1
            if row[1] in teams:
                teams[row[1]] += 1
            else:
                teams[row[1]] = 1
    sorted_teams = sorted(teams.items(), key=lambda x: x[1], reverse=True)
    return [f'{i+1}. {team[0]} - {team[1]} ' for i, team in enumerate(sorted_teams[:10])]

# Обработчик команды /search
@bot.message_handler(func=lambda message: message.text == 'Поиск' and message.chat.id in registered_users)
def search(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Личные анкеты"), KeyboardButton("Командные анкеты"), KeyboardButton("Все анкеты"))
    bot.reply_to(message, 'Какие анкеты вы хотите найти?', reply_markup=markup)

# Обработчик выбора типа анкет для поиска
@bot.message_handler(func=lambda message: message.text in ['Личные анкеты', 'Командные анкеты', 'Все анкеты'])
def process_search_type(message):
    user_data[message.chat.id] = {'search_type': message.text}
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Новичок"), KeyboardButton("Средний уровень"), KeyboardButton("Профи"), KeyboardButton("Все уровни"))
    bot.reply_to(message, 'Какой уровень игры вы ищете?', reply_markup=markup)

# Обработчик выбора уровня игры для поиска
@bot.message_handler(func=lambda message: message.text in ['Новичок', 'Средний уровень', 'Профи', 'Все уровни'])
def process_search_level(message):
    level_mapping = {
        'Новичок': 'начинающий',
        'Средний уровень': 'средний',
        'Профи': 'продвинутый',
        'Все уровни': 'все уровни'
    }
    user_data[message.chat.id]['search_level'] = level_mapping[message.text]
    if user_data[message.chat.id]['search_type'] == 'Личные анкеты':
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("Младше 18"), KeyboardButton("18-24"), KeyboardButton("Старше 24"), KeyboardButton("Все возраста"))
        bot.reply_to(message, 'Какой возраст вы ищете?', reply_markup=markup)
    elif user_data[message.chat.id]['search_type'] == 'Командные анкеты':
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("Младше 18"), KeyboardButton("18-24"), KeyboardButton("Старше 24"), KeyboardButton("Все возраста"))
        bot.reply_to(message, 'Какой возраст капитана команды вы ищете?', reply_markup=markup)
    else:
        search_profiles(message)

# Обработчик выбора возраста для поиска
@bot.message_handler(func=lambda message: message.text in ['Младше 18', '18-24', 'Старше 24', 'Все возраста'])
def process_search_age(message):
    user_data[message.chat.id]['search_age'] = message.text
    search_profiles(message)

# Функция для поиска анкет
def search_profiles(message):
    search_type = user_data[message.chat.id]['search_type']
    level = user_data[message.chat.id]['search_level']
    age_range = user_data[message.chat.id].get('search_age', 'Все возраста')
    results = []

    if search_type == 'Личные анкеты' or search_type == 'Все анкеты':
        if level == 'все уровни':
            results.extend([row for row in sheet_players.get_all_values()[1:] if row[3] != str(message.chat.id) and row[7] == 'Активна'])
        else:
            results.extend([row for row in sheet_players.get_all_values()[1:] if row[4].lower() == level and row[3] != str(message.chat.id) and row[7] == 'Активна'])

    if search_type == 'Командные анкеты' or search_type == 'Все анкеты':
        if level == 'все уровни':
            results.extend([row for row in sheet_teams.get_all_values()[1:] if row[4] != str(message.chat.id) and row[8] == 'Активна'])
        else:
            results.extend([row for row in sheet_teams.get_all_values()[1:] if row[5].lower() == level and row[4] != str(message.chat.id) and row[8] == 'Активна'])

    if age_range != 'Все возраста':
        age_filter = []
        for row in results:
            if len(row) > 1 and row[1].isdigit():
                age = int(row[1])
                if age_range == 'Младше 18' and age < 18:
                    age_filter.append(row)
                elif age_range == '18-24' and 18 <= age <= 24:
                    age_filter.append(row)
                elif age_range == 'Старше 24' and age > 24:
                    age_filter.append(row)
        results = age_filter

    search_results[message.chat.id] = {'results': results, 'index': 0}
    show_next_profile(message)

# Функция для отображения следующей анкеты
def show_next_profile(message):
    chat_id = message.chat.id
    results = search_results[chat_id]['results']
    index = search_results[chat_id]['index']
    if index < len(results):
        profile = results[index]
        profile_info = get_profile_info(profile)
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("Играть!"), KeyboardButton("Отправить сообщение"), KeyboardButton("Пропуск"), KeyboardButton("Главное меню"))
        bot.send_message(chat_id, profile_info, reply_markup=markup)
        search_results[chat_id]['index'] += 1
    else:
        bot.send_message(chat_id, "Анкеты закончились. Пожалуйста, выберите другой уровень или начните новый поиск.")
        start(message)

def get_profile_info(profile):
    if len(profile) == 8:  # Личная анкета
        return f"Имя: {profile[0]}\nВозраст: {profile[1]}\nУровень игры: {profile[4]}\nО себе,удобное время для игры: {profile[5]}\nКого ищет для игр? - {profile[6]}а"
    elif len(profile) == 9:  # Командная анкета
        return f"Имя команды: {profile[0]}\nВозраст капитана: {profile[1]}\nКоличество человек в команде: {profile[2]}\nУровень игры: {profile[5]}\nО команде,удобное время для игр: {profile[6]}\nКого ищете для игр? - {profile[7]}а"
    else:
        return "Неизвестный формат анкеты"


def get_user_tag_and_chat_id(chat_id):
    # Проверяем таблицу игроков
    cell = sheet_players.find(str(chat_id))
    if cell:
        row = sheet_players.row_values(cell.row)
        return row[2], row[3]  # Возвращаем тег и chat_id из таблицы игроков

    # Проверяем таблицу команд
    cell = sheet_teams.find(str(chat_id))
    if cell:
        row = sheet_teams.row_values(cell.row)
        return row[3], row[4]  # Возвращаем тег и chat_id из таблицы команд

    return None, None  # Если не найдено, возвращаем None

# Обработчик кнопки "К следующей анкете"
@bot.message_handler(func=lambda message: message.text == 'К следующей анкете')
def handle_next_profile(message):
    chat_id = message.chat.id
    if chat_id in search_results and 'results' in search_results[chat_id]:
        show_next_profile(message)
    else:
        bot.send_message(chat_id, "Нет доступных анкет для отображения.")

# Обработчик кнопок
@bot.message_handler(func=lambda message: message.text in ['Играть!', 'Отправить сообщение', 'Пропуск', 'Главное меню'])
def handle_buttons(message):
    chat_id = message.chat.id
    if message.text == 'Играть!':
        from_tag, from_chat_id = get_user_tag_and_chat_id(chat_id)

        if not from_tag:
            bot.send_message(chat_id, "Ваш тег не найден. Пожалуйста, убедитесь, что вы зарегистрированы.")
            return

        current_index = search_results[chat_id]['index'] - 1
        results = search_results[chat_id]['results']
        profile = results[current_index]
        target_tag, target_chat_id = get_user_tag_and_chat_id(profile[3])  # Предполагаем, что chat_id находится в 4 столбце результатов поиска

        if not target_tag:
            bot.send_message(chat_id, "Анкета получателя не найдена.")
            return

        sheet_invitations.append_row([target_chat_id, chat_id, target_tag, from_tag, "Отправлено"])
        bot.send_message(target_chat_id, f"С вами хотят сыграть! Нажмите 'Смотреть приглашения', чтобы увидеть все приглашения.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('Смотреть приглашения')))
        bot.send_message(chat_id, "Ваше приглашение отправлено.")

        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("К следующей анкете"), KeyboardButton("Главное меню"))
        bot.send_message(chat_id, "Что вы хотите сделать дальше?", reply_markup=markup)

    elif message.text == 'К следующей анкете':
        show_next_profile(message)

    elif message.text == 'Главное меню':
        start(message)

    elif message.text == 'Отправить сообщение':
        results = search_results[chat_id]['results']
        index = search_results[chat_id]['index'] - 1
        profile = results[index]
        bot.send_message(chat_id, f"Вы выбрали 'Отправить сообщение' для анкеты. Введите ваше сообщение:")
        bot.register_next_step_handler(message, process_message_to_profile, profile=profile)

    elif message.text == 'Пропуск':
        show_next_profile(message)

# Обработчик для просмотра приглашений
@bot.message_handler(func=lambda message: message.text == 'Смотреть приглашения')
def view_invitations(message):
    chat_id = message.chat.id
    invitations = sheet_invitations.get_all_values()
    pending_invitations = [row for row in invitations if row[0] == str(chat_id) and row[4] == "Отправлено"]
    if not pending_invitations:
        bot.send_message(chat_id, "У вас нет новых приглашений.")
        start(message)
        return
    process_invitation(message, pending_invitations)

def process_invitation(message, invitations):
    chat_id = message.chat.id
    if not invitations:
        bot.send_message(chat_id, "Все приглашения обработаны.")
        start(message)
        return
    invitation = invitations.pop(0)
    from_chat_id = invitation[1]
    from_tag = invitation[3]
    # Найдем анкету отправителя
    sender_profile = None
    for sheet in [sheet_players, sheet_teams]:
        records = sheet.get_all_values()
        for record in records:
            if sheet == sheet_teams:  # Проверяем, что это таблица команд
                if len(record) > 4 and record[4] == from_chat_id:  # Проверяем chat_id в 5 столбце
                    sender_profile = record
                    break
            else:  # Для таблицы игроков
                if len(record) > 3 and record[3] == from_chat_id:  # Проверяем chat_id в 4 столбце
                    sender_profile = record
                    break
        if sender_profile:
            break
    if not sender_profile:
        bot.send_message(chat_id, "Анкета отправителя не найдена.")
        return
    profile_info = get_profile_info(sender_profile)
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Принять"), KeyboardButton("Отказаться"))
    bot.send_message(chat_id, f"Вам пришло приглашение поиграть.\nАнкета отправителя:\n{profile_info}\nПринять или отказаться?", reply_markup=markup)
    bot.register_next_step_handler(message, handle_invitation_response, invitation, invitations)

def handle_invitation_response(message, invitation, remaining_invitations):
    chat_id = message.chat.id
    from_chat_id = invitation[1]
    from_tag = invitation[3]
    if message.text == "Принять":
        bot.send_message(chat_id, f"Вы приняли приглашение от игрока с тегом {from_tag}.")
        bot.send_message(from_chat_id, f"Ваше приглашение принято игроком с тегом {invitation[2]}.")
        update_invitation_status(invitation, "Принято")
    elif message.text == "Отказаться":
        bot.send_message(chat_id, f"Вы отказались от приглашения от игрока.")
        update_invitation_status(invitation, "Отказано")
    process_invitation(message, remaining_invitations)

def update_invitation_status(invitation, status):
    cell = sheet_invitations.find(invitation[0])
    row_index = cell.row
    sheet_invitations.update_cell(row_index, 5, status)

# Обработка ввода сообщения для отправки
def process_message_to_profile(message, profile):
    chat_id = message.chat.id
    user_message = message.text

    # Определяем, какой тип анкеты передан в profile
    if len(profile) == 8:  # Личная анкета
        target_tag = profile[2]
        target_chat_id = profile[3]
    elif len(profile) == 9:  # Командная анкета
        target_tag = profile[3]
        target_chat_id = profile[4]
    else:
        bot.send_message(chat_id, "Неизвестный формат анкеты.")
        return

    # Получаем тег отправителя
    sender_tag, _ = get_user_tag_and_chat_id(chat_id)

    if target_tag and target_chat_id:
        try:
            bot.send_message(target_chat_id, f"Вам сообщение от игрока {sender_tag}: {user_message}")
            bot.send_message(chat_id, f"Ваше сообщение отправлено игроку {target_tag}.")
        except telebot.apihelper.ApiTelegramException as e:
            bot.send_message(chat_id, f"Не удалось отправить сообщение: {e}")
    else:
        bot.send_message(chat_id, "Анкета получателя не найдена.")

    show_next_profile(message)

# Обработчик принятия приглашения
@bot.message_handler(func=lambda message: message.text == 'Принять приглашение')
def accept_invitation(message):
    chat_id = message.chat.id
    invitations = sheet_invitations.get_all_values()
    for row in invitations:
        if row[0] == str(chat_id):
            from_chat_id = row[1]
            target_tag = row[2]
            bot.send_message(from_chat_id, f"Ваше приглашение принято! Анкета и тег: {target_tag}")
            bot.send_message(chat_id, f"Вы приняли приглашение от игрока {target_tag}. Теперь вы можете связаться с ним.")
            sheet_invitations.delete_row(invitations.index(row) + 1)
            return
    bot.send_message(chat_id, "У вас нет активных приглашений.")

# Обработчик команды "На площадке"
@bot.message_handler(func=lambda message: message.text == 'На площадке')
def on_court(message):
    chat_id = message.chat.id
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Кто на площадке?'), KeyboardButton('Я на площадке'), KeyboardButton('Главное меню'))
    bot.reply_to(message, 'Выберите действие:', reply_markup=markup)

# Обработчик кнопки "Кто на площадке?"
@bot.message_handler(func=lambda message: message.text == 'Кто на площадке?')
def who_is_on_court(message):
    chat_id = message.chat.id
    temp_profiles = sheet_temp.get_all_values()
    if not temp_profiles:
        bot.reply_to(message, 'Никто не указал время пребывания на площадке.')
        return

    for profile in temp_profiles:
        if len(profile) > 0 and profile[0] != str(chat_id):
            profile_info = get_profile_info(profile)
            bot.send_message(chat_id, profile_info)

    bot.send_message(chat_id, 'Больше никто не указал время пребывания на площадке.')

# Обработчик кнопки "Я на площадке"
@bot.message_handler(func=lambda message: message.text == 'Я на площадке')
def i_am_on_court(message):
    chat_id = message.chat.id
    has_personal_profile = any(row[3] == str(chat_id) for row in sheet_players.get_all_values())
    has_team_profile = any(row[4] == str(chat_id) for row in sheet_teams.get_all_values())

    if has_personal_profile and has_team_profile:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton('Личную анкету'), KeyboardButton('Командную анкету'))
        bot.reply_to(message, 'У вас есть обе анкеты. Какую анкету вы хотите добавить на площадку?', reply_markup=markup)
    elif has_personal_profile:
        process_profile_for_court(message, 'Личная анкета')
    elif has_team_profile:
        process_profile_for_court(message, 'Командная анкета')
    else:
        bot.reply_to(message, 'У вас нет анкет для добавления на площадку.')

# Обработчик выбора анкеты для добавления на площадку
@bot.message_handler(func=lambda message: message.text in ['Личную анкету', 'Командную анкету'])
def process_profile_for_court_handler(message):
    profile_type = message.text
    process_profile_for_court(message, profile_type)

def process_profile_for_court(message, profile_type):
    chat_id = message.chat.id
    user_data[chat_id] = {'profile_type': profile_type}
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Да'), KeyboardButton('Нет'))
    bot.reply_to(message, 'Готовы ли вы, что ваш тег будет виден другим?', reply_markup=markup)
    bot.register_next_step_handler(message, confirm_profile_for_court)

def confirm_profile_for_court(message):
    chat_id = message.chat.id
    if message.text == 'Да':
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton('Соперник'), KeyboardButton('Сокомандник'), KeyboardButton('Не имеет значения'))
        bot.reply_to(message, 'Кого вы ищете?', reply_markup=markup)
        bot.register_next_step_handler(message, process_search_type_on_court)
    elif message.text == 'Нет':
        bot.reply_to(message, 'Операция прервана. Выберите "да", чтобы завершить её.')
        on_court(message)

@bot.message_handler(func=lambda message: message.text in ['Соперник', 'Сокомандник', 'Не имеет значения'])
def process_search_type_on_court(message):
    user_data[message.chat.id]['search_type'] = message.text
    bot.reply_to(message, 'Введите время вашего прибытия на площадку (например, 09:30):')
    bot.register_next_step_handler(message, process_arrival_time)
def process_arrival_time(message):
    user_data[message.chat.id]['arrival_time'] = message.text
    bot.reply_to(message, 'Введите время вашего ухода с площадки (например, 16:00):')
    bot.register_next_step_handler(message, process_departure_time)

def process_departure_time(message):
    user_data[message.chat.id]['departure_time'] = message.text
    add_to_temp_table(message)

def add_to_temp_table(message):
    chat_id = message.chat.id
    search_type = user_data[chat_id]['search_type']
    arrival_time = user_data[chat_id]['arrival_time']
    departure_time = user_data[chat_id]['departure_time']

    # Найти анкету пользователя
    profile = find_user_profile(chat_id)
    if not profile:
        bot.reply_to(message, 'Ваша анкета не найдена.')
        return

    # Определяем тег пользователя в зависимости от типа анкеты
    if len(profile) == 8:  # Личная анкета
        tag = profile[2]  # Тег находится в третьем столбце
        profile_chat_id = profile[3]  # Чат ID находится в четвертом столбце
    elif len(profile) == 9:  # Командная анкета
        tag = profile[3]  # Тег находится в четвертом столбце
        profile_chat_id = profile[4]  # Чат ID находится в пятом столбце
    else:
        bot.reply_to(message, 'Неизвестный формат анкеты.')
        return

    # Добавить в "Временную таблицу"
    if len(profile) == 8:  # Личная анкета
        row = [chat_id, search_type, arrival_time, departure_time, profile[0], profile[1], profile_chat_id, tag, profile[4], profile[5]]
    elif len(profile) == 9:  # Командная анкета
        row = [chat_id, search_type, arrival_time, departure_time, profile[0], profile[1], profile_chat_id, tag, profile[5], profile[6]]
    sheet_temp.append_row(row)
    bot.reply_to(message, 'Ваша анкета добавлена во "Временную таблицу".')

    # Запланировать уведомления и удаление
    departure_time_dt = datetime.strptime(departure_time, '%H:%M')
    current_date = datetime.now().date()
    departure_time_full = datetime.combine(current_date, departure_time_dt.time())

    if departure_time_full < datetime.now():
        departure_time_full += timedelta(days=1)

    scheduler.add_job(send_notification_and_remove_player, 'date', run_date=departure_time_full - timedelta(minutes=20), args=[chat_id, departure_time_full])
    scheduler.add_job(send_notification_and_remove_player, 'date', run_date=departure_time_full - timedelta(minutes=10), args=[chat_id, departure_time_full])
    scheduler.add_job(send_notification_and_remove_player, 'date', run_date=departure_time_full - timedelta(minutes=5), args=[chat_id, departure_time_full])
    scheduler.add_job(send_notification_and_remove_player, 'date', run_date=departure_time_full, args=[chat_id, departure_time_full])

@bot.message_handler(func=lambda message: message.text.startswith('Продлить время'))
def extend_time(message):
    chat_id = message.chat.id
    bot.reply_to(message, 'Введите новое время ухода с площадки (например, 18:00):')
    bot.register_next_step_handler(message, update_departure_time)

def update_departure_time(message):
    chat_id = message.chat.id
    new_departure_time = message.text
    cell = sheet_temp.find(str(chat_id))
    if cell:
        sheet_temp.update_cell(cell.row, 4, new_departure_time)
        bot.reply_to(message, 'Время ухода обновлено.')

        # Перепланировать уведомления и удаление
        new_departure_time_dt = datetime.strptime(new_departure_time, '%H:%M')
        current_date = datetime.now().date()
        new_departure_time_full = datetime.combine(current_date, new_departure_time_dt.time())

        if new_departure_time_full < datetime.now():
            new_departure_time_full += timedelta(days=1)

        scheduler.add_job(send_notification_and_remove_player, 'date', run_date=new_departure_time_full - timedelta(minutes=20), args=[chat_id, new_departure_time_full])
        scheduler.add_job(send_notification_and_remove_player, 'date', run_date=new_departure_time_full - timedelta(minutes=10), args=[chat_id, new_departure_time_full])
        scheduler.add_job(send_notification_and_remove_player, 'date', run_date=new_departure_time_full - timedelta(minutes=5), args=[chat_id, new_departure_time_full])
        scheduler.add_job(send_notification_and_remove_player, 'date', run_date=new_departure_time_full, args=[chat_id, new_departure_time_full])
    else:
        bot.reply_to(message, 'Ваша анкета не найдена во "Временной таблице".')

def find_user_profile(chat_id):
    # Проверяем таблицу игроков
    cell = sheet_players.find(str(chat_id))
    if cell:
        row = sheet_players.row_values(cell.row)
        return row

    # Проверяем таблицу команд
    cell = sheet_teams.find(str(chat_id))
    if cell:
        row = sheet_teams.row_values(cell.row)
        return row

    return None

# Обработчик кнопки "Главное меню"
@bot.message_handler(func=lambda message: message.text == 'Главное меню')
def main_menu(message):
    start(message)

def get_profile_info(profile):
    if len(profile) == 8:  # Личная анкета
        return f"Имя: {profile[0]}\nВозраст: {profile[1]}\nУровень игры: {profile[4]}\nО себе: {profile[5]}"
    elif len(profile) == 9:  # Командная анкета
        return f"Название команды: {profile[0]}\nВозраст капитана: {profile[1]}\nКоличество человек: {profile[2]}\nУровень игры: {profile[5]}\nО команде: {profile[6]}"
    elif len(profile) >= 10:  # Данные из "Временной таблицы"
        search_type = profile[1]
        arrival_time = profile[2]
        departure_time = profile[3]
        return (f"Имя: {profile[4]}\nВозраст: {profile[5]}\nУровень игры: {profile[8]}\n"
                f"Удобное время для игр, информация о себе: {profile[9]}\nТег: {profile[7]}\nИщет: {search_type}а\n"
                f"С: {arrival_time}\nДо: {departure_time}")
    else:
        return "Неизвестный формат анкеты"

# Обработчик для добавления анкеты на площадку
@bot.message_handler(func=lambda message: message.text == 'Да')
def add_profile_to_court(message):
    chat_id = message.chat.id
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Соперник'), KeyboardButton('Сокомандник'), KeyboardButton('Главное меню'))
    bot.reply_to(message, 'Вы ищете соперника или сокомандника?', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'Нет')
def decline_add_profile(message):
    main_menu(message)

# Обработчик выбора типа поиска
@bot.message_handler(func=lambda message: message.text in ['Соперник', 'Сокомандник'])
def process_search_type_on_court(message):
    user_data[message.chat.id] = {'search_type': message.text}
    bot.reply_to(message, 'Введите время вашего прибытия на площадку (например, 09:30):')
    bot.register_next_step_handler(message, process_arrival_time)

def is_valid_time(time_str):
    # Проверяем, что строка соответствует формату 'HH:MM' и что часы и минуты находятся в допустимых пределах
    return re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str) is not None

def process_arrival_time(message):
    chat_id = message.chat.id
    arrival_time = message.text
    if not is_valid_time(arrival_time):
        bot.reply_to(message, 'Неверный формат времени. Пожалуйста, введите время в формате HH:MM (например, 09:30).')
        bot.register_next_step_handler(message, process_arrival_time)
        return
    user_data[chat_id]['arrival_time'] = arrival_time
    bot.reply_to(message, 'Введите время вашего ухода с площадки (например, 16:00):')
    bot.register_next_step_handler(message, process_departure_time)

def process_departure_time(message):
    chat_id = message.chat.id
    departure_time = message.text
    if not is_valid_time(departure_time):
        bot.reply_to(message, 'Неверный формат времени. Пожалуйста, введите время в формате HH:MM (например, 16:00).')
        bot.register_next_step_handler(message, process_departure_time)
        return
    user_data[chat_id]['departure_time'] = departure_time
    add_to_temp_table(message)

def add_to_temp_table(message):
    chat_id = message.chat.id
    search_type = user_data[chat_id]['search_type']
    arrival_time = user_data[chat_id]['arrival_time']
    departure_time = user_data[chat_id]['departure_time']

    # Найти анкету пользователя
    profile = find_user_profile(chat_id)
    if not profile:
        bot.reply_to(message, 'Ваша анкета не найдена.')
        return

    # Определяем тег пользователя в зависимости от типа анкеты
    if len(profile) == 8:  # Личная анкета
        tag = profile[2]  # Тег находится в третьем столбце
        profile_chat_id = profile[3]  # Чат ID находится в четвертом столбце
    elif len(profile) == 9:  # Командная анкета
        tag = profile[3]  # Тег находится в четвертом столбце
        profile_chat_id = profile[4]  # Чат ID находится в пятом столбце
    else:
        bot.reply_to(message, 'Неизвестный формат анкеты.')
        return

# Добавить в "Временную таблицу"
    if len(profile) == 8:  # Личная анкета
        row = [chat_id, search_type, arrival_time, departure_time, profile[0], profile[1], profile_chat_id, tag, profile[4], profile[5]]
    elif len(profile) == 9:  # Командная анкета
        row = [chat_id, search_type, arrival_time, departure_time, profile[0], profile[1], profile_chat_id, tag, profile[5], profile[6]]
    sheet_temp.append_row(row)
    bot.reply_to(message, 'Ваша анкета добавлена во "Временную таблицу".')

    # Запланировать уведомления и удаление
    departure_time_dt = datetime.strptime(departure_time, '%H:%M')
    current_date = datetime.now().date()
    departure_time_full = datetime.combine(current_date, departure_time_dt.time())

    if departure_time_full < datetime.now():
        departure_time_full += timedelta(days=1)

    scheduler.add_job(send_notification_and_remove_player, 'date', run_date=departure_time_full - timedelta(minutes=20000),
                      args=[chat_id, departure_time_full])
    scheduler.add_job(send_notification_and_remove_player, 'date', run_date=departure_time_full - timedelta(minutes=10000),
                      args=[chat_id, departure_time_full])
    scheduler.add_job(send_notification_and_remove_player, 'date', run_date=departure_time_full - timedelta(minutes=5000),
                      args=[chat_id, departure_time_full])
    scheduler.add_job(send_notification_and_remove_player, 'date', run_date=departure_time_full,
                      args=[chat_id, departure_time_full])

    # Возвращаем пользователя к меню "На площадке"
    on_court(message)

@bot.message_handler(func=lambda message: message.text == 'Нет')
def decline_to_show_tag(message):
    chat_id = message.chat.id
    user_data[chat_id]['show_tag'] = 'Нет'
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Соперник'), KeyboardButton('Сокомандник'), KeyboardButton('Не имеет значения'))
    bot.reply_to(message, 'Кого вы ищете?', reply_markup=markup)

def find_user_profile(chat_id):
    # Проверяем таблицу игроков
    cell = sheet_players.find(str(chat_id))
    if cell:
        row = sheet_players.row_values(cell.row)
        return row

    # Проверяем таблицу команд
    cell = sheet_teams.find(str(chat_id))
    if cell:
        row = sheet_teams.row_values(cell.row)
        return row

    return None

# Обработчик для поиска подходящих анкет
@bot.message_handler(func=lambda message: message.text == 'Поиск' and message.chat.id in registered_users)
def search_on_court(message):
    chat_id = message.chat.id
    user_profile = find_user_profile(chat_id)
    if not user_profile:
        bot.reply_to(message, 'Ваша анкета не найдена.')
        return

    # Получить все анкеты из "Временной таблицы"
    temp_profiles = sheet_temp.get_all_values()
    suitable_profiles = []

    for profile in temp_profiles:
        if len(profile) > 0 and profile[0] != str(chat_id):  # Проверка на длину списка и не показывать свою анкету
            arrival_time = datetime.strptime(profile[2], '%H:%M')
            departure_time = datetime.strptime(profile[3], '%H:%M')
            user_arrival_time = datetime.strptime(user_data[chat_id]['arrival_time'], '%H:%M')
            user_departure_time = datetime.strptime(user_data[chat_id]['departure_time'], '%H:%M')

            if arrival_time <= user_departure_time and departure_time >= user_arrival_time:
                suitable_profiles.append(profile)

    if suitable_profiles:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for profile in suitable_profiles:
            markup.add(KeyboardButton(f"Анкета {profile[0]}"))
        bot.reply_to(message, 'Найдены подходящие анкеты:', reply_markup=markup)
    else:
        bot.reply_to(message, 'Подходящих анкет не найдено.')

# Обработчик для получения тега игрока
@bot.message_handler(func=lambda message: message.text.startswith('Анкета'))
def get_player_tag(message):
    chat_id = message.chat.id
    profile_id = message.text.split(' ')[1]
    profile = sheet_temp.find(profile_id)
    if profile:
        row = sheet_temp.row_values(profile.row)
        bot.reply_to(message, f"Тег игрока: {row[4]}")
    else:
        bot.reply_to(message, 'Анкета не найдена.')

# Обработчик для продления времени на площадке
@bot.message_handler(func=lambda message: message.text.startswith('Продлить время'))
def extend_time(message):
    chat_id = message.chat.id
    bot.reply_to(message, 'Введите новое время ухода с площадки (например, 18:00):')
    bot.register_next_step_handler(message, update_departure_time)

def update_departure_time(message):
    chat_id = message.chat.id
    new_departure_time = message.text
    cell = sheet_temp.find(str(chat_id))
    if cell:
        sheet_temp.update_cell(cell.row, 4, new_departure_time)
        bot.reply_to(message, 'Время ухода обновлено.')
    else:
        bot.reply_to(message, 'Ваша анкета не найдена во "Временной таблице".')
def send_notification_and_remove_player(chat_id, departure_time):
    current_time = datetime.now()
    time_diff = (departure_time - current_time).total_seconds()

    if time_diff <= 0:
        # Удалить игрока из "временной" таблицы
        cell = sheet_temp.find(str(chat_id))
        if cell:
            sheet_temp.delete_rows(cell.row)
        bot.send_message(chat_id, "Ваше время на площадке истекло. Вы удалены из временной таблицы.")
    elif time_diff <= 5 * 60:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("Да"), KeyboardButton("Нет"), KeyboardButton("Главное меню"))
        bot.send_message(chat_id, "Ваше время на площадке истекает через 5 минут. Желаете продлить?", reply_markup=markup)
    elif time_diff <= 10 * 60:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("Да"), KeyboardButton("Нет"), KeyboardButton("Главное меню"))
        bot.send_message(chat_id, "Ваше время на площадке истекает через 10 минут. Желаете продлить?", reply_markup=markup)
    elif time_diff <= 20 * 60:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("Да"), KeyboardButton("Нет"), KeyboardButton("Главное меню"))
        bot.send_message(chat_id, "Ваше время на площадке истекает через 20 минут. Желаете продлить?", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ['Да', 'Нет', 'Главное меню'])
def handle_extend_time_response(message):
    chat_id = message.chat.id
    if message.text == 'Да':
        extend_time(message)
    elif message.text == 'Нет':
        bot.send_message(chat_id, "Вы отказались от продления времени.")
        # Удаление строки из "Временной таблицы"
        cell = sheet_temp.find(str(chat_id))
        if cell:
            sheet_temp.delete_rows(cell.row)
        start(message)  # Перенаправление в главное меню
    elif message.text == 'Главное меню':
        start(message)

# Обработчик команды для редактирования анкеты
@bot.message_handler(func=lambda message: message.text == 'Профиль' and message.chat.id in registered_users)
def edit_profile(message):
    chat_id = message.chat.id
    has_personal_profile = any(row[3] == str(chat_id) for row in sheet_players.get_all_values())
    has_team_profile = any(row[4] == str(chat_id) for row in sheet_teams.get_all_values())

    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton('Ред-ать личную анкету'), KeyboardButton('Ред-ать команду'), KeyboardButton('Приостановить анкету'), KeyboardButton('Активировать анкету'), KeyboardButton('Главное меню'))
    if not has_personal_profile:
        markup.add(KeyboardButton('Создать личную анкету'))
    if not has_team_profile:
        markup.add(KeyboardButton('Создать команду'))
    bot.reply_to(message, 'Выберите действие:', reply_markup=markup)

# Обработчик для создания второй анкеты
@bot.message_handler(func=lambda message: message.text in ['Создать личную анкету', 'Создать команду'] )
def create_second_profile(message):
    if message.text == 'Создать личную анкету':
        bot.reply_to(message, 'Введите ваше имя:')
        bot.register_next_step_handler(message, process_personal_name)
    elif message.text == 'Создать команду':
        bot.reply_to(message, 'Введите название команды:')
        bot.register_next_step_handler(message, process_team_name)

# Обработчик выбора типа анкеты для редактирования
@bot.message_handler(func=lambda message: message.text in ['Ред-ать личную анкету', 'Ред-ать команду', 'Главное меню'])
def process_edit_type(message):
    if message.text == 'Ред-ать личную анкету':
        bot.reply_to(message, 'Введите новое имя:')
        bot.register_next_step_handler(message, process_edit_personal_name)
    elif message.text == 'Ред-ать команду':
        bot.reply_to(message, 'Введите новое название команды:')
        bot.register_next_step_handler(message, process_edit_team_name)
    elif message.text == 'Главное меню':
        start(message)

@bot.message_handler(func=lambda message: message.text in ['Приостановить анкету', 'Активировать анкету'])
def toggle_profile_status(message):
    chat_id = message.chat.id
    has_personal_profile = any(row[3] == str(chat_id) for row in sheet_players.get_all_values())
    has_team_profile = any(row[4] == str(chat_id) for row in sheet_teams.get_all_values())

    if has_personal_profile and has_team_profile:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        if message.text == 'Приостановить анкету':
            markup.add(KeyboardButton('Приостановить личную анкету'), KeyboardButton('Приостановить команду'))
        elif message.text == 'Активировать анкету':
            markup.add(KeyboardButton('Активировать личную анкету'), KeyboardButton('Активировать команду'))
        bot.reply_to(message, 'Выберите анкету для изменения статуса:', reply_markup=markup)
    elif has_personal_profile:
        process_profile_status(message, 'Личная анкета')
    elif has_team_profile:
        process_profile_status(message, 'Командная анкета')
    else:
        bot.reply_to(message, 'У вас нет анкет для изменения статуса.')

@bot.message_handler(func=lambda message: message.text in ['Приостановить личную анкету', 'Приостановить команду', 'Активировать личную анкету', 'Активировать команду'])
def handle_profile_status_buttons(message):
    if message.text in ['Приостановить личную анкету', 'Активировать личную анкету']:
        process_profile_status(message, 'Личная анкета')
    elif message.text in ['Приостановить команду', 'Активировать команду']:
        process_profile_status(message, 'Командная анкета')

@bot.message_handler(func=lambda message: message.text in ['Приостановить анкету', 'Активировать анкету'])
def toggle_profile_status(message):
    chat_id = message.chat.id
    has_personal_profile = any(row[3] == str(chat_id) for row in sheet_players.get_all_values())
    has_team_profile = any(row[4] == str(chat_id) for row in sheet_teams.get_all_values())

    if has_personal_profile and has_team_profile:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        if message.text == 'Приостановить анкету':
            markup.add(KeyboardButton('Приостановить личную анкету'), KeyboardButton('Приостановить команду'))
        elif message.text == 'Активировать анкету':
            markup.add(KeyboardButton('Активировать личную анкету'), KeyboardButton('Активировать команду'))
        bot.reply_to(message, 'Выберите анкету для изменения статуса:', reply_markup=markup)
    elif has_personal_profile:
        process_profile_status(message, 'Личная анкета')
    elif has_team_profile:
        process_profile_status(message, 'Командная анкета')
    else:
        bot.reply_to(message, 'У вас нет анкет для изменения статуса.')

@bot.message_handler(func=lambda message: message.text in ['Приостановить личную анкету', 'Приостановить команду', 'Активировать личную анкету', 'Активировать команду'])
def handle_profile_status_buttons(message):
    if message.text in ['Приостановить личную анкету', 'Активировать личную анкету']:
        process_profile_status(message, 'Личная анкета')
    elif message.text in ['Приостановить команду', 'Активировать команду']:
        process_profile_status(message, 'Командная анкета')

def process_profile_status(message, profile_type):
    chat_id = message.chat.id
    action = 'Приостановить' if 'Приостановить' in message.text else 'Активировать'
    if profile_type == 'Личная анкета':
        cell = sheet_players.find(str(chat_id))
        if cell:
            row_index = cell.row
            current_status = sheet_players.cell(row_index, 8).value
            new_status = 'Приостановлена' if action == 'Приостановить' else 'Активна'
            if current_status != new_status:
                sheet_players.update_cell(row_index, 8, new_status)
                bot.reply_to(message, f'Вы решили {action.lower()} анкету.')
            else:
                bot.reply_to(message, f'Личная анкета уже {current_status.lower()}.')
    elif profile_type == 'Командная анкета':
        cell = sheet_teams.find(str(chat_id))
        if cell:
            row_index = cell.row
            current_status = sheet_teams.cell(row_index, 9).value
            new_status = 'Приостановлена' if action == 'Приостановить' else 'Активна'
            if current_status != new_status:
                sheet_teams.update_cell(row_index, 9, new_status)
                bot.reply_to(message, f'Вы решили {action.lower()} командную анкету.')
            else:
                bot.reply_to(message, f'Командная анкета уже {current_status.lower()}.')
    start(message)

# Обработка ввода нового имени для личной анкеты
def process_edit_personal_name(message):
    user_data[message.chat.id] = {'name': message.text}
    bot.reply_to(message, 'Введите новый возраст:')
    bot.register_next_step_handler(message, process_edit_personal_age)

# Обработка ввода нового возраста для личной анкеты
def process_edit_personal_age(message):
    if not message.text.isdigit() or int(message.text) > 100:
        bot.reply_to(message, 'Пожалуйста, введите корректный возраст (число до 100).')
        bot.register_next_step_handler(message, process_edit_personal_age)
        return
    user_data[message.chat.id]['age'] = message.text
    bot.reply_to(message, 'Расскажите о себе:')
    bot.register_next_step_handler(message, process_edit_personal_bio)

# Обработка ввода новой биографии для личной анкеты
def process_edit_personal_bio(message):
    bio = message.text
    if not re.search(r'\b\d{2}:\d{2}\b', bio):
        bot.reply_to(message, 'Пожалуйста, укажите удобное время для игры в формате hh:mm, расскажите о себе.')
        bot.register_next_step_handler(message, process_edit_personal_bio)
        return
    user_data[message.chat.id]['bio'] = bio
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Соперник"), KeyboardButton("Союзник"), KeyboardButton("Мне всё равно"))
    bot.reply_to(message, 'Ищете соперника или союзника?', reply_markup=markup)
    bot.register_next_step_handler(message, process_edit_personal_preference)

# Обработка ввода нового предпочтения для личной анкеты
def process_edit_personal_preference(message):
    user_data[message.chat.id]['preference'] = message.text
    ask_level(message)

# Обработка ввода нового названия команды для командной анкеты
def process_edit_team_name(message):
    user_data[message.chat.id] = {'team_name': message.text}
    bot.reply_to(message, 'Введите новый возраст капитана команды:')
    bot.register_next_step_handler(message, process_edit_team_captain_age)

# Обработка ввода нового возраста капитана для командной анкеты
def process_edit_team_captain_age(message):
    if not message.text.isdigit() or int(message.text) > 100:
        bot.reply_to(message, 'Пожалуйста, введите корректный возраст капитана (число до 100).')
        bot.register_next_step_handler(message, process_edit_team_captain_age)
        return
    user_data[message.chat.id]['captain_age'] = message.text
    bot.reply_to(message, 'Введите новое количество участников:')
    bot.register_next_step_handler(message, process_edit_team_members)

# Обработка ввода нового количества участников для командной анкеты
def process_edit_team_members(message):
    if not message.text.isdigit() or int(message.text) < 1 or int(message.text) > 30:
        bot.reply_to(message, 'Пожалуйста, введите корректное количество участников (от 1 до 30).')
        bot.register_next_step_handler(message, process_edit_team_members)
        return
    user_data[message.chat.id]['members'] = message.text
    bot.reply_to(message, 'Расскажите о команде, в какое время удобнее всего играть(например,09:30)? Перечислите состав команды в формате: М20,Ж19,М16')
    bot.register_next_step_handler(message, process_edit_team_bio)

# Обработка ввода новой биографии для командной анкеты
def process_edit_team_bio(message):
    bio = message.text
    if not re.search(r'\b\d{2}:\d{2}\b', bio) or not re.search(r'\b[МЖ]\d{2}\b', bio):
        bot.reply_to(message, 'Пожалуйста, укажите удобное время для игры в формате hh:mm и состав команды в формате (Мвозраст,Жвозраст),расскажите о себе.')
        bot.register_next_step_handler(message, process_edit_team_bio)
        return
    user_data[message.chat.id]['bio'] = bio
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Соперник"), KeyboardButton("Союзник"), KeyboardButton("Мне всё равно"))
    bot.reply_to(message, 'Ищете соперников или союзников?', reply_markup=markup)
    bot.register_next_step_handler(message, process_edit_team_preference)

# Обработка ввода нового предпочтения для командной анкеты
def process_edit_team_preference(message):
    user_data[message.chat.id]['preference'] = message.text
    ask_level(message)

# Обработчик команды для удаления анкеты
@bot.message_handler(func=lambda message: message.text == 'Удалить анкету' and message.chat.id in registered_users)
def delete_profile(message):
    chat_id = message.chat.id
    personal_profile_cell = sheet_players.find(str(chat_id), in_column=4)  # Проверяем наличие в столбце chat_id
    team_profile_cell = sheet_teams.find(str(chat_id), in_column=5)  # Проверяем наличие в столбце chat_id

    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if personal_profile_cell:
        markup.add(KeyboardButton('Удалить личную анкету'))
    if team_profile_cell:
        markup.add(KeyboardButton('Удалить команду'))
    markup.add(KeyboardButton('Главное меню'))

    if personal_profile_cell or team_profile_cell:
        bot.reply_to(message, 'Выберите анкету для удаления или вернитесь в главное меню:', reply_markup=markup)
    else:
        bot.reply_to(message, 'Ваша анкета не найдена.')

# Обработчик выбора типа анкеты для удаления
@bot.message_handler(func=lambda message: message.text in ['Удалить личную анкету', 'Удалить команду', 'Главное меню'])
def process_delete_type(message):
    chat_id = message.chat.id
    if message.text == 'Удалить личную анкету':
        try:
            cell = sheet_players.find(str(chat_id), in_column=4)
            if cell:
                sheet_players.delete_rows(cell.row)
                registered_users.remove(chat_id)
                bot.send_message(chat_id, 'Личная анкета удалена.')
            else:
                bot.send_message(chat_id, 'Ваша личная анкета не найдена.')
        except Exception as e:
            bot.send_message(chat_id, f'Ошибка при удалении личной анкеты: {e}')
        finally:
            start(message)  # Перенаправление в главное меню
            return  # Завершение функции после перенаправления

    elif message.text == 'Удалить команду':
        try:
            cell = sheet_teams.find(str(chat_id), in_column=5)
            if cell:
                sheet_teams.delete_rows(cell.row)
                registered_users.remove(chat_id)
                bot.send_message(chat_id, 'Командная анкета удалена.')
            else:
                bot.send_message(chat_id, 'Ваша командная анкета не найдена.')
        except Exception as e:
            bot.send_message(chat_id, f'Ошибка при удалении командной анкеты: {e}')
        finally:
            start(message)  # Перенаправление в главное меню
            return  # Завершение функции после перенаправления

    elif message.text == 'Главное меню':
        start(message)
        return  # Завершение функции после перенаправления

# Глобальный флаг для состояния рассылки
broadcast_active = False

# Обработчик команды для начала рассылки
@bot.message_handler(commands=['start_broadcast'])
def start_broadcast(message):
    global broadcast_active
    chat_id = message.chat.id
    if chat_id == 1720103881:
        broadcast_active = True
        bot.reply_to(message, 'Отправьте сообщение для рассылки.')
        bot.register_next_step_handler(message, process_broadcast_message)
    else:
        bot.reply_to(message, 'У вас нет прав для выполнения этой команды.')

# Обработка сообщений для рассылки
def process_broadcast_message(message):
    global broadcast_active
    chat_id = message.chat.id
    if message.text:
        broadcast_text_message(message.text)
    elif message.photo:
        broadcast_photo_message(message.photo[-1].file_id, message.caption)
    bot.reply_to(message, 'Рассылка завершена.')
    broadcast_active = False

# Функция для рассылки текстовых сообщений
def broadcast_text_message(text):
    unique_chat_ids = set()
    for row in sheet_players.get_all_values()[1:]:
        if len(row) > 3:
            unique_chat_ids.add(int(row[3]))
    for row in sheet_teams.get_all_values()[1:]:
        if len(row) > 4:
            unique_chat_ids.add(int(row[4]))

    for chat_id in unique_chat_ids:
        try:
            bot.send_message(chat_id, text)
        except Exception as e:
            print(f"Failed to send message to {chat_id}: {e}")

# Функция для рассылки изображений
def broadcast_photo_message(photo_id, caption=None):
    unique_chat_ids = set()
    for row in sheet_players.get_all_values()[1:]:
        if len(row) > 3:
            unique_chat_ids.add(int(row[3]))
    for row in sheet_teams.get_all_values()[1:]:
        if len(row) > 4:
            unique_chat_ids.add(int(row[4]))

    for chat_id in unique_chat_ids:
        try:
            bot.send_photo(chat_id, photo_id, caption=caption)
        except Exception as e:
            print(f"Failed to send photo to {chat_id}: {e}")

# Обработчик для текстовых сообщений
@bot.message_handler(content_types=['text'])
def handle_text(message):
    global broadcast_active
    if broadcast_active:
        chat_id = message.chat.id
        user_message = message.text
        bot.reply_to(message, f"Вы сказали: {user_message}")

# Обработчик для изображений
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    global broadcast_active
    if broadcast_active:
        chat_id = message.chat.id
        photo = message.photo[-1]  # Берем последнее (самое большое) изображение
        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Сохранение изображения на сервере (например, в папку 'photos')
        with open(f"photos/{photo.file_id}.jpg", 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.reply_to(message, "Изображение сохранено.")

bot.polling()
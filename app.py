from flask import Flask, render_template, request, jsonify, send_from_directory
import requests
import json
import os
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# === ФУНКЦИЯ ЗАПРОСА К ИИ ===
def ask_ai(prompt, timeout=45):
    try:
        response = requests.get(f"https://text.pollinations.ai/{prompt}", timeout=timeout)
        text = response.text
        if '"error"' in text or 'Queue full' in text or '429' in text:
            return None
        return text
    except Exception as e:
        print("Ошибка ИИ:", e)
        return None

def calculate_bju_multiple(items):
    lines = [f"{i}. {item['dish']} — {item['grams']} г" for i, item in enumerate(items, 1)]
    dishes_text = "\n".join(lines)
    prompt = f"""Ты нутрициолог. Пользователь съел:
{dishes_text}

Посчитай БЖУ и ХЕ для КАЖДОГО блюда (1 ХЕ = 10 г углеводов).
Ответь ТОЛЬКО JSON-массивом, без пояснений:
[{{"name": "Название", "grams": 150, "protein": 1.5, "fat": 0.3, "carbs": 30, "xe": 3.0}}]
Числа — для указанного веса каждого блюда. Порядок сохрани как в списке. Ровно {len(items)} элементов."""
    response = ask_ai(prompt)
    if not response:
        return None
    try:
        clean = response.replace("```json", "").replace("```", "").strip()
        start = clean.find('[')
        end = clean.rfind(']') + 1
        return json.loads(clean[start:end])
    except Exception as e:
        print("Ошибка парсинга массива:", e)
        return None

@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    if request.method == 'POST':
        dishes = request.form.getlist('dish')
        grams_list = request.form.getlist('grams')
        items = []
        for dish, grams in zip(dishes, grams_list):
            dish = dish.strip()
            if dish:
                try:
                    items.append({'dish': dish, 'grams': float(grams)})
                except ValueError:
                    pass
        if items:
            data_list = calculate_bju_multiple(items)
            if data_list:
                for data in data_list:
                    protein = float(data.get('protein', 0))
                    fat = float(data.get('fat', 0))
                    carbs = float(data.get('carbs', 0))
                    calories = round(protein * 4 + fat * 9 + carbs * 4, 0)
                    results.append({
                        'name': data.get('name', 'Блюдо'),
                        'grams': data.get('grams', 0),
                        'protein': protein,
                        'fat': fat,
                        'carbs': carbs,
                        'xe': float(data.get('xe', 0)),
                        'calories': calories
                    })
    return render_template('index.html', results=results)

@app.route('/ask_history', methods=['POST'])
def ask_history():
    data = request.get_json()
    history = data.get('history', [])
    goal = data.get('goal', 'похудеть')
    glucose = data.get('glucose', '')
    target = data.get('target', '')
    ratio = data.get('ratio', '')
    timing = data.get('timing', '')
    if not history:
        return jsonify({'answer': 'История пуста.'})
    history_text = "Питание за день:\n"
    total_cal = total_p = total_f = total_c = total_xe = 0
    for item in history:
        history_text += f"- {item['name']} {item['grams']} г: Б {item['protein']}, Ж {item['fat']}, У {item['carbs']}, ХЕ {item['xe']}, {item['calories']} ккал\n"
        total_cal += item['calories']; total_p += item['protein']
        total_f += item['fat']; total_c += item['carbs']; total_xe += item['xe']
    history_text += f"\nИТОГО: {total_cal} ккал, Б {total_p}, Ж {total_f}, У {total_c}, ХЕ {total_xe}"
    diabetes_block = ""
    if glucose or target or ratio:
        diabetes_block = "\n\n📊 ДАННЫЕ ПО ДИАБЕТУ:\n"
        if glucose: diabetes_block += f"- Текущий сахар: {glucose} ммоль/л\n"
        if target: diabetes_block += f"- Целевой: {target} ммоль/л\n"
        if ratio: diabetes_block += f"- Углеводный коэффициент: {ratio} ЕД/ХЕ\n"
        if timing: diabetes_block += f"- Измерение: {timing}\n"
        if ratio and total_xe:
            try:
                diabetes_block += f"- На {total_xe:.1f} ХЕ примерно {float(ratio)*total_xe:.1f} ЕД инсулина (справочно!)\n"
            except: pass
    prompt = f"""Ты диетолог-эндокринолог. Помогаешь человеку с диабетом 1 типа.

{history_text}{diabetes_block}

Цель: {goal}.
Дай подробный анализ (6-8 предложений): оценка рациона, комментарий по глюкозе, справочная оценка инсулина, что убрать, что добавить, совет.
ВАЖНО: напоминай, что расчёт инсулина справочный, решение принимает врач."""
    answer = ask_ai(prompt)
    return jsonify({'answer': answer or 'ИИ сейчас загружен.'})

# === ЧАТ С АПЕЛЬСИНЧИКОМ ===
@app.route('/chat', methods=['POST'])
def mascot_chat():
    data = request.get_json()
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'answer': 'Напиши что-нибудь! 🍊'})
    prompt = f"""Ты — милый апельсинчик по имени Апельсинчик. Ты живёшь на сайте-калькуляторе БЖУ и ХЕ.
Отвечай коротко (2-4 предложения), дружелюбно, с юмором. Можешь использовать эмодзи.
Ты помогаешь с вопросами о питании, здоровье, диабете, а также можешь просто поболтать.
Вопрос пользователя: {message}"""
    answer = ask_ai(prompt)
    return jsonify({'answer': answer or 'Ой, я задумался... Попробуй ещё раз! 🍊'})

# === ПОИСК ПРОДУКТА ПО ШТРИХКОДУ ===
@app.route('/barcode/<code>')
def barcode_lookup(code):
    try:
        r = requests.get(f'https://world.openfoodfacts.org/api/v0/product/{code}.json', timeout=10)
        data = r.json()
        if data.get('status') == 1:
            p = data['product']
            n = p.get('nutriments', {})
            return jsonify({
                'name': p.get('product_name') or p.get('generic_name') or 'Продукт',
                'protein': round(float(n.get('proteins_100g', 0) or 0), 1),
                'fat': round(float(n.get('fat_100g', 0) or 0), 1),
                'carbs': round(float(n.get('carbohydrates_100g', 0) or 0), 1),
            })
        return jsonify({'error': 'Продукт не найден'}), 404
    except Exception as e:
        print("Ошибка штрихкода:", e)
        return jsonify({'error': 'Сервис недоступен'}), 500

# === ОТПРАВКА ОТЧЁТА НА ПОЧТУ ===
@app.route('/send_email', methods=['POST'])
def send_email_route():
    data = request.get_json()
    to = data.get('to', '').strip()
    content = data.get('content', '')
    if not to or '@' not in to:
        return jsonify({'error': 'Введите корректный email'}), 400
    user = os.environ.get('SMTP_USER')
    pwd = os.environ.get('SMTP_PASSWORD')
    if not user or not pwd:
        return jsonify({'error': 'Отправка на почту пока не настроена на сервере'}), 400
    try:
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = 'Отчёт о питании — Калькулятор БЖУ и ХЕ'
        msg['From'] = user
        msg['To'] = to
        with smtplib.SMTP_SSL('smtp.yandex.ru', 465, timeout=15) as s:
            s.login(user, pwd)
            s.send_message(msg)
        return jsonify({'ok': True})
    except Exception as e:
        print("Ошибка почты:", e)
        return jsonify({'error': f'Не удалось отправить: {str(e)}'}), 500

# === PWA ===
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

if __name__ == '__main__':
    app.run(debug=True)

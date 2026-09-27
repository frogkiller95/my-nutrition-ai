from flask import Flask, render_template, request, jsonify
import requests
import json

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

# === РАСЧЁТ НЕСКОЛЬКИХ БЛЮД ===
def calculate_bju_multiple(items):
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['dish']} — {item['grams']} г")
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
        print("Ошибка парсинга массива:", e, "Ответ:", response)
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

# === АНАЛИЗ ИСТОРИИ + ГЛЮКОЗЫ ЧЕРЕЗ ИИ ===
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
        return jsonify({'answer': 'История пуста. Сначала добавьте блюда.'})
    
    history_text = "Питание за день:\n"
    total_cal = 0
    total_p = total_f = total_c = total_xe = 0
    
    for item in history:
        history_text += f"- {item['name']} {item['grams']} г: Б {item['protein']}, Ж {item['fat']}, У {item['carbs']}, ХЕ {item['xe']}, {item['calories']} ккал\n"
        total_cal += item['calories']
        total_p += item['protein']
        total_f += item['fat']
        total_c += item['carbs']
        total_xe += item['xe']
    
    history_text += f"\nИТОГО: {total_cal} ккал, Б {total_p} г, Ж {total_f} г, У {total_c} г, ХЕ {total_xe}"
    
    diabetes_block = ""
    if glucose or target or ratio:
        diabetes_block = "\n\n📊 ДАННЫЕ ПО ДИАБЕТУ:\n"
        if glucose:
            diabetes_block += f"- Текущий уровень глюкозы: {glucose} ммоль/л\n"
        if target:
            diabetes_block += f"- Целевой уровень: {target} ммоль/л\n"
        if ratio:
            diabetes_block += f"- Углеводный коэффициент: {ratio} ЕД инсулина на 1 ХЕ\n"
        if timing:
            diabetes_block += f"- Измерение: {timing}\n"
        
        if ratio and total_xe:
            try:
                estimated_insulin = float(ratio) * total_xe
                diabetes_block += f"- На {total_xe:.1f} ХЕ по коэффициенту {ratio} выходит примерно {estimated_insulin:.1f} ЕД инсулина (справочно!)\n"
            except:
                pass
    
    prompt = f"""Ты диетолог-эндокринолог. Помогаешь человеку с диабетом 1 типа.

{history_text}{diabetes_block}

Цель пользователя: {goal}.

Дай подробный анализ (6-8 предложений):
1. Общая оценка рациона (что хорошо, что плохо).
2. Если есть данные по глюкозе — прокомментируй уровень и связь с едой.
3. Если есть углеводный коэффициент — дай справочную оценку инсулина на съеденное (с оговоркой, что решение принимает врач).
4. Что убрать или уменьшить.
5. Что добавить.
6. Общий совет с учётом цели.

ВАЖНО: Всегда напоминай, что расчёт инсулина — только справочный, и решение принимает лечащий врач.
Отвечай простым языком, без сложных терминов."""
    
    answer = ask_ai(prompt)
    return jsonify({'answer': answer or 'ИИ сейчас загружен, попробуйте через минуту.'})

if __name__ == '__main__':
    app.run(debug=True)

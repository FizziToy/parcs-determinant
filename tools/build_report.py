"""Build the Ukrainian report from recorded local and historical data.

Run with the bundled artifact Python and pass bundled Node/package paths.
All output is placed in a NEW directory; existing reports are preserved.
"""
import argparse
import csv
import json
import math
import statistics
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from reportlab.graphics import renderSVG
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.lib import colors

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def medians(rows, key, value='seconds'):
    grouped = {}
    for row in rows:
        grouped.setdefault(tuple(row[k] for k in key), []).append(float(row[value]))
    return {k: statistics.median(v) for k, v in grouped.items()}


def chart(path, title, series, ylabel, xmax=4, ymax=None, missing=False):
    drawing = Drawing(600, 265)
    drawing.add(String(300, 246, title, textAnchor='middle', fontName='Helvetica', fontSize=12))
    drawing.add(String(15, 224, ylabel, fontName='Helvetica', fontSize=10))
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 62, 54, 500, 158
    plot.xValueAxis.valueMin = 1 if xmax == 4 else 128
    plot.xValueAxis.valueMax = xmax
    plot.xValueAxis.valueSteps = [1, 2, 3, 4] if xmax == 4 else [128, 256, 512]
    plot.yValueAxis.valueMin = 0
    if ymax:
        plot.yValueAxis.valueMax = ymax
        plot.yValueAxis.valueSteps = [ymax * n / 4 for n in range(5)]
    plot.xValueAxis.labels.fontSize = plot.yValueAxis.labels.fontSize = 10
    plot.yValueAxis.visibleGrid = True
    plot.yValueAxis.gridStrokeColor = colors.HexColor('#dddddd')
    palette = [colors.HexColor('#24567a'), colors.HexColor('#666666'), colors.HexColor('#0d714b')]
    plot.data = [points for _, points in series]
    for i, (label, _) in enumerate(series):
        plot.lines[i].strokeColor = palette[i % len(palette)]
        plot.lines[i].strokeWidth = 1.8
        drawing.add(String(70 + i*178, 15, label, fillColor=palette[i % len(palette)], fontSize=10))
    if series:
        drawing.add(plot)
    else:
        # Empty axes only: do not invent zero-valued observations for missing runs.
        drawing.add(Line(62, 54, 562, 54))
        drawing.add(Line(62, 54, 62, 212))
        for worker in (1, 2, 3, 4):
            x = 62 + (worker - 1)*500/3
            drawing.add(Line(x, 51, x, 54))
            drawing.add(String(x, 40, str(worker), textAnchor='middle', fontSize=10))
    drawing.add(String(310, 31, 'Workers' if xmax == 4 else 'Matrix size n',
                       textAnchor='middle', fontSize=10))
    if missing:
        drawing.add(String(310, 144, 'No optimized PARCS measurements',
                           textAnchor='middle', fontSize=15, fillColor=colors.HexColor('#555555')))
        drawing.add(String(310, 120, '12 configurations / 36 repeats are NOT RUN',
                           textAnchor='middle', fontSize=12))
    renderSVG.drawToFile(drawing, str(path))


def table(doc, headers, rows, widths=None):
    result = doc.add_table(rows=1, cols=len(headers))
    result.autofit = False
    if widths:
        for col, width in zip(result.columns, widths):
            col.width = Inches(width)
        preferred = result._tbl.tblPr.find(qn('w:tblW'))
        preferred.set(qn('w:type'), 'dxa')
        preferred.set(qn('w:w'), str(Inches(sum(widths)).twips))
    for cell, text in zip(result.rows[0].cells, headers):
        cell.text = str(text)
        props = cell._tc.get_or_add_tcPr()
        shade = OxmlElement('w:shd')
        shade.set(qn('w:fill'), 'EEEEEE')
        props.append(shade)
    repeat = OxmlElement('w:tblHeader')
    result.rows[0]._tr.get_or_add_trPr().append(repeat)
    for values in rows:
        for cell, text in zip(result.add_row().cells, values):
            cell.text = str(text)
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        element = OxmlElement('w:' + edge)
        for attr, value in [('val', 'single'), ('sz', '4'), ('color', 'D9D9D9')]:
            element.set(qn('w:' + attr), value)
        borders.append(element)
    result._tbl.tblPr.append(borders)
    for row in result.rows:
        if widths:
            for cell, width in zip(row.cells, widths):
                cell.width = Inches(width)
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.paragraph_format.space_after = Pt(4)
                paragraph.paragraph_format.space_before = Pt(4)
                for run in paragraph.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(10)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return result


def equation(doc, text):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    formula = OxmlElement('m:oMath')
    run = OxmlElement('m:r')
    node = OxmlElement('m:t')
    node.text = text
    run.append(node)
    formula.append(run)
    paragraph._p.append(formula)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--node', required=True)
    parser.add_argument('--node-modules', required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    assets = args.out / 'charts'
    assets.mkdir()
    kernel_rows = read_csv(ROOT / 'experiments/local_kernels_20261118/raw.csv')
    exact_rows = read_csv(ROOT / 'experiments/local_exact_20261118/raw.csv')
    kernels = medians(kernel_rows, ['size', 'kernel'])
    exact = medians(exact_rows, ['size'])
    historical = [json.loads((ROOT / ('outputs/n128_p%d.txt' % w)).read_text()) for w in range(1, 5)]
    for metric, label, filename, ymax in [
        ('parallel_median_s', 'seconds', 'historical_time', 3.2),
        ('speedup', 'Tseq / Tpar', 'historical_speedup', 4),
        ('efficiency', 'S / workers', 'historical_efficiency', 1.2),
    ]:
        series = [('PARCS n=128 old solver', [(i+1, d[metric]) for i, d in enumerate(historical)])]
        if filename == 'historical_time':
            series.append(('sequential old solver', [(i+1, d['sequential_median_s']) for i, d in enumerate(historical)]))
        chart(assets / (filename + '.svg'), 'HISTORICAL CLOUD / original solver', series, label, ymax=ymax)
        chart(assets / (filename.replace('historical', 'optimized') + '.svg'),
              'OPTIMIZED PARCS / missing data', [], label, ymax=ymax, missing=True)
    chart(assets / 'local_kernel_speedup.svg', 'LOCAL kernel speedup / one prime / 3 repeats',
          [(name, [(n, kernels[(str(n), 'original_python')] / kernels[(str(n), key)])
                   for n in (128, 256, 512)])
           for name, key in [('Python optimized', 'optimized_python'), ('NumPy int64', 'numpy_int64')]],
          'Original time / kernel time', xmax=512, ymax=32)
    for svg in assets.glob('*.svg'):
        subprocess.run([args.node, str(ROOT / 'tools/render_svg.cjs'), args.node_modules,
                        str(svg), str(svg.with_suffix('.png'))], check=True)
    # Separate CSVs make provenance obvious even outside the DOCX.
    with (args.out / 'local_kernel_summary.csv').open('x', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle)
        writer.writerow(['environment', 'size', 'original_python_s', 'optimized_python_s', 'numpy_s', 'numpy_kernel_speedup'])
        for n in ('128', '256', '512'):
            original, optimized, numpy = [kernels[(n, key)] for key in ('original_python', 'optimized_python', 'numpy_int64')]
            writer.writerow(['local_not_parcs', n, original, optimized, numpy, original/numpy])
    with (args.out / 'historical_128_summary.csv').open('x', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle)
        writer.writerow(['source', 'workers', 'sequential_median_s', 'parallel_median_s', 'speedup', 'efficiency'])
        for d in historical:
            writer.writerow(['historical_original_solver', d['workers'], d['sequential_median_s'],
                             d['parallel_median_s'], d['speedup'], d['efficiency']])

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(.72)
    section.left_margin = section.right_margin = Inches(.85)
    normal = doc.styles['Normal']
    normal.font.name, normal.font.size = 'Times New Roman', Pt(12)
    normal.paragraph_format.line_spacing = 1.12
    normal.paragraph_format.space_after = Pt(7)
    for name in ('Title', 'Subtitle', 'Heading 1', 'Heading 2'):
        style = doc.styles[name]
        style.font.name = 'Times New Roman'
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.size = Pt(16 if name == 'Title' else 13)
        style.paragraph_format.space_after = Pt(8)
    # The bundled default DOCX has theme fonts and a title paragraph border.
    # Remove both so Word renders the requested plain student formatting.
    for border in doc.styles.element.xpath('.//w:pBdr'):
        border.getparent().remove(border)
    for name in ('Normal', 'Title', 'Subtitle', 'Heading 1', 'Heading 2'):
        fonts = doc.styles[name].element.get_or_add_rPr().get_or_add_rFonts()
        for attr in list(fonts.attrib):
            if 'theme' in attr.lower():
                del fonts.attrib[attr]
        for script in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
            fonts.set(qn('w:' + script), 'Times New Roman')
    doc.core_properties.title = 'Точне паралельне обчислення визначника матриці у PARCS Python'
    doc.core_properties.subject = 'Лабораторна робота з хмарних обчислень'
    doc.core_properties.author = ''
    def p(text):
        return doc.add_paragraph(text)
    def h(text):
        return doc.add_heading(text, level=1)
    def page():
        doc.add_page_break()
    def picture(name, caption, width=6.25):
        doc.add_picture(str(assets / name), width=Inches(width))
        paragraph = p(caption)
        paragraph.paragraph_format.space_after = Pt(7)
        for run in paragraph.runs:
            run.font.size = Pt(10)

    doc.add_paragraph('Київський національний університет імені Тараса Шевченка\n'
                      'Факультет комп’ютерних наук та кібернетики\nДисципліна Хмарні обчислення')
    doc.add_paragraph('Точне паралельне обчислення визначника матриці у PARCS Python', 'Title')
    p('Звіт до лабораторної роботи № 1\nВиконав(ла) [ПІБ]   Група [ГРУПА]\nКиїв 2026   Оновлено 19 листопада 2026 року')
    h('1 Мета та постановка задачі')
    p('Мета роботи — перевірити та прискорити точне обчислення визначника цілочисельної матриці '
      'в PARCS-Python і підготувати вимірювання на Google Cloud. Збережено модульний метод Гауса '
      'та відновлення китайською теоремою про лишки. Локальні перевірки й повні розрахунки '
      'для 128×128, 256×256 і 512×512 виконано. Нова хмарна серія поки не запускалася.')
    p('Вихідний проєкт: github.com/FizziToy/parcs-determinant, гілка refactor-parallel, '
      'початковий коміт e35ca13. Старі результати збережено окремо. Зміни не опубліковано через push.')
    h('2 Математичний метод')
    p('Для кожного простого модуля p обчислюється залишок визначника методом Гауса над скінченним '
      'полем. Якщо опорний елемент нульовий, шукається ненульовий нижче й переставляються рядки. '
      'Перестановка змінює знак; визначник дорівнює добутку опорних елементів з урахуванням знака. '
      'Ненульовий елемент має обернений, який знаходиться модульним піднесенням до степеня p − 2.')
    p('Нульовий результат за одним модулем ще не означає нульовий цілий визначник. Потрібно '
      'зібрати всі залишки. Для вибору достатньої кількості модулів використовується межа Адамара.')
    equation(doc, '|det A|² ≤ B² = ∏ᵢ (∑ⱼ aᵢⱼ²)       M = ∏ᵢ pᵢ       M² > 4B²')
    p('Отже, M > 2|det A|. CRT однозначно відновлює визначник у симетричному інтервалі '
      'від −M/2 до M/2. Межа й добутки обчислюються цілими числами довільної точності. '
      'Умова зупинки не залежить від випадкового збігу залишків і не використовує округлення.')

    page()
    h('3 Архітектура паралельного розв’язку')
    p('Master лише координує: читає конфігурацію, передає дані, запускає RPC, вимірює час '
      'і записує відповіді. Worker 1 готує матрицю та прості модулі. Map виконується '
      'на вибраних workers. Після отримання залишків Master передає їх Worker 1 для '
      'Reduce і відновлення CRT. Математичні функції на Master не викликаються.')
    table(doc, ['Компонент', 'Функції'], [
        ['Master', 'solve   координація RPC   таймер   запис Output'],
        ['Підготовка Worker', 'prepare_problem   матриця   межа Адамара   модулі'],
        ['Map і Worker', 'mymap та det_mod_batch   залишки за виділеними модулями'],
        ['Reduce на Worker', 'reduce_determinant   перевірка залишків   CRT'],
        ['Pyro4 RPC', 'Одночасні виклики через потоки на master'],
    ], [1.5, 5.2])
    p('Потоки перекривають мережеві виклики. Самі обчислення виконуються у процесах віддалених '
      'воркерів. Метод det_mod_batch, клас Solver і схема JSON Input/Output залишилися сумісними '
      'з наявним PARCS. Файл solver.py збирається скриптом build_solver.py із чотирьох модулів src.')
    h('Розподіл частин матриці')
    p('Коректний розподілений метод Гауса за блоками рядків можливий. Для кожного простого модуля '
      'потрібно спільно вибрати pivot, узгодити перестановки, передати опорний рядок і оновити '
      'локальні рядки. Це створює приблизно n залежних кроків обміну на один модуль. '
      'Ефективність такого варіанта на невеликому кластері PARCS потребує окремих вимірювань.')
    p('Обчислення визначників незалежних блоків із подальшим множенням для загальної матриці '
      'неправильне. Рядкові блоки зазвичай прямокутні; навіть добуток квадратних діагональних '
      'блоків не враховує позадіагональні зв’язки. Наприклад, визначник матриці [[1,2],[3,4]] '
      'дорівнює −2, а добуток діагональних елементів дорівнює 4.')
    p('Формула через доповнення Шура також потребує оберненого опорного блока та спільного '
      'обчислення доповнення. Блок може бути сингулярним за окремим модулем. Тому залишено '
      'розподіл незалежних простих модулів: для потрібних розмірів їх достатньо для 1–4 воркерів.')

    page()
    h('4 Оптимізація та перевірка реалізації')
    p('Початкові 11 тестів пройшли. Виявлено обмеження генератора розміром 400, яке забороняло '
      '512×512; тепер дозволено 512. Основна причина повільного виконання — потрійний Python-цикл '
      'для кожного простого модуля. Складність становить O(k n³). У локальних матриць кількість '
      'модулів становить 26, 56 та 120, тому зростання роботи набагато більше, ніж лише збільшення n.')
    p('Python-ядро кешує опорний рядок і оновлює хвости рядків через list comprehension. '
      'Для нульових множників обчислення пропускаються. Цей варіант працює без NumPy.')
    p('За наявності NumPy для розміру від 32 використовується точне ядро int64. Оновлення '
      'підматриці обчислюється зовнішнім добутком, а робочий буфер використовується повторно. '
      'Вхідні елементи спочатку зводяться за модулем у Python, тому великі цілі не переповнюються '
      'під час перетворення. Плаваюча кома та numpy.linalg.det не використовуються.')
    equation(doc, '0 ≤ aᵢⱼ + cᵢ aₖⱼ ≤ (p − 1) + (p − 1)² = p(p − 1) ≤ 2⁶³ − 1')
    p('Множник c обирається для додавання за модулем p. Наведена перевірка гарантує відсутність '
      'переповнення int64; якщо модуль завеликий, обирається Python-ядро. Після кожного оновлення '
      'підматриця знову зводиться за модулем. Математичний алгоритм і точність не змінено.')
    p('Reduce додатково відхиляє нецілі та неканонічні залишки. Таймер використовує perf_counter '
      'там, де він доступний, і сумісний time.time у Python 2. Результати та вхідні файли '
      'нових інструментів захищені від перезапису.')
    h('Локальні тести')
    p('Після змін пройдено 28 тестів із NumPy. У середовищі без NumPy пройдено 25 тестів, '
      'а 3 перевірки необов’язкового ядра явно пропущено. Перевірено відомі визначники, '
      'випадкові матриці за незалежним методом Барейса, малі прості поля, перестановки рядків, '
      'великі цілі, межу int64, збереження входу та від’ємний визначник трикутної матриці 512×512.')
    p('Тести оркестрації перевіряють одночасність викликів, помилки воркерів і структуру '
      'результатів. Тести HTTP перевіряють подання, завантаження, походження даних і продовження '
      'без повторного подання. Окремо перевірено заборону математики на Master та '
      'відсутність локального fallback. Це локальні моделі відповідей, а не вимірювання PARCS.')

    page()
    h('5 Середовище та методика експериментів')
    p('Локальне середовище: Windows 11, CPython 3.12.14, NumPy 2.3.5. Дані нижче отримано '
      'фактичним виконанням, seed=2026, елементи від −9 до 9, по три повторення. '
      'Початкове ядро завантажено з коміту e35ca13; порядок порівняння ядер чергувався.')
    p('Хмарний кластер за наданими даними: Google Cloud, проєкт parcs-514519, зона us-central1-a, '
      'parcs-master і чотири parcs-worker. Доступ налаштований у браузерному Cloud Shell через '
      'SSH-тунель на порт 8080. Фактичні типи ВМ, CPU/RAM і digest образу ще потрібно '
      'зафіксувати скриптом check_existing_cluster.sh перед новою серією.')
    p('Штатний PARCS використовує старе Python-середовище без NumPy у переліку залежностей. '
      'Для Python 2.7 підготовлено необов’язкове встановлення NumPy 1.16.6 на чотири workers. '
      'Його роботу в хмарі ще потрібно перевірити контрольним завданням. Для порівняння '
      'на чотирьох воркерах має працювати однакове ядро; Master не потребує NumPy.')
    h('6 Фактичні локальні результати')
    p('Таблиця 1. Медіана часу одного модульного визначника, включно з копіюванням матриці. '
      'Останній стовпець порівнює ядра на одному комп’ютері й не є прискоренням за воркерами.')
    kernel_table = []
    for n in ('128', '256', '512'):
        old, py, np = [kernels[(n, key)] for key in ('original_python', 'optimized_python', 'numpy_int64')]
        kernel_table.append([n, '%.6f' % old, '%.6f' % py, '%.6f' % np, '%.2f' % (old/np)])
    table(doc, ['n', 'Початкове\nPython с', 'Оновлене\nPython с', 'NumPy с', 'Відношення\nчасів'], kernel_table,
          [.45, 1.5, 1.5, 1.3, 1.6])
    p('Таблиця 2. Попередні локальні перевірки ядра від 18 листопада, поза PARCS. Підготовка матриці та '
      'модулів поза таймером. У кожному розмірі всі три цілі результати збіглися.')
    table(doc, ['n', 'Модулів', 'Повторень', 'Медіана с'],
          [[n, next(r['prime_count'] for r in exact_rows if r['size'] == n), 3,
            '%.6f' % exact[(n,)]] for n in ('128', '256', '512')], [.7, 1.2, 1.4, 2.2])
    p('Додатковий залишок за простим 1000000009 перевірено Python-ядром; він не входив '
      'до набору CRT. Гарантію точності дає межа Адамара. Це додаткова перевірка реалізації. '
      'Через відмінності random.randint між версіями Python однаковий seed не гарантує '
      'тотожності локальної та історичної хмарної матриць.')

    page()
    h('Нова хмарна серія')
    p('Підготовлено 12 конфігурацій і 36 пар вимірювань. Для кожної конфігурації Solver '
      'тричі порівнює один віддалений worker із p workers на тій самій матриці. Порядок '
      'у парі чергується. У цій сесії доступу до Cloud Shell немає, тому нових результатів '
      'PARCS немає. Пропуски в CSV порожні, а не заповнені нулями або оцінками.')
    table(doc, ['n', 'Воркери', 'Повтори', 'T1 RPC с', 'Tp RPC с', 'Статус'],
          [[n, w, 3, '—', '—', 'Не запущено'] for n in (128, 256, 512) for w in (1, 2, 3, 4)],
          [.6, .8, .8, .9, .9, 2.1])
    p('Медіана трьох часів є підсумковим показником. Прискорення визначається як '
      'S(p) = T1_remote / Tp_remote, ефективність як E(p) = S(p) / p. Для контролю стабільності '
      'потрібно переглядати також усі три початкові значення, а не лише медіану.')
    p('Поля sequential_* збережено для сумісності: це один віддалений worker. Обидва режими '
      'включають серіалізацію матриці, RPC, очікування Map і Reduce/CRT на worker. Генерація, '
      'добір модулів, підготовка воркерів та черга PARCS не входять до цих внутрішніх '
      'вимірювань. Це не повний час завдання від його подання до завершення.')
    p('Скрипт run_cloud_experiments.py подає завдання по одному й перевіряє Code/Input '
      'після завантаження. Зберігається JSON Output та SHA256 походження. Аналіз приймає '
      'лише результати відповідного плану. Старі вимірювання не додаються до цієї серії.')

    page()
    h('Історичні результати PARCS для 128 на 128')
    p('Наведено наявні файли outputs/n128_p1.txt … n128_p4.txt початкової реалізації. '
      'Це стара методика з базою на Master; вона не порівнюється з новою базою на worker. '
      'Кожна конфігурація містить три повторення.')
    table(doc, ['Воркери', 'Tseq с', 'Tpar с', 'S', 'E'],
          [[d['workers']] + ['%.4f' % d[key] for key in ('sequential_median_s', 'parallel_median_s', 'speedup', 'efficiency')]
           for d in historical], [1, 1.3, 1.3, 1.2, 1.2])
    picture('historical_time.png', 'Рисунок 1. Історичні медіани часу 128×128.', width=5.9)
    picture('historical_speedup.png', 'Рисунок 2. Історичне прискорення 128×128.', width=5.9)
    p('Історичні вимірювання вважаються нестабільними. Ці значення не доводять надлінійного '
      'прискорення та не дозволяють передбачити час нового алгоритму на 256×256 чи 512×512.')

    page()
    picture('historical_efficiency.png', 'Рисунок 3. Історична ефективність 128×128.', width=6.1)
    picture('local_kernel_speedup.png', 'Рисунок 4. Локальне порівняння ядер для одного простого модуля.', width=6.1)
    h('7 Аналіз результатів')
    p('У локальному порівнянні NumPy скоротив час одного модульного визначника приблизно '
      'у 12,66 раза для 128×128, у 23,82 раза для 256×256 і у 29,22 раза для 512×512. '
      'Python-варіант без залежностей дав менше покращення. Повне локальне обчислення '
      '512×512 завершилося з медіаною близько 30,10 с. Ці числа стосуються цього комп’ютера '
      'та версій бібліотек і не є оцінкою Google Cloud.')
    p('Кубічна робота повторюється за дедалі більшою кількістю модулів. Саме це пояснює '
      'сильне зростання часу великих матриць. У PARCS додатково впливають навантаження '
      'master, різні швидкості ВМ, мережа та баланс пакетів. Надлінійне S без стабільної '
      'послідовної бази слід перевіряти повторними серіями, а не трактувати як властивість методу.')

    page()
    h('8 Висновки')
    p('Перевірено точність модульного методу Гауса та достатність межі CRT для великих матриць. '
      'Збережено зрозумілу структуру Master, Worker, Map і Reduce та сумісний самодостатній '
      'solver.py. Master лише координує; підготовка, Map та CRT працюють на workers. '
      'Усунуто заборону розміру 512, оптимізовано Python-ядро і додано точний '
      'NumPy-варіант із перевіркою переповнення.')
    p('Локальні тести й дев’ять повних щільних обчислень завершилися успішно. Коректний '
      'розподіл рядків можливий лише як узгоджений розподілений Гаус; незалежне множення '
      'визначників блоків відхилено як неправильне. Поточний розподіл простих модулів збережено.')
    p('Хмарну частину лабораторної ще потрібно завершити. Підготовлено всі входи, інструменти '
      'подання та збору, CSV із пропусками й команди для наявного кластера. Після доступу '
      'потрібно перевірити середовище, виконати контрольний запуск, провести 12 конфігурацій '
      'і оновити таблицю та графіки новими фактичними вимірюваннями.')
    h('Порядок завершення хмарної частини')
    p('1. Завантажити parcs_workers_only_20261119.zip у Cloud Shell і розпакувати в нову папку. '
      '2. Виконати команди з docs/CLOUD_RUN_UK.md та зберегти інвентаризацію. '
      '3. Перевірити однакове ядро на workers і контрольне завдання 32×32. '
      '4. Запустити run_cloud_experiments.py через тунель. '
      '5. Побудувати CSV й графіки analyze_experiments.py та повернути вихідні JSON для звіту.')
    h('9 Використані джерела')
    sources = [
        '1. Репозиторій роботи та початкові вихідні дані. https://github.com/FizziToy/parcs-determinant/tree/refactor-parallel',
        '2. PARCS-Python. Вихідний код RPC, scheduler, Dockerfile та HTTP API; перевірена ревізія 00c5399. https://github.com/Hummer12007/parcs-python',
        '3. NumPy Documentation. Data types, overflow errors. https://numpy.org/doc/stable/user/basics.types.html',
        '4. Локальні протоколи experiments/local_kernels_20261118 та experiments/local_exact_20261118. Початкові часи й метадані середовища, 18 листопада 2026 року.',
        '5. Історичні файли outputs/n128_p1.txt … outputs/n128_p4.txt. Початкова реалізація e35ca13.',
    ]
    for source in sources:
        p(source)
    path = args.out / 'Report_PARCS_optimized_UK.docx'
    for border in doc.element.xpath('.//w:pBdr'):
        border.getparent().remove(border)
    doc.save(path)
    print('Created', path)


if __name__ == '__main__':
    main()

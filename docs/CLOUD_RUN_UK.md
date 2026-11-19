# Перенесення і запуск на наявному кластері

Поточний кластер: проєкт `parcs-514519`, зона `us-central1-a`, `parcs-master`
і `parcs-worker-1` … `parcs-worker-4`. Наведені нижче дії виконуються після
локальної підготовки; нові ВМ не створюються. Нові хмарні вимірювання поки відсутні.

## Передати локальні зміни без push

Готовий архів `parcs_workers_only_20261119.zip` лежить поруч із репозиторієм.
Він містить змінений код, тести, звіт і підготовлені експерименти, без `.git`,
кешів, залежностей і секретів. У Cloud Shell оберіть Upload file та завантажте
цей архів у домашню папку. У терміналі Cloud Shell:

```bash
cd "$HOME"
DEST="parcs-workers-only-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$DEST"
unzip -q parcs_workers_only_20261119.zip -d "$DEST"
cd "$DEST/parcs-determinant"
python3 build_solver.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q solver.py src tools tests
sha256sum solver.py
python3 -c "import json,hashlib; m=json.load(open('experiments/workers_only_20261119/manifest.json')); assert hashlib.sha256(open('solver.py','rb').read()).hexdigest()==m['solver_sha256']; print('Manifest matches solver')"
```

Не робіть `git clone` для запуску неопублікованих змін: remote ще містить
початкову реалізацію. Upload архіву передає саме оптимізований код.

## Зафіксувати середовище

```bash
INVENTORY="cluster-inventory-$(date -u +%Y%m%dT%H%M%SZ).txt"
bash cloud/check_existing_cluster.sh 2>&1 | tee "$INVENTORY"
```

Перевірте всі 5 контейнерів: ім'я `parcs-node`, версію Python, NumPy і digest
Docker-образу. Якщо імена контейнерів інші, замініть їх у двох допоміжних
скриптах. Точні CPU/RAM потрібно зчитати за фактичним machine type GCP,
а не з RAM у вебінтерфейсі старого PARCS.

Для штатного образу з Python 2.7 прискорений режим потребує NumPy 1.16.6.
Необов'язкова команда встановлення у чотири контейнери workers; Master NumPy не потребує:

```bash
bash cloud/install_numpy_existing.sh
bash cloud/check_existing_cluster.sh 2>&1 | tee "cluster-with-numpy-$(date -u +%Y%m%dT%H%M%SZ).txt"
```

Не запускайте її для Python 3: скрипт перевіряє 2.7 і зупиниться.
Встановлення змінює лише Python-пакети в поточних контейнерах, не відтворює
ВМ і не перезапускає PARCS. Після перевідтворення контейнера пакет потрібно
встановити знову або підготувати окремий зафіксований образ. Встановлення та
роботу NumPy 1.16.6 в хмарному контейнері в цій сесії не перевірено.
Якщо встановлення не вдалося, solver працює з Python-ядром, але локальне
прискорення NumPy до такої серії не застосовується. Не змішуйте різні ядра
між воркерами або посеред однієї серії.

## Тунель

В окремій вкладці Cloud Shell виконайте і залиште процес працювати:

```bash
gcloud compute ssh parcs-master --project parcs-514519 \
  --zone us-central1-a \
  -- -4 -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8080:127.0.0.1:8080
```

Web Preview на порту 8080 відкриває PARCS. Скрипт запуску звертається до
`http://127.0.0.1:8080` безпосередньо з Cloud Shell. Всі 4 воркери повинні бути
зареєстровані та увімкнені; кількість використаних задає поле `workers`.

## Контрольний запуск у справжньому PARCS

Перш ніж запускати велику серію, завантажте `solver.py` як Code у вебінтерфейсі
та перевірте обчислення на 4 воркерах із таким Input. Розмір 32 вмикає NumPy,
якщо пакет встановлено:

```bash
python3 -c 'import json; print(json.dumps(dict(size=32,workers=4,repetitions=1,seed=2026)))' > smoke32.json
```

Переконайтеся в успішному завершенні та `correct: true`. Це необхідно, бо
локальні тести використовують CPython 3.12/NumPy 2.3.5, а штатний PARCS старіший.
Контрольний запуск не додавайте до основної таблиці експериментів.

## Послідовно запустити 12 конфігурацій

У другій вкладці перейдіть до створеної вище папки репозиторію:

```bash
python3 tools/run_cloud_experiments.py --run experiments/workers_only_20261119 --check-only
python3 tools/run_cloud_experiments.py --run experiments/workers_only_20261119
```

Порядок: 128, потім 256, потім 512; для кожного розміру 1, 2, 3, 4 воркери.
Кожне завдання виконує 3 порівняння одного віддаленого worker з p віддаленими workers
на однаковій матриці з seed=2026 та діапазоном [-9,9]. Не запускайте інші
завдання паралельно. Для запуску наступної серії використайте нову папку:

```bash
python3 tools/prepare_experiments.py --out experiments/optimized_second_series
```

Скрипт очікує завершення, перевіряє завантажені Code/Input, correct, конфігурацію
та довжину масивів часу; зберігає Output і SHA256 походження. Числові результати
не перезаписуються. Після обриву з'єднання або таймауту спочатку перегляньте
Jobs; завдання не скасовується автоматично. Для продовження того самого плану:

```bash
python3 tools/run_cloud_experiments.py --run experiments/workers_only_20261119 --resume
```

`--resume` перевіряє та пропускає збережені результати, знаходить уже подане
завдання за унікальним ім'ям і не подає його повторно. Якщо запис подання є,
а завдання у PARCS не знайдене, скрипт зупиняється для ручної перевірки.

## CSV та графіки

```bash
python3 -m venv .venv-analysis
.venv-analysis/bin/pip install matplotlib
ANALYSIS="experiments/workers_only_20261119/analysis-$(date -u +%Y%m%dT%H%M%SZ)"
.venv-analysis/bin/python tools/analyze_experiments.py \
  --run experiments/workers_only_20261119 --out "$ANALYSIS" --plots
```

`raw.csv` містить 36 пар вимірювань, `summary.csv` — 12 медіан, прискорення
T1_remote/Tp_remote та ефективність S/workers. Відсутні вимірювання залишаються порожніми.
Графіки `time.png`, `speedup.png`, `efficiency.png` використовують тільки нову
серію. Старі `outputs/` та `results.csv` не імпортуються.

Не інтерпретуйте S > workers як доведене надлінійне прискорення. Перевірте
коливання базового часу на одному worker, навантаження вузлів і повторіть всю серію.
Генерація матриці, вибір модулів, підготовка воркерів та черга PARCS не входять
до внутрішнього часу solver. Серіалізація, RPC, Map і Worker Reduce/CRT входять в обидва часи.

Після завершення завантажте папку експериментів і файли інвентаризації назад
на ноутбук. Звіт слід доповнити саме цими новими даними, реальними параметрами
ВМ та, за вимогою викладача, знімками Workers/Jobs. Теперішній DOCX уже містить
локальні перевірки, історичні результати з позначенням і відсутні хмарні дані.

## Ролі вузлів у версії від 19 листопада

Master лише координує RPC, таймери, порівняння відповідей і запис Output. Worker 1 готує матрицю й модулі та виконує Reduce/CRT після Map. Усі модульні визначники виконують workers. Поля sequential_* тепер вимірюють одного віддаленого worker, а parallel_* — p workers, включно з RPC і Reduce на worker. В Output мають бути execution_model=workers_only та timing_baseline=one_remote_worker_including_rpc_and_reduce. Аналізатор відхиляє стару методику з обчисленням бази на Master. Старий архів від 18 листопада та попередній план збережені; для поточного запуску використовуйте новий архів і workers_only_20261119.

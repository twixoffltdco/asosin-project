# 🛸 Asosin-Project

<div align="center">

![Auto Hunt](https://github.com/YOUR_USERNAME/asosin-project/actions/workflows/hunter.yml/badge.svg)
![Channels](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/YOUR_USERNAME/asosin-project/main/playlist/known_streams.json&label=channels&query=$.length&color=brightgreen&logo=tv&logoColor=white)
![Updated](https://img.shields.io/github/last-commit/YOUR_USERNAME/asosin-project?label=updated&color=blue)
![License](https://img.shields.io/badge/license-MIT-orange)

**Автономный IPTV-агрегатор. Ищет, проверяет и собирает рабочие M3U8-потоки каждый час.**

[📺 Плейлист](#-плейлист) • [🔧 Как работает](#-как-работает) • [🚀 Deploy](#-деплой) • [⚙️ Настройка](#️-настройка)

</div>

---

## 📺 Плейлист

Плейлист обновляется автоматически каждый час. Вставь ссылку в свой IPTV-плеер:

```
https://raw.githubusercontent.com/YOUR_USERNAME/asosin-project/main/playlist/asosin.m3u
```

> Совместим с **VLC**, **Kodi**, **IPTVnator**, **TiviMate**, **OTT Navigator**, **GSE Smart IPTV** и любым HLS-плеером.

---

## 🔧 Как работает

```
┌──────────────────────────────────────────────────────────┐
│                   GitHub Actions (каждый час)            │
│                                                          │
│  🔍 ПОИСК            🧪 ПРОВЕРКА         💾 СОХРАНЕНИЕ  │
│  ──────────          ──────────          ──────────────  │
│  Google              aiohttp GET         playlist/        │
│  Yandex      ──►     HTTP 200?   ──►     asosin.m3u       │
│  Bing                #EXTM3U?            known_streams    │
│  DuckDuckGo          HLS valid?          .json            │
│  Ecosia                                                   │
│  Mojeek              80 параллельных                     │
│                      воркеров                            │
└──────────────────────────────────────────────────────────┘
```

### Этапы работы робота

| Шаг | Описание |
|-----|----------|
| **1. Поиск** | 20 поисковых запросов × 6 движков = до 120 HTTP-запросов |
| **2. Парсинг** | Regex вытаскивает все `.m3u8` URL из HTML-ответов |
| **3. Дедупликация** | Убираем дубли, исключаем уже известные живые потоки |
| **4. Проверка** | 80 параллельных воркеров делают GET-запрос к каждому URL |
| **5. Валидация** | Поток принят только если отдаёт `#EXTM3U` / `#EXT-X-` заголовок |
| **6. Реинкарнация** | Старые потоки перепроверяются — мёртвые удаляются после 3 неудач |
| **7. Коммит** | Обновлённый `asosin.m3u` пушится в репозиторий |

---

## 🚀 Деплой

### 1. Fork репозитория

Нажми **Fork** в правом верхнем углу → у тебя появится своя копия.

### 2. Включи Actions

Зайди в **Settings → Actions → General** → выбери `Allow all actions`.

### 3. Включи запись в репо

**Settings → Actions → General → Workflow permissions** → `Read and write permissions` ✅

### 4. Первый ручной запуск

**Actions** → **🛸 Asosin Hunter** → **Run workflow** → готово!

После этого бот будет запускаться **автоматически каждый час**.

---

## ⚙️ Настройка

Все параметры в `scripts/hunter.py`:

```python
MAX_WORKERS   = 80     # параллельных проверок (↑ быстрее, ↑ нагрузка)
CHECK_TIMEOUT = 8      # секунд на один поток
SEARCH_DELAY  = (2, 5) # пауза между запросами (сек, рандом)
```

### Добавить свои поисковые запросы

```python
SEARCH_QUERIES = [
    'inurl:m3u8 "ваш канал"',
    # ... добавляй сюда
]
```

### Изменить расписание

В `.github/workflows/hunter.yml`:

```yaml
schedule:
  - cron: "0 * * * *"   # каждый час
  - cron: "0 */2 * * *" # каждые 2 часа
  - cron: "0 6,18 * * *" # в 6:00 и 18:00 UTC
```

---

## 📁 Структура

```
asosin-project/
├── .github/
│   └── workflows/
│       └── hunter.yml          # GitHub Actions расписание
├── scripts/
│   └── hunter.py               # основной робот-охотник
├── playlist/
│   ├── asosin.m3u              # 📺 готовый плейлист
│   └── known_streams.json      # база известных потоков
├── requirements.txt
└── README.md
```

---

## ⚠️ Disclaimer

Проект предназначен исключительно для технических исследований и агрегации **публично доступных** потоков. Все найденные ссылки — открытые URL из публичного интернета. Автор не несёт ответственности за содержимое транслируемого контента.

---

<div align="center">

**Asosin-Project** · автономный IPTV-охотник · обновляется каждый час 🛸

</div>

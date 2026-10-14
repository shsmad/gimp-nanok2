# Установка

## Системные зависимости

Для сборки `python-rtmidi` нужны заголовки ALSA/JACK и компилятор:

```bash
sudo apt install build-essential python3-dev libasound2-dev libjack-jackd2-dev
```

## Окружение (PDM, Python 3.14)

```bash
pdm install -G dev
```

Виртуальное окружение — `venv/` в корне репозитория.

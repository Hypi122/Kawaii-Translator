# Kawaii Translator

Small GUI program allowing for quick OCR and translation of text.
screenshot/video

## Installation

You can install Kawaii Translator using pip:

`pip install .[all] `

Or install all ocr engines:

`pip install .[all_ocr]`

Or install all translations engines:

`pip install .[all_translation]`

To install with specific OCR or translation engines, use the following:

*   **Windows OCR:** `pip install .[windows_ocr]`
*   **MangaOCR:** `pip install .[manga_ocr]`
*   **PaddleOCR:** `pip install .[paddle_ocr_cpu]`
*   **OpenAI Compatible (for translation and OCR):** `pip install .[openai]`
*   **Google Translate:** `pip install .[google_translate]`

You can also combine them, for example:

`pip install .[manga_ocr,openai,google_translate]`

## Usage
You can run Kawaii Translator using:

`python .\src\main.py`

## Tested On

This project has been tested on Python versions 3.13.6 and 3.9.7.

## Description

Built using:
*   **GUI:** PyQt6
*   **Screenshot Handling:** Pillow, NumPy, OpenCV, MSS
*   **Hotkeys:** Pynput

## TODO

*   Custom prompts for openai api engine
    *   Per preset?
*   Better setting up hotkeys
*   Ability to re-translate single engine
*   General gui improvements
*   Paddle OCR support gpu inference
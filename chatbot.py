"""
Chatbot Gemini — clé API Google AI Studio
Usage:
  1. pip install -r requirements.txt
  2. Copiez votre clé dans le fichier .env (GEMINI_API_KEY=...)
  3. python chatbot.py
"""

import os
import sys
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
# Flash-Lite est en général plus disponible que Flash en cas de pic de charge
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODELS = list(
    dict.fromkeys(
        [
            MODEL,
            "gemini-3.5-flash-lite",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
        ]
    )
)
MAX_RETRIES = 3


def is_busy(exc: Exception) -> bool:
    text = str(exc).lower()
    return "503" in text or "unavailable" in text or "high demand" in text


def make_chat(client: genai.Client, model: str):
    return client.chats.create(
        model=model,
        config={
            "system_instruction": (
                "Tu es Geminia, un assistant conversationnel utile et concis. "
                f"Tu tournes via l'API Google Gemini, modèle exact: {model}. "
                "Si on te demande quel modèle ou quelle version tu utilises, "
                f"réponds clairement: {model}."
            )
        },
    )


def send_with_retry(client: genai.Client, chat, model: str, message: str):
    """Réessaie en cas de saturation, puis bascule sur un autre modèle."""
    last_error = None
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]

    for current_model in models_to_try:
        if current_model != model:
            print(f"(bascule vers {current_model}…)", file=sys.stderr)
            chat = make_chat(client, current_model)
            model = current_model

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = chat.send_message(message)
                return response, chat, model
            except Exception as exc:
                last_error = exc
                if not is_busy(exc):
                    raise
                if attempt < MAX_RETRIES:
                    wait = 2**attempt
                    print(
                        f"(serveur occupé, nouvel essai dans {wait}s…)",
                        file=sys.stderr,
                    )
                    time.sleep(wait)

    raise last_error


def main() -> None:
    if not API_KEY:
        print(
            "Erreur: définissez GEMINI_API_KEY dans le fichier .env "
            "(clé depuis https://aistudio.google.com/apikey)",
            file=sys.stderr,
        )
        sys.exit(1)

    client = genai.Client(api_key=API_KEY)
    model = MODEL
    chat = make_chat(client, model)

    print(f"Geminia ({model}) — tapez 'quit' ou 'exit' pour quitter.\n")
    print("Commandes: /model  |  quit\n")

    while True:
        try:
            user = input("Vous: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break

        if not user:
            continue
        if user.lower() in {"quit", "exit", "q"}:
            print("Au revoir.")
            break
        if user.lower() in {"/model", "model"}:
            print(f"Geminia: modèle actuel = {model}\n")
            continue

        try:
            response, chat, model = send_with_retry(client, chat, model, user)
            print(f"Geminia: {response.text}\n")
        except Exception as exc:
            if is_busy(exc):
                print(
                    "Gemini est saturé pour le moment. Réessayez dans quelques minutes.\n",
                    file=sys.stderr,
                )
            else:
                print(f"Erreur API: {exc}\n", file=sys.stderr)


if __name__ == "__main__":
    main()

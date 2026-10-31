"""Terminal chat. `emporio` starts a conversation; `--session NAME` keeps it on disk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from .agent import Agent, OpenAIChatClient

SESSIONS_DIR = Path(".sessions")


def main() -> None:
    load_dotenv(override=True)  # the project .env wins over stale shell variables
    parser = argparse.ArgumentParser(description="Atendimento da Empório da Música (protótipo)")
    parser.add_argument("--session", help="nome da sessão para salvar e retomar o histórico")
    parser.add_argument("--debug", action="store_true", help="mostra as ferramentas chamadas a cada resposta")
    parser.add_argument("--model", help="sobrescreve LLM_MODEL")
    args = parser.parse_args()

    agent = Agent(OpenAIChatClient(model=args.model))
    session_path = SESSIONS_DIR / f"{args.session}.json" if args.session else None
    if session_path:
        agent.load(session_path)
        if agent.history:
            print(f"(sessão '{args.session}' retomada com {len(agent.history)} mensagens)")

    print("Empório da Música · digite sua mensagem (ou 'sair')\n")
    while True:
        try:
            text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in {"sair", "exit", "quit"}:
            break
        turn = agent.send(text)
        if args.debug:
            for t in turn.tools:
                print(f"  [ferramenta] {t.name}({json.dumps(t.arguments, ensure_ascii=False)})")
        print(f"\nLia: {turn.reply}\n")
        if session_path:
            agent.save(session_path)


if __name__ == "__main__":
    main()

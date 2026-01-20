from __future__ import annotations

import html
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "journal.db"
STATIC_DIR = BASE_DIR / "static"

PRACTICE_FIELDS = [
    ("breathing", "Respiração"),
    ("meditation", "Meditação"),
    ("writing", "Escrita"),
    ("reading", "Leitura"),
]


CSS_PATH = STATIC_DIR / "styles.css"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                sleep_score INTEGER NOT NULL,
                energy_score INTEGER NOT NULL,
                training_type TEXT NOT NULL,
                training_intensity INTEGER NOT NULL,
                food_notes TEXT NOT NULL,
                practice_breathing INTEGER NOT NULL,
                practice_meditation INTEGER NOT NULL,
                practice_writing INTEGER NOT NULL,
                practice_reading INTEGER NOT NULL,
                perceptions TEXT NOT NULL,
                emotional_wave INTEGER NOT NULL,
                emotional_trigger TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


init_db()


def html_page(title: str, body: str) -> bytes:
    return f"""<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{html.escape(title)}</title>
  <link rel=\"stylesheet\" href=\"/static/styles.css\">
</head>
<body>
{body}
</body>
</html>""".encode("utf-8")


def index_page(students: list[str]) -> bytes:
    today = date.today().isoformat()
    student_links = "".join(
        f"<li><a href=\"/report/{quote(student)}\">Relatório semanal de {html.escape(student)}</a></li>"
        for student in students
    )
    report_section = (
        f"<ul class=\"report-list\">{student_links}</ul>"
        if students
        else "<p class=\"muted\">Nenhum registro ainda. Adicione o primeiro para liberar os relatórios.</p>"
    )
    practices = "".join(
        f"""
        <label class=\"checkbox\">
          <input type=\"checkbox\" name=\"{field}\">
          {label}
        </label>
        """
        for field, label in PRACTICE_FIELDS
    )
    body = f"""
<main class=\"container\">
  <header>
    <h1>Diário diário do aluno</h1>
    <p>Registre as informações do dia para acompanhar hábitos e bem-estar.</p>
  </header>

  <section class=\"card\">
    <h2>Novo registro</h2>
    <form action=\"/submit\" method=\"post\" class=\"form-grid\">
      <label>
        Nome do aluno
        <input type=\"text\" name=\"student_name\" placeholder=\"Ex: Ana Paula\" required>
      </label>

      <label>
        Data
        <input type=\"date\" name=\"entry_date\" value=\"{today}\" required>
      </label>

      <label>
        Sono (0-10)
        <input type=\"number\" name=\"sleep_score\" min=\"0\" max=\"10\" required>
      </label>

      <label>
        Energia (0-10)
        <input type=\"number\" name=\"energy_score\" min=\"0\" max=\"10\" required>
      </label>

      <label>
        Tipo de treino
        <input type=\"text\" name=\"training_type\" placeholder=\"Força, corrida, mobilidade...\" required>
      </label>

      <label>
        Intensidade do treino (0-10)
        <input type=\"number\" name=\"training_intensity\" min=\"0\" max=\"10\" required>
      </label>

      <label class=\"full\">
        Alimentação (texto curto)
        <input type=\"text\" name=\"food_notes\" maxlength=\"200\" placeholder=\"Ex: almoço leve, pouco açúcar\" required>
      </label>

      <fieldset class=\"full\">
        <legend>Prática de retomada</legend>
        <div class=\"checkbox-grid\">
          {practices}
        </div>
      </fieldset>

      <label class=\"full\">
        Percepções
        <textarea name=\"perceptions\" rows=\"3\" placeholder=\"O que percebeu hoje?\" required></textarea>
      </label>

      <label>
        Onda emocional (0-10)
        <input type=\"number\" name=\"emotional_wave\" min=\"0\" max=\"10\" required>
      </label>

      <label>
        Gatilho da onda emocional
        <input type=\"text\" name=\"emotional_trigger\" placeholder=\"Ex: conversa, prova, treino\" required>
      </label>

      <button type=\"submit\" class=\"primary\">Salvar registro</button>
    </form>
  </section>

  <section class=\"card\">
    <h2>Relatórios disponíveis</h2>
    {report_section}
  </section>
</main>
"""
    return html_page("Diário diário - Alunos", body)


def _fetch_weekly_entries(student_name: str) -> list[sqlite3.Row]:
    end_date = date.today()
    start_date = end_date - timedelta(days=6)
    with get_db() as conn:
        return conn.execute(
            """
            SELECT * FROM entries
            WHERE student_name = ?
              AND entry_date BETWEEN ? AND ?
            ORDER BY entry_date DESC
            """,
            (student_name, start_date.isoformat(), end_date.isoformat()),
        ).fetchall()


def _fetch_previous_week(student_name: str) -> list[sqlite3.Row]:
    end_date = date.today() - timedelta(days=7)
    start_date = end_date - timedelta(days=6)
    with get_db() as conn:
        return conn.execute(
            """
            SELECT * FROM entries
            WHERE student_name = ?
              AND entry_date BETWEEN ? AND ?
            ORDER BY entry_date DESC
            """,
            (student_name, start_date.isoformat(), end_date.isoformat()),
        ).fetchall()


def _average(rows: list[sqlite3.Row], field: str) -> float:
    if not rows:
        return 0.0
    return sum(row[field] for row in rows) / len(rows)


def _trend(current: float, previous: float) -> str:
    delta = current - previous
    if delta > 0.5:
        return "↑ em alta"
    if delta < -0.5:
        return "↓ em queda"
    return "→ estável"


def _highlights(rows: list[sqlite3.Row]) -> dict[str, Any]:
    if not rows:
        return {}
    best_sleep = max(rows, key=lambda row: row["sleep_score"])
    low_energy = min(rows, key=lambda row: row["energy_score"])
    top_emotion = max(rows, key=lambda row: row["emotional_wave"])
    training_by_type: dict[str, int] = Counter(
        row["training_type"] for row in rows if row["training_type"]
    )
    top_training = max(training_by_type.items(), key=lambda item: item[1])[0]
    return {
        "best_sleep": best_sleep,
        "low_energy": low_energy,
        "top_emotion": top_emotion,
        "top_training": top_training,
    }


def report_page(student_name: str, entries: list[sqlite3.Row]) -> bytes:
    weekly_entries = entries
    previous_entries = _fetch_previous_week(student_name)

    averages = {
        "sleep": _average(weekly_entries, "sleep_score"),
        "energy": _average(weekly_entries, "energy_score"),
        "training": _average(weekly_entries, "training_intensity"),
        "emotional": _average(weekly_entries, "emotional_wave"),
    }
    previous_averages = {
        "sleep": _average(previous_entries, "sleep_score"),
        "energy": _average(previous_entries, "energy_score"),
        "training": _average(previous_entries, "training_intensity"),
        "emotional": _average(previous_entries, "emotional_wave"),
    }

    trends = {key: _trend(averages[key], previous_averages[key]) for key in averages}
    highlights = _highlights(weekly_entries)

    practices = {
        "breathing": sum(row["practice_breathing"] for row in weekly_entries),
        "meditation": sum(row["practice_meditation"] for row in weekly_entries),
        "writing": sum(row["practice_writing"] for row in weekly_entries),
        "reading": sum(row["practice_reading"] for row in weekly_entries),
    }

    if not entries:
        body = f"""
<main class=\"container\">
  <header class=\"header-row\">
    <div>
      <h1>Relatório semanal</h1>
      <p>Aluno: <strong>{html.escape(student_name)}</strong></p>
    </div>
    <a class=\"secondary\" href=\"/\">Voltar ao formulário</a>
  </header>

  <section class=\"card\">
    <h2>Sem registros para a semana</h2>
    <p>Adicione entradas nos últimos 7 dias para visualizar as médias, tendências e destaques.</p>
  </section>
</main>
"""
        return html_page(f"Relatório semanal - {student_name}", body)

    highlight_html = f"""
      <li>Melhor sono: {highlights['best_sleep']['entry_date']} ({highlights['best_sleep']['sleep_score']})</li>
      <li>Menor energia: {highlights['low_energy']['entry_date']} ({highlights['low_energy']['energy_score']})</li>
      <li>Pico emocional: {highlights['top_emotion']['entry_date']} ({highlights['top_emotion']['emotional_wave']})</li>
      <li>Treino mais comum: {html.escape(highlights['top_training'])}</li>
    """

    entries_html = ""
    for entry in weekly_entries:
        tags = []
        if entry["practice_breathing"]:
            tags.append("Respiração")
        if entry["practice_meditation"]:
            tags.append("Meditação")
        if entry["practice_writing"]:
            tags.append("Escrita")
        if entry["practice_reading"]:
            tags.append("Leitura")
        practice_text = ", ".join(tags) if tags else "Nenhuma"
        entries_html += f"""
        <article>
          <h3>{entry['entry_date']}</h3>
          <p><strong>Sono:</strong> {entry['sleep_score']} | <strong>Energia:</strong> {entry['energy_score']} | <strong>Onda emocional:</strong> {entry['emotional_wave']}</p>
          <p><strong>Treino:</strong> {html.escape(entry['training_type'])} ({entry['training_intensity']})</p>
          <p><strong>Alimentação:</strong> {html.escape(entry['food_notes'])}</p>
          <p><strong>Retomada:</strong> {practice_text}</p>
          <p><strong>Percepções:</strong> {html.escape(entry['perceptions'])}</p>
          <p><strong>Gatilho emocional:</strong> {html.escape(entry['emotional_trigger'])}</p>
        </article>
        """

    body = f"""
<main class=\"container\">
  <header class=\"header-row\">
    <div>
      <h1>Relatório semanal</h1>
      <p>Aluno: <strong>{html.escape(student_name)}</strong></p>
    </div>
    <a class=\"secondary\" href=\"/\">Voltar ao formulário</a>
  </header>

  <section class=\"card\">
    <h2>Médias da semana (últimos 7 dias)</h2>
    <div class=\"metric-grid\">
      <div>
        <span>Sono</span>
        <strong>{averages['sleep']:.1f}</strong>
        <em>{trends['sleep']}</em>
      </div>
      <div>
        <span>Energia</span>
        <strong>{averages['energy']:.1f}</strong>
        <em>{trends['energy']}</em>
      </div>
      <div>
        <span>Treino</span>
        <strong>{averages['training']:.1f}</strong>
        <em>{trends['training']}</em>
      </div>
      <div>
        <span>Onda emocional</span>
        <strong>{averages['emotional']:.1f}</strong>
        <em>{trends['emotional']}</em>
      </div>
    </div>
  </section>

  <section class=\"card\">
    <h2>Destaques</h2>
    <ul class=\"highlight-list\">
      {highlight_html}
    </ul>
  </section>

  <section class=\"card\">
    <h2>Práticas de retomada</h2>
    <div class=\"metric-grid\">
      <div>
        <span>Respiração</span>
        <strong>{practices['breathing']}</strong>
      </div>
      <div>
        <span>Meditação</span>
        <strong>{practices['meditation']}</strong>
      </div>
      <div>
        <span>Escrita</span>
        <strong>{practices['writing']}</strong>
      </div>
      <div>
        <span>Leitura</span>
        <strong>{practices['reading']}</strong>
      </div>
    </div>
  </section>

  <section class=\"card\">
    <h2>Entradas da semana</h2>
    <div class=\"entries\">
      {entries_html}
    </div>
  </section>
</main>
"""
    return html_page(f"Relatório semanal - {student_name}", body)


class JournalHandler(BaseHTTPRequestHandler):
    def _send_response(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            with get_db() as conn:
                students = [
                    row["student_name"]
                    for row in conn.execute(
                        "SELECT DISTINCT student_name FROM entries ORDER BY student_name"
                    ).fetchall()
                ]
            body = index_page(students)
            self._send_response(HTTPStatus.OK, body, "text/html; charset=utf-8")
            return

        if parsed.path.startswith("/report/"):
            student_name = unquote(parsed.path.replace("/report/", "", 1))
            weekly_entries = _fetch_weekly_entries(student_name)
            body = report_page(student_name, weekly_entries)
            self._send_response(HTTPStatus.OK, body, "text/html; charset=utf-8")
            return

        if parsed.path == "/static/styles.css" and CSS_PATH.exists():
            body = CSS_PATH.read_bytes()
            self._send_response(HTTPStatus.OK, body, "text/css; charset=utf-8")
            return

        self._send_response(
            HTTPStatus.NOT_FOUND,
            html_page("Não encontrado", "<h1>404 - Página não encontrada</h1>"),
            "text/html; charset=utf-8",
        )

    def do_POST(self) -> None:
        if self.path != "/submit":
            self._send_response(
                HTTPStatus.NOT_FOUND,
                html_page("Não encontrado", "<h1>404 - Página não encontrada</h1>"),
                "text/html; charset=utf-8",
            )
            return

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")
        data = parse_qs(post_data)

        def get_value(key: str) -> str:
            return data.get(key, [""])[0].strip()

        entry_date = get_value("entry_date") or date.today().isoformat()
        created_at = datetime.utcnow().isoformat()
        practices = {field: 1 if field in data else 0 for field, _ in PRACTICE_FIELDS}

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO entries (
                    student_name,
                    entry_date,
                    sleep_score,
                    energy_score,
                    training_type,
                    training_intensity,
                    food_notes,
                    practice_breathing,
                    practice_meditation,
                    practice_writing,
                    practice_reading,
                    perceptions,
                    emotional_wave,
                    emotional_trigger,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    get_value("student_name"),
                    entry_date,
                    int(get_value("sleep_score") or 0),
                    int(get_value("energy_score") or 0),
                    get_value("training_type"),
                    int(get_value("training_intensity") or 0),
                    get_value("food_notes"),
                    practices["breathing"],
                    practices["meditation"],
                    practices["writing"],
                    practices["reading"],
                    get_value("perceptions"),
                    int(get_value("emotional_wave") or 0),
                    get_value("emotional_trigger"),
                    created_at,
                ),
            )

        self.send_response(HTTPStatus.SEE_OTHER.value)
        self.send_header("Location", "/")
        self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 5000), JournalHandler)
    print("Servidor ativo em http://0.0.0.0:5000")
    server.serve_forever()

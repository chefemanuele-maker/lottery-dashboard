import csv
from collections import Counter
from pathlib import Path

DATA_FILE = Path("superenalotto_history.csv")


def load_draws():
    draws = []

    if not DATA_FILE.exists():
        return draws

    with open(DATA_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)

        for row in reader:
            try:
                numbers = [int(n) for n in row[:6]]
                draws.append(numbers)
            except:
                continue

    return draws


def compute_frequency(draws):

    counter = Counter()

    for draw in draws:
        counter.update(draw)

    return counter


def build_dashboard_payload():

    draws = load_draws()

    if not draws:
        return {
            "total_draws": 0,
            "most_common": []
        }

    freq = compute_frequency(draws)

    most_common = freq.most_common(10)

    return {
        "total_draws": len(draws),
        "most_common": most_common
    }


def render_html(payload):

    html = """
    <html>
    <head>
        <title>SuperEnalotto Dashboard</title>
        <style>
        body{
            background:#0b0f19;
            color:white;
            font-family:Arial;
            padding:40px;
        }

        h1{
            color:#4dd0ff;
        }

        table{
            border-collapse: collapse;
            margin-top:20px;
        }

        td,th{
            padding:10px 20px;
            border-bottom:1px solid #333;
        }

        th{
            color:#4dd0ff;
        }
        </style>
    </head>

    <body>

    <h1>SuperEnalotto Dashboard</h1>
    """

    html += f"<p>Total draws analysed: {payload['total_draws']}</p>"

    html += """
    <h2>Most frequent numbers</h2>

    <table>
    <tr>
    <th>Number</th>
    <th>Frequency</th>
    </tr>
    """

    for number, count in payload["most_common"]:

        html += f"""
        <tr>
        <td>{number}</td>
        <td>{count}</td>
        </tr>
        """

    html += """
    </table>
    </body>
    </html>
    """

    return html

from flask import Flask, Response
import euromillions_live_dashboard_v2 as euro
import superenalotto_live_dashboard as supereno

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <html>
    <head>
        <title>Lottery Dashboard</title>
        <style>
            body {
                background: #0b0f19;
                color: white;
                font-family: Arial, sans-serif;
                padding: 30px;
            }
            a {
                color: #4dd0ff;
                font-size: 22px;
            }
            h1 { margin-bottom: 10px; }
            ul { line-height: 2; }
        </style>
    </head>
    <body>
        <h1>Lottery Dashboard</h1>
        <p>Server running on Render</p>
        <h2>Available dashboards</h2>
        <ul>
            <li><a href="/euromillions">EuroMillions</a></li>
            <li><a href="/superenalotto">SuperEnalotto</a></li>
        </ul>
    </body>
    </html>
    """

@app.route("/euromillions")
def euromillions():
    payload = euro.build_dashboard_payload()
    html = euro.render_html(payload)
    return Response(html, mimetype="text/html")

@app.route("/superenalotto")
def superenalotto():
    payload = supereno.build_dashboard_payload()
    html = supereno.render_html(payload)
    return Response(html, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

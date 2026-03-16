from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/superenalotto":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            html = """
            <html>
            <head>
            <title>Superenalotto Dashboard</title>
            </head>
            <body>
            <h1>Superenalotto Dashboard</h1>
            <p>Server attivo su Render</p>
            <p>Versione light per server gratuito</p>
            </body>
            </html>
            """

            self.wfile.write(html.encode())
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Lottery Dashboard running")

def run():
    port = 10000
    server = HTTPServer(("", port), Handler)
    print("Server running...")
    server.serve_forever()

run()

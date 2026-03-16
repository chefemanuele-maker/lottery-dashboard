from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            html = """
            <html>
            <head>
                <title>Lottery Dashboard</title>
            </head>
            <body style="font-family: Arial; background:#111; color:white;">
                <h1>Lottery Dashboard</h1>

                <p>Server running on Render</p>

                <h2>Available dashboards</h2>

                <ul>
                    <li><a href="/euromillions" style="color:cyan;">EuroMillions</a></li>
                    <li><a href="/superenalotto" style="color:cyan;">SuperEnalotto</a></li>
                </ul>

            </body>
            </html>
            """

            self.wfile.write(html.encode())


        elif self.path == "/euromillions":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            html = """
            <html>
            <body style="background:#111;color:white;font-family:Arial;">
            <h1>EuroMillions Dashboard</h1>
            <p>EuroMillions section working.</p>
            </body>
            </html>
            """

            self.wfile.write(html.encode())


        elif self.path == "/superenalotto":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            html = """
            <html>
            <body style="background:#111;color:white;font-family:Arial;">
            <h1>SuperEnalotto Dashboard</h1>
            <p>SuperEnalotto section working.</p>
            </body>
            </html>
            """

            self.wfile.write(html.encode())


        else:
            self.send_response(404)
            self.end_headers()


def run():
    port = 10000
    server = HTTPServer(("", port), Handler)
    print("Lottery Dashboard running")
    server.serve_forever()


run()

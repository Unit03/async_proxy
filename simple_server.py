import datetime
import http.server


class SimpleHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write("<html><head><title>Hello</title></head>".encode())
        self.wfile.write("<body><h1>Hello</h1></body></html>".encode())

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write("<html><head><title>Hello</title></head><body>"
                         .encode())
        data = self.rfile.read(int(self.headers["content-length"]))
        self.wfile.write(data)
        self.wfile.write("</body></html>".encode())


if __name__ == "__main__":
    server = http.server.HTTPServer(("localhost", 8001), SimpleHandler)

    print("Start: {}".format(datetime.datetime.now()))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    server.server_close()
    print("Stop: {}".format(datetime.datetime.now()))

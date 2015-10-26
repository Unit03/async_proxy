import argparse
import datetime
import http.server
import urllib.parse


class SimpleHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/range":
            self.send_response(206)
            self.send_header("Content-Range", "bytes 6-11/*")
            self.send_header("Content-type", "text/html")
            self.end_headers()
            # Hard-coded range of bytes=6-11.
            self.wfile.write("<head>".encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
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
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", default=8001, type=int)
    args = parser.parse_args()

    host = "localhost"
    server = http.server.HTTPServer((host, args.port), SimpleHandler)

    print("Start: {}. Listening on {}:{}"
          .format(datetime.datetime.now(), host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    server.server_close()
    print("Stop: {}".format(datetime.datetime.now()))

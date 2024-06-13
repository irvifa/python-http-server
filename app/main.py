import socket
from urllib.parse import urlparse

class HTTPServer:
    def __init__(self, host='localhost', port=4221):
        self.host = host
        self.port = port
        self.server_socket = socket.create_server((self.host, self.port), reuse_port=True)
        self.routes = {
            '/': self.handle_root,
            '/echo': self.handle_echo,
        }
    
    def start(self):
        print(f'Server listening on {self.host}:{self.port}')
        while True:
            client_socket, _ = self.server_socket.accept()
            self.handle_request(client_socket)

    def handle_request(self, client_socket):
        request = client_socket.recv(1024).decode('utf-8')
        request_line = request.split('\n')[0]
        method, path, _ = request_line.split()
        parsed_path, _ = self.parse_path(path)

        handler = self.routes.get(parsed_path, self.handle_404)
        handler(client_socket)

    def parse_path(self, path):
        parsed_url = urlparse(path)
        return parsed_url.path, parsed_url.query

    def handle_root(self, client_socket):
        self.send_response(client_socket, 200, 'text/plain', 'OK')

    def handle_echo(self, client_socket):
        self.send_response(client_socket, 200, 'text/plain', 'Echo Handler')

    def handle_404(self, client_socket):
        self.send_response(client_socket, 404, 'text/plain', '404 Not Found')

    def send_response(self, client_socket, status_code, content_type, body):
        response_line = f'HTTP/1.1 {status_code} {self.get_reason_phrase(status_code)}\r\n'
        headers = f'Content-Type: {content_type}\r\nContent-Length: {len(body)}\r\n\r\n'
        response = response_line + headers + body
        client_socket.sendall(response.encode('utf-8'))
        client_socket.close()

    def get_reason_phrase(self, status_code):
        phrases = {
            200: 'OK',
            404: 'Not Found',
        }
        return phrases.get(status_code, '')

def run_server():
    server = HTTPServer()
    server.start()

if __name__ == '__main__':
    run_server()

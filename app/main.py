import socket
import os
import gzip
from urllib.parse import urlparse

class HTTPServer:
    def __init__(self, host='localhost', port=4221):
        self.host = host
        self.port = port
        self.server_socket = socket.create_server((self.host, self.port), reuse_port=True)
        self.routes = {
            ('GET', '/'): self.handle_root,
            ('GET', '/echo'): self.handle_echo,
            ('GET', '/user-agent'): self.handle_user_agent,
            ('GET', '/files'): self.handle_files,
            ('POST', '/files'): self.handle_files_create,
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
        headers = self.parse_headers(request)
        path, query = self.parse_path(path)

        handler = self.find_handler(method, path)
        if handler:
            handler(client_socket, path, headers, request)
        else:
            self.send_response(client_socket, 404, 'text/plain', '404 Not Found')

    def find_handler(self, method, path):
        for (route_method, route_path), handler in self.routes.items():
            if method == route_method and path.startswith(route_path):
                return handler
        return None

    def parse_headers(self, request):
        headers = {}
        lines = request.split('\n')
        for line in lines[1:]:
            if line.strip() == '':
                break
            key, value = line.split(':', 1)
            headers[key.strip()] = value.strip()
        return headers

    def parse_path(self, path):
        parsed_url = urlparse(path)
        return parsed_url.path, parsed_url.query

    def handle_root(self, client_socket, path, headers, request):
        self.send_response(client_socket, 200, 'text/plain', 'OK')

    def handle_echo(self, client_socket, path, headers, request):
        message = path[len('/echo/'):].encode('utf-8')
        if 'Accept-Encoding' in headers and 'gzip' in headers['Accept-Encoding']:
            message = gzip.compress(message)
            self.send_response(client_socket, 200, 'text/plain', message, 'gzip')
        else:
            self.send_response(client_socket, 200, 'text/plain', message)

    def handle_user_agent(self, client_socket, path, headers, request):
        user_agent = headers.get('User-Agent', 'No User-Agent found').encode('utf-8')
        self.send_response(client_socket, 200, 'text/plain', user_agent)

    def handle_files(self, client_socket, path, headers, request):
        file_name = path[len('/files/'):]
        file_path = os.path.join(os.getcwd(), file_name)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                content = f.read()
                self.send_response(client_socket, 200, 'application/octet-stream', content)
        else:
            self.send_response(client_socket, 404, 'text/plain', '404 Not Found')

    def handle_files_create(self, client_socket, path, headers, request):
        file_name = path[len('/files/'):]
        content_length = int(headers['Content-Length'])
        body = request.split('\r\n\r\n')[1][:content_length]
        file_path = os.path.join(os.getcwd(), file_name)
        
        with open(file_path, 'wb') as f:
            f.write(body.encode('utf-8'))

        self.send_response(client_socket, 201, 'text/plain', 'Created')

    def send_response(self, client_socket, status_code, content_type, body, content_encoding=None):
        if isinstance(body, str):
            body = body.encode('utf-8')
        response_line = f'HTTP/1.1 {status_code} {self.get_reason_phrase(status_code)}\r\n'
        headers = f'Content-Type: {content_type}\r\nContent-Length: {len(body)}\r\n'
        if content_encoding:
            headers += f'Content-Encoding: {content_encoding}\r\n'
        headers += '\r\n'

        response = response_line.encode('utf-8') + headers.encode('utf-8') + body
        client_socket.sendall(response)
        client_socket.close()

    def get_reason_phrase(self, status_code):
        phrases = {
            200: 'OK',
            201: 'Created',
            404: 'Not Found',
            500: 'Internal Server Error'
        }
        return phrases.get(status_code, '')

def run_server():
    server = HTTPServer()
    server.start()

if __name__ == '__main__':
    run_server()

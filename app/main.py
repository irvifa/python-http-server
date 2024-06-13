import socket
import os
from urllib.parse import unquote
from threading import Thread
import sys
from enum import Enum


class HTTPMethod(Enum):
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'
    PATCH = 'PATCH'


class HTTPRequest:
    def __init__(self, method, target, headers, body):
        self.method = method
        self.target = target
        self.headers = headers
        self.body = body

    @classmethod
    def from_raw_request(cls, raw_request):
        lines = raw_request.split('\r\n')
        request_line = lines[0].split()
        method = HTTPMethod[request_line[0]]
        target = request_line[1]

        headers = {}
        body = ''
        is_body = False

        for line in lines[1:]:
            if line == '':
                is_body = True
                continue

            if is_body:
                body += line
            else:
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    headers[key.lower()] = value

        return cls(method, target, headers, body)


class HTTPResponse:
    def __init__(self, status_code, headers, body):
        self.status_code = status_code
        self.headers = headers
        self.body = body

    def to_raw_response(self):
        response_line = f'HTTP/1.1 {self.status_code} {self.get_reason_phrase()}\r\n'
        headers = ''.join([f'{key}: {value}\r\n' for key, value in self.headers.items()])
        return response_line + headers + '\r\n' + self.body

    def get_reason_phrase(self):
        phrases = {
            200: 'OK',
            201: 'Created',
            404: 'Not Found',
            500: 'Internal Server Error',
        }
        return phrases.get(self.status_code, '')


class HTTPServer:
    def __init__(self, host='localhost', port=4221, directory='/tmp'):
        self.host = host
        self.port = port
        self.directory = directory
        self.server_socket = socket.create_server((self.host, self.port), reuse_port=True)
        self.routes = {
            '/': self.handle_root,
            '/echo': self.handle_echo,
            '/user-agent': self.handle_user_agent,
            '/files': self.handle_files,
        }

    def start(self):
        print(f'Server listening on {self.host}:{self.port}')
        while True:
            client_socket, _ = self.server_socket.accept()
            client_thread = Thread(target=self.handle_request, args=(client_socket,))
            client_thread.start()

    def handle_request(self, client_socket):
        raw_request = client_socket.recv(1024).decode('utf-8')
        request = HTTPRequest.from_raw_request(raw_request)
        target_path = request.target.split('?')[0]
        handler = self.routes.get(target_path, self.handle_dynamic_route)
        handler(client_socket, request)

    def handle_root(self, client_socket, request):
        headers = {'Content-Type': 'text/plain', 'Content-Length': len(request.body)}
        self.send_response(client_socket, HTTPResponse(200, headers, 'OK'))

    def handle_echo(self, client_socket, request):
        echoed_string = request.target.split('/echo/', 1)[-1]
        echoed_string = unquote(echoed_string)
        headers = {
            'Content-Type': 'text/plain',
            'Content-Length': str(len(echoed_string)),
        }
        request.headers.update(headers)
        self.send_response(client_socket, HTTPResponse(200, request.headers, echoed_string))

    def handle_user_agent(self, client_socket, request):
        user_agent = request.headers.get('user-agent', 'No User-Agent found')
        headers = {
            'Content-Type': 'text/plain',
            'Content-Length': str(len(user_agent)),
        }
        request.headers.update(headers)
        self.send_response(client_socket, HTTPResponse(200, request.headers, user_agent))

    def handle_files(self, client_socket, request):
        filename = request.target.split('/files/', 1)[-1]
        filepath = os.path.join(self.directory, filename)

        if request.method == HTTPMethod.GET:
            if os.path.exists(filepath):
                with open(filepath, 'rb') as file:
                    file_content = file.read()
                headers = {
                    'Content-Type': 'application/octet-stream',
                    'Content-Length': str(len(file_content)),
                }
                request.headers.update(headers)
                self.send_response(client_socket, HTTPResponse(200, request.headers, file_content.decode('utf-8')))
            else:
                self.handle_404(client_socket)
        elif request.method == HTTPMethod.POST:
            with open(filepath, 'wb') as file:
                file.write(request.body.encode('utf-8'))
            headers = {
                'Content-Type': 'application/octet-stream',
                'Content-Length': '0',
            }
            self.send_response(client_socket, HTTPResponse(201, headers, ''))

    def handle_dynamic_route(self, client_socket, request):
        if request.target.startswith('/echo/'):
            self.handle_echo(client_socket, request)
        elif request.target.startswith('/files/'):
            self.handle_files(client_socket, request)
        else:
            self.handle_404(client_socket)

    def handle_404(self, client_socket):
        headers = {'Content-Type': 'text/plain', 'Content-Length': 0}
        self.send_response(client_socket, HTTPResponse(404, headers, '404 Not Found'))

    def send_response(self, client_socket, response):
        raw_response = response.to_raw_response()
        client_socket.sendall(raw_response.encode('utf-8'))
        client_socket.close()


def run_server(directory):
    server = HTTPServer(directory=directory)
    server.start()


if __name__ == '__main__':
    directory = '/tmp'
    if len(sys.argv) > 2 and sys.argv[1] == '--directory':
        directory = sys.argv[2]
    run_server(directory)

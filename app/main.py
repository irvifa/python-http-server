import socket
import os
import gzip
import sys
from threading import Thread
from enum import Enum
from urllib.parse import unquote


class HTTPMethod(Enum):
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'


class ContentEncoding(Enum):
    NONE = 'none'
    GZIP = 'gzip'


class ContentType(Enum):
    TEXT_PLAIN = 'text/plain'
    APPLICATION_OCTET_STREAM = 'application/octet-stream'
    CUSTOM = 'custom'


class HTTPRequest:
    def __init__(self, method, target, headers, body, encodings):
        self.method = method
        self.target = target
        self.headers = headers
        self.body = body
        self.encodings = encodings

    @classmethod
    def from_raw_request(cls, raw_request):
        lines = raw_request.split('\r\n')
        request_line = lines[0].split()
        method = HTTPMethod[request_line[0]]
        target = request_line[1]

        headers = {}
        body = ''
        encodings = []
        is_body = False

        for line in lines[1:]:
            if line == '':
                is_body = True
                continue

            if is_body:
                body += line + '\n'
            else:
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    headers[key.lower()] = value
                    if key.lower() == 'accept-encoding':
                        encodings = []
                        for e in value.split(','):
                            encoding = e.strip().lower()
                            if encoding.upper() in ContentEncoding._member_names_:
                                encodings.append(ContentEncoding[encoding.upper()])
        return cls(method, target, headers, body.rstrip('\n'), encodings)

    def set_content_encoding_header(self):
        if ContentEncoding.GZIP in self.encodings:
            self.headers['Content-Encoding'] = 'gzip'


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


class HTTPServerWithRoutes:
    def __init__(self, host, port, directory):
        self.host = host
        self.port = port
        self.directory = directory
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
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
        
        # Check if there's a Content-Length header and read the body accordingly
        if 'content-length' in request.headers:
            content_length = int(request.headers['content-length'])
            body = request.body
            while len(body.encode('utf-8')) < content_length:
                body += client_socket.recv(1024).decode('utf-8')
            request.body = body

        request.set_content_encoding_header()  # Set the Content-Encoding header based on encodings
        target_path = request.target.split('?')[0]
        handler = self.routes.get(target_path, self.handle_dynamic_route)
        response = handler(request)
        raw_response = response.to_raw_response()
        client_socket.sendall(raw_response.encode('utf-8'))
        client_socket.close()

    def handle_root(self, request):
        body = 'OK'
        headers = {'Content-Type': 'text/plain'}
        if ContentEncoding.GZIP in request.encodings:
            headers['Content-Encoding'] = 'gzip'
            body = gzip.compress(body.encode('utf-8')).decode('latin1')
        headers['Content-Length'] = str(len(body))
        return HTTPResponse(200, headers, body)

    def handle_echo(self, request):
        echoed_string = request.target.split('/echo/', 1)[-1]
        echoed_string = unquote(echoed_string)
        headers = {
            'Content-Type': 'text/plain',
        }
        if ContentEncoding.GZIP in request.encodings:
            headers['Content-Encoding'] = 'gzip'
            echoed_string = gzip.compress(echoed_string.encode('utf-8')).decode('latin1')
        headers['Content-Length'] = str(len(echoed_string))
        return HTTPResponse(200, headers, echoed_string)

    def handle_user_agent(self, request):
        user_agent = request.headers.get('user-agent', 'No User-Agent found')
        headers = {
            'Content-Type': 'text/plain',
        }
        if ContentEncoding.GZIP in request.encodings:
            headers['Content-Encoding'] = 'gzip'
            user_agent = gzip.compress(user_agent.encode('utf-8')).decode('latin1')
        headers['Content-Length'] = str(len(user_agent))
        return HTTPResponse(200, headers, user_agent)

    def handle_files(self, request):
        filename = request.target.split('/files/', 1)[-1]
        filepath = os.path.join(self.directory, filename)

        if request.method == HTTPMethod.GET:
            if os.path.exists(filepath):
                with open(filepath, 'rb') as file:
                    file_content = file.read()
                headers = {
                    'Content-Type': 'application/octet-stream',
                }
                if ContentEncoding.GZIP in request.encodings:
                    headers['Content-Encoding'] = 'gzip'
                    file_content = gzip.compress(file_content).decode('latin1')
                headers['Content-Length'] = str(len(file_content))
                return HTTPResponse(200, headers, file_content.decode('utf-8'))
            else:
                return self.handle_404(request)
        elif request.method == HTTPMethod.POST:
            with open(filepath, 'wb') as file:
                file.write(request.body.encode('utf-8'))
            headers = {
                'Content-Type': 'application/octet-stream',
                'Content-Length': 0,
            }
            return HTTPResponse(201, headers, '')

    def handle_dynamic_route(self, request):
        if request.target.startswith('/echo/'):
            return self.handle_echo(request)
        elif request.target.startswith('/files/'):
            return self.handle_files(request)
        else:
            return self.handle_404(request)

    def handle_404(self, request):
        body = '404 Not Found'
        headers = {'Content-Type': 'text/plain'}
        if ContentEncoding.GZIP in request.encodings:
            headers['Content-Encoding'] = 'gzip'
            body = gzip.compress(body.encode('utf-8')).decode('latin1')
        headers['Content-Length'] = str(len(body))
        return HTTPResponse(404, headers, body)


def run_server(directory):
    server = HTTPServerWithRoutes('localhost', 4221, directory)
    server.start()


if __name__ == '__main__':
    directory = '/tmp'
    if len(sys.argv) > 2 and sys.argv[1] == '--directory':
        directory = sys.argv[2]
    run_server(directory)

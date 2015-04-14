import re
from optparse import OptionParser
from itertools import cycle
from urlparse import urlparse, urlunparse
from BaseHTTPServer import BaseHTTPRequestHandler
from BaseHTTPServer import HTTPServer
from SocketServer import ThreadingMixIn

import requests

SERVERS = [
    ("localhost", 4723),
    ("localhost", 4823),
    ("localhost", 4923)
]


CREATE_SESSION_PAT = re.compile("^/wd/hub/session$")
EXTRACT_SESSION_PAT = re.compile("/session/([a-z0-9]+)(?:/|\\?|$)")


class AppiumServerDistpatcher(object):
    """
    Abstract interface for session dispatcher strategies. All subclasses
    must implement the get_appium_server method, and might override the
    on_session_delete method.
    """

    def get_appium_server(self, create_session_request_body):
        """
        Decides which appium server instance will handle a new session.

        :param create_session_request_body: The body of the create session 
        request, this will contain for example the desired capabilities.
        A specific dispatcher implementation may use that info to decice which 
        appium_server will handle the session.

        :returns: a (host, port) tuple where requests for the session will be
        forwared.
        """
        raise NotImplementedError("Method should be implemented by subclass")

    def on_session_delete(self, server, session_id):
        """
        Called after the proxy has forwared a DELETE session request. Might be
        used by a specific dispatcher implementation for example to tear down
        an appium server or to put it back into a pool of available servers.

        :server: the (host, port) tuple identifying the server that was handling
        the session.
        :session_id: the id of the session that was just destroyed

        """
        pass


class RoundRobinServerDistpatcher(AppiumServerDistpatcher):
    """
    Basic dispatcher implementation. It just do round robin on a list of appium
    server endpoints. It doesn't keep a list of free/busy instances or make any
    decision based on requested capabilities, or do any kind of server 
    initialization/tear down.
    """
    def __init__(self, server_list):
        self.pool = cycle(SERVERS)

    def get_appium_server(self, body):
        return self.pool.next()


class AppiumProxy(object):
    """Starts a transparent proxy server and forward calls to different appium
    servers based on a given ServerDispatcher strategy"""

    def __init__(self, host, port, dispatcher):
        """
        Starts the proxy server

        :host: the hostname/interface to bind the proxy server
        :port: the port to listed on
        :dispatcher: and instance of any AppiumServerDistpatcher subclass
        """

        #
        self.sessions = {}
        self.dispatcher = dispatcher
        HttpHandler.bootstrap = self.bootstrap
        HttpHandler.forward = self.forward
        server = ThreadedHTTPServer((host, port), HttpHandler)
        print 'Listening on %s:%d, use <Ctrl-C> to stop' % (host, port)
        server.serve_forever()


    def bootstrap(self, handler):
        """Hooks a session creation call, asking the dispatcher to provide
        an appium server to handle the session. 
        Also rewrites the location header for those clients that honor a new
        host in the resource (so hopefully the subsequent requests are directly
        sent to the appium server"""

        headers = handler.headers
        body = self._read_handler_body(handler)

        response, appium_server = self._create_new_session(headers, body)
        headers = response.headers

        #Extract the session id from the location header
        o_location = urlparse(headers["location"])

        session_id = EXTRACT_SESSION_PAT.findall(o_location.path)[0]
        self.sessions[session_id] = appium_server

        #Rewrite the location header to appium's server
        location = list(o_location)
        location[1] = "%s:%d" % appium_server
        headers["location"] = urlunparse(location)

        return response.status_code, headers, response.text


    def forward(self, method, handler):
        """Extracts the session id from the requests received by the handler
        forwards the request to the appium server in care of that session and
        returns the response to the handler so it passed back to the client"""

        match = EXTRACT_SESSION_PAT.findall(handler.path)
        if not match:
            return 404, {}, "Appium Proxy: No session provided"

        session_id = match[0]

        server = self.sessions.get(session_id)

        if not server:
            return 404, {}, "Appium Proxy: Session %s not found" % session_id

        url = "http://%s:%d%s" % (server[0], server[1], handler.path)
        body = self._read_handler_body(handler)

        response = getattr(requests, method)(url, data=body, 
            headers=handler.headers)

        if method == "delete" and response.status_code == 200:
            self.dispatcher.on_session_delete(self.sessions[session_id],
                session_id)

        return response.status_code, response.headers, response.text


    def _read_handler_body(self, handler):
        #calling read() directly on the handler's rfile can block the socket
        #So just read whatever amount of bytes is defined in the Content-Lenght
        #header
        return handler.rfile.read(
            int(handler.headers.getheader('content-length', 0)))


    def _create_new_session(self, headers, body):
        appium_server = self.dispatcher.get_appium_server(body)
        url = "http://%s:%d/wd/hub/session" % appium_server

        #Disable automatic redirects so we can get hold on the location header
        #containing the session id
        response = requests.post(url, data=body, headers=headers,
            allow_redirects=False)

        return response, appium_server


class HttpHandler(BaseHTTPRequestHandler):
    """Proxy Web Server handler"""

    bootstrap = None;
    forward = None

    def do_DELETE(self):
        """Forward DELETE requests to the corresponding server"""
        code, headers, body = self.forward("delete", self)
        self._write_response(code, headers, body)

    def do_GET(self):
        """Forward GET requests to the corresponding server"""
        code, headers, body = self.forward("get", self)
        self._write_response(code, headers, body)

    def do_POST(self):
        """Bootstraps the webdriver session creation to decide which appium
        server will handle the session. Other POST requests are forwarded 
        directly"""
        if CREATE_SESSION_PAT.findall(self.path):
            code, headers, body = self.bootstrap(self)
        else:
            code, headers, body = self.forward("post", self)

        self._write_response(code, headers, body)

    def _write_response(self, code, headers, body):
        self.send_response(code)
        for k,v in headers.iteritems():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


def main():
    parser = OptionParser()

    parser.add_option("-H", "--host", dest="host", type="string",
        default="localhost", metavar="HOSTNAME",
        help="Hostname/interface to bind the proxy")
    
    parser.add_option("-p", "--port", dest="port", type="int", default=7777,
        metavar="PORT", help="Port to listen for requests")

    (options, args) = parser.parse_args()

    AppiumProxy(options.host, options.port,RoundRobinServerDistpatcher(SERVERS))

if __name__ == '__main__':
    main()
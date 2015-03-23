#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Copyright 2012-2015 OpenBroadcaster, Inc.

This file is part of OpenBroadcaster Player.

OpenBroadcaster Player is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

OpenBroadcaster Player is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with OpenBroadcaster Player.  If not, see <http://www.gnu.org/licenses/>.
"""

import obplayer

import os
import sys
import time
import traceback

import BaseHTTPServer

from sys import version as python_version
from cgi import parse_header, parse_multipart

import json

if python_version.startswith('3'):
    from urllib.parse import parse_qs,urlparse
else:
    from urlparse import parse_qs,urlparse


class ObHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    #protocol_version = 'HTTP/1.1'
    server_version = "OpenBroadcasterHTTP/0.1"

    extensions = {
	'css' : 'text/css',
	'html' : 'text/html',
	'js' : 'application/javascript',
	'svg' : 'image/svg+xml'
    }

    def log_message(self, format, *args):
        self.server.log(self.address_string() + ' ' + format % args)

    def parse(self, data, params=None):

	ret = ''
        while data != '':
            first = data.partition('<%')
	    ret += first[0]
            second = first[2].partition('%>')
	    code = second[0].lstrip(' ')

	    try:
		if code:
		    if code.startswith('exec '):
			exec(code[5:])
		    else:
			ret += str(eval(code))
	    except Exception as e:
		#ret += '<b>Eval Error</b>: ' + '(line ' + str(ret.count('\n') + 1) + ') ' + e.__class__.__name__ + ': ' + e.args[0] + '<br>\n'
		ret += '<b>Eval Error</b>: ' + '(line ' + str(ret.count('\n') + 1) + ') ' + repr(e) + '<br>\n'

	    data = second[2]

        return ret

    def check_authorization(self):

	if not self.server.username:
	    return True

	self.authenticated = False

        authdata = self.headers.getheader('Authorization')
        if type(authdata).__name__ == 'str':
            authdata = authdata.split(' ')[-1].decode('base64')
            username = authdata.split(':')[0]
            password = authdata.split(':')[1]

	    if username == '' and password == '':
                self.admin_access = False
                self.authenticated = True
            elif username == self.server.username and password == self.server.password:
                self.admin_access = True
                self.authenticated = True

        return self.authenticated

    def send_content(self, code, mimetype, content, headers=None):
	self.send_response(code)
	if headers:
	    for name, value in headers:
		self.send_header(name, value)
        self.send_header('Content-Type', mimetype)
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def send_404(self):
	self.send_content(404, 'text/plain', "404 Not Found")

    def do_GET(self):
	url = urlparse(self.path)
	params = parse_qs(url.query, keep_blank_values=True)

        if self.check_authorization() == False:
	    self.send_content(401, 'text/plain', "Authorization Required", [ ('WWW-Authenticate', 'Basic realm="Secure Area"') ])
            return

	# handle commands sent via GET
        if url.path.startswith('/command/'):
	    command = url.path[9:]

	    try:
		command_func = getattr(self.server, 'command_' + url.path[9:])
	    except AttributeError:
		self.send_404()
		return

	    ret = command_func()
	    self.send_content(200, 'application/json', json.dumps(ret))
	    return

	if not self.is_valid_path(url.path):
	    self.send_404()
	    return

	filename = self.server.root + '/' + url.path[1:]

	# If the path resolves to a directory, then set the filename to the index.html file inside that directory
	if os.path.isdir(filename):
	    filename = filename.strip('/') + '/index.html'

	# server up the file
	if os.path.isfile(filename):
	    self.extension = self.get_extension(filename)
	    self.mimetype = self.get_mimetype(filename)

	    with open(filename, 'r') as f:
		contents = f.read()
		if self.extension == 'html':
		    contents = self.parse(contents, params)
		self.send_content(200, self.mimetype, contents)
		return

	# send error if nothing found
	self.send_404()

    def do_POST(self):

        if self.check_authorization() == False:
	    self.send_content(401, 'text/plain', "Authorization Required", [ ('WWW-Authenticate', 'Basic realm="Secure Area"') ])
            return

	# empty post doesn't provide a content-type.
	ctype = None
        try:
            (ctype, pdict) = parse_header(self.headers['content-type'])
        except:
	    pass

        if ctype == 'multipart/form-data':
            postvars = parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers['content-length'])
            postvars = parse_qs(self.rfile.read(length), keep_blank_values=True)
        else:
            postvars = {}

	ret = self.server.handle_post(self.path, postvars, self.admin_access)

        self.send_content(200, 'application/json', json.dumps(ret))

    @staticmethod
    def is_valid_path(path):
	if not path[0] == '/':
	    return False
	for name in path.split('/'):
	    if name == '.' or name == '..':
		return False
	return True

    @staticmethod
    def get_extension(filename):
	return filename.rpartition('.')[2]

    @staticmethod
    def get_mimetype(filename):
	extension = ObHTTPRequestHandler.get_extension(filename)
	if extension in ObHTTPRequestHandler.extensions:
	    return ObHTTPRequestHandler.extensions[extension]
	else:
	    return 'text/plain'



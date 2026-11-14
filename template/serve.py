"""Static demo hosting with byte ranges for mobile MP4 playback."""
import functools
import http.server
import os
import re
import shutil
import sys


class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        self.remaining = None
        path = self.translate_path(self.path)
        header = self.headers.get('Range', '')
        if not header or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip())
        if not match or not any(match.groups()):
            self.send_error(416, 'Invalid range')
            return None
        left, right = match.groups()
        start = int(left) if left else max(0, size-int(right))
        end = min(int(right),size-1) if left and right else size-1
        if start >= size or start > end:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return None
        file = open(path, 'rb')
        file.seek(start)
        self.remaining = end-start+1
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(self.remaining))
        self.end_headers()
        return file

    def copyfile(self, source, outputfile):
        if self.remaining is None:
            return shutil.copyfileobj(source,outputfile)
        while self.remaining:
            chunk=source.read(min(65536,self.remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            self.remaining-=len(chunk)


if __name__ == '__main__':
    http.server.ThreadingHTTPServer(('0.0.0.0',8000),functools.partial(Handler,directory=sys.argv[1] if len(sys.argv)>1 else '.')).serve_forever()

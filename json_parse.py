from json import JSONDecoder
from functools import partial
from time import sleep
import re


def json_parse(fileobj, decoder=JSONDecoder(), buffersize=2048, seek_offset = None):
    buffer = ''
    if type(seek_offset) is int:
        fileobj.seek(seek_offset)
        buffer = fileobj.read(1000000)
        offset = re.search('{\n.*"lat', buffer).span(0)[0]
        buffer = buffer[offset:]
    for chunk in iter(partial(fileobj.read, buffersize), ''):
         chunk = re.sub('\{\n  "locations": \[', '', chunk)
         buffer += chunk
         buffer = re.sub('^, ', '', buffer)
#         print(chunk)
#         sleep(0.5)

         while buffer:
             try:
#                 sleep(0.5)
                 result, index = decoder.raw_decode(buffer)
                 yield result
                 buffer = buffer[index:].lstrip()
                 buffer = re.sub('^, ', '', buffer)
             except ValueError:
                 # Not enough data to decode, read more
                 print(len(buffer))
                 if len(buffer) > 800000:
                    print(buffer)
                    print('=========================')
                    print(repr(buffer))
                    exit()
                 break

with open('Records.json', 'r') as infh:
    print("open")
    for data in json_parse(infh, seek_offset = 800000000):
        print(data, "\n----")
        # process object


#!/usr/bin/env python

from __future__ import print_function

import argparse
import errno
import io
import json
import logging
import os
import shutil
import sys
import tarfile
import gzip
import tempfile

from contextlib import closing


LOG = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument('--ignore-errors', '-i',
                   action='store_true',
                   help='Ignore OS errors when extracting files')
    p.add_argument('--output', '-o',
                   default='.',
                   help='Output directory (defaults to ".")')
    p.add_argument('--layers',
                   action='store_true',
                   help='List layers in an image')
    p.add_argument('--list', '--ls',
                   action='store_true',
                   help='List images/tags contained in archive')
    p.add_argument('--layer', '-l',
                   action='append',
                   help='Extract only the specified layer')
    p.add_argument('--no-whiteouts', '-W',
                   action='store_true',
                   help='Do not process whiteout (.wh.*) files')

    g = p.add_argument_group('Logging options')
    g.add_argument('--verbose', '-v',
                   action='store_const',
                   const=logging.INFO,
                   dest='loglevel')
    g.add_argument('--debug', '-d',
                   action='store_const',
                   const=logging.DEBUG,
                   dest='loglevel')

    p.add_argument('image', nargs='?')

    p.set_defaults(level=logging.WARN)
    return p.parse_args()


def parse_image_spec(image):
    try:
        path, base = image.rsplit('/', 1)
    except ValueError:
        path, base = None, image
    try:
        name, tag = base.rsplit(':', 1)
    except ValueError:
        name, tag = base, 'latest'
    name = path + '/' + name if path else name
    return name, tag


def main():
    args = parse_args()
    logging.basicConfig(level=args.loglevel)

    stdin = io.open(sys.stdin.fileno(), 'rb')

    with tempfile.NamedTemporaryFile() as fd:
        while True:
            data = stdin.read(8192)
            if not data:
                break
            fd.write(data)
        fd.seek(0)
        with tarfile.TarFile(fileobj=fd) as img:
            manifest = img.extractfile('manifest.json')
            manifest = json.loads(manifest.read().decode('utf-8'))[0]

            if args.list:
                for name, tags in repos.items():
                    print('%s: %s' % (
                        name,
                        ' '.join(tags)))
                sys.exit(0)

            if not os.path.isdir(args.output):
                os.mkdir(args.output)

            for layer in manifest['Layers']:
                if args.layer and id not in args.layer:
                    continue

                LOG.info('extracting layer %s', layer)
                layer_obj = img.extractfile(layer)

                # test if gzip
                pos = layer_obj.tell()
                head_bits = layer_obj.read(2)
                layer_obj.seek(pos) # reset back to original position
                isGzip = (head_bits == b'\x1f\x8b')

                if isGzip:
                    tar = tarfile.open(fileobj=gzip.open(layer_obj), mode='r:')
                else:
                    tar = tarfile.open(fileobj=layer_obj, mode='r:')

                with tar:
                    tar.extractall(path=args.output)
                    if not args.no_whiteouts:
                        LOG.info('processing whiteouts')
                        for member in tar.getmembers():
                            path = os.path.join(args.output, member.path)
                            if path.startswith('.wh.') or '/.wh.' in path:
                                if path.startswith('.wh.'):
                                    newpath = path[4:]
                                else:
                                    newpath = path.replace('/.wh.', '/')

                                try:
                                    LOG.info('removing path %s', newpath)
                                    os.unlink(path)

                                    if os.path.isdir(newpath) and not os.path.islink(newpath):
                                        shutil.rmtree(newpath)
                                    else:
                                        os.unlink(newpath)
                                except OSError as err:
                                    if err.errno != errno.ENOENT:
                                        raise


if __name__ == '__main__':
    main()

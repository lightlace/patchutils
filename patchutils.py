#!/usr/bin/python
# -*- coding: utf-8 -*-,
"""Classes to represent patch files."""

from __future__ import print_function
from builtins import range

__all__ = [
    'Change', 'Hunk', 'FileInfo', 'Header', 'Patch', 'PatchFile',
    'Reader', 'LineReader', 'FileReader'
]

import sys
import re
import datetime
import dateutil.parser

ANY_DIFF = 0
CONTEXT_DIFF = 1
NORMAL_DIFF = 2
ED_DIFF = 3
NEW_CONTEXT_DIFF = 4
UNI_DIFF = 5
GIT_BINARY_DIFF = 6

__all__.extend([_var for _var in globals().keys() if _var.endswith('_DIFF')])

re_cmd = re.compile(r'(\d+)(?:,(\d+))?([acd])(\d+)(?:,(\d+))?[ \t]*\r?\n')
re_cstring = re.compile(r'("(?:\\.|[^"\\])*")(.*)')
re_unescape = re.compile(r'\\[0-7]{1,3}|\\x[0-9a-fA-F]+|\\.')
re_tabterm = re.compile(r'([^\t]*)\t(.*)')
re_edcmd = re.compile(r'(?:(?:\d+)?([aicd]|s/.//)|\d+,\d+([cd]|s/.//))[ \t]*\r?\n')
re_gitindex = re.compile(r'[0-9a-f]+\.\.[0-9a-f]+(?:\s+(.*))?$')
re_unihunk = re.compile(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: (.*))?')

def fetchmode(spec):
    try:
        return int(spec, base=8)
    except ValueError:
        return 0

def unescape(match):
    seq = match.group(0)[1:]
    if seq.isdigit():
        return chr(int(seq, base=8) & 0xff)
    elif seq[0] == 'x':
        if len(seq) < 2:
            raise ValueError('\\x with no following hex digits')
        return chr(int(seq[1:], base=16) & 0xff)
    else:
        try:
            return '\a\b\f\n\r\t\v\\\"'['abfnrtv\\"'.index(seq)]
        except ValueError:
            raise ValueError("Invalid escape sequence '\\%s'" % seq)

def parse_c_name(spec):
    match = re_cstring.match(spec)
    if match is None:
        # unterminated C string
        return (None, spec)
    try:
        return (re_unescape.sub(unescape, match.group(1)), match.group(2))
    except ValueError:
        # wrong escape sequence
        return (None, spec)

def parse_name(spec, tabterm=False):
    spec = spec.lstrip()
    if spec.startswith('"'):
        return parse_c_name(spec)

    if tabterm:
        match = re_tabterm.match(spec)
        if match:
            return (match.group(1).rstrip(), match.group(2))
    return re.match('(\S*)\s*(.*)', spec).groups()

class Reader(object):
    def __init__(self, value=None):
        self.tab_size = 8
        self.indent = 0
        self.rfc934_nesting = 0
        self.strip_cr = False
        self.set(value)

    def get_pos(self, lineoff=0):
        raise NotImplementedError()

    def set_pos(self, pos):
        raise NotImplementedError()

    def _get_line(self):
        raise NotImplementedError()

    def strip_indent(self):
        indent = 0
        for i in range(len(self.line)):
            if self.line[i] == '\t':
                indent += self.tab_size - (indent % self.tab_size)
            elif self.line[i] in ' X':
                indent += 1
            else:
                break
        self.line = self.line[i:]
        return indent

    def pget_line(self, indent, rfc934_nesting, strip_cr, skip_comments):
        needmore = True
        while needmore:
            line = self._get_line()
            if line is None:
                return False

            curindent = 0
            for i in range(len(line)):
                if curindent >= indent:
                    break
                if line[i] == '\t':
                    curindent += self.tab_size - (curindent % self.tab_size)
                elif line[i] in ' X':
                    curindent += 1
                else:
                    break

            nesting = rfc934_nesting
            while nesting > 0 and line.startswith('- ', i):
                i += 2
                nesting -= 1

            needmore = skip_comments and line.startswith('#', i)

        if not line.endswith('\n'):
            # patch unexpectedly ends in the middle of a line
            return False

        if strip_cr and line[-2:] == '\r\n':
            self.line = line[i:-2] + '\n'
        else:
            self.line = line[i:]
        return True

    def get_line(self, skip_comments=True):
        return self.pget_line(self.indent, self.rfc934_nesting,
                              self.strip_cr, skip_comments)

    def get_raw_line(self, skip_comments=True):
        return self.pget_line(0, 0, False, True)

    def get_raw_lines(self, start, end=None):
        raise NotImplementedError()

    def set(self, value):
        raise NotImplementedError()

class LineReader(Reader):
    def __init__(self, *args, **kwargs):
        super(LineReader, self).__init__(*args, **kwargs)
        self.lineno = 0

    def get_pos(self, lineoff=0):
        return self.lineno + lineoff

    def set_pos(self, pos):
        self.lineno = pos

    def _get_line(self):
        if self.lineno >= len(self.lines):
            return None
        line = self.lines[self.lineno]
        self.lineno += 1
        return line

    def get_raw_lines(self, start, end=None):
        return self.lines[start:end]

    def set(self, lines):
        self.lines = lines

class FileReader(Reader):
    def __init__(self, *args, **kwargs):
        super(FileReader, self).__init__(*args, **kwargs)
        self.lineno = 0

    def get_pos(self, lineoff=0):
        return self.lineno + lineoff

    def set_pos(self, pos):
        self.f.seek(self.line2pos[pos])
        self.lineno = pos

    def _get_line(self):
        if self.f is None:
            return None
        line = self.f.readline()
        if len(line) == 0:
            return None
        self.lineno += 1
        if len(self.line2pos) <= self.lineno:
            self.line2pos.append(self.f.tell())
        return line

    def get_raw_lines(self, start, end=None):
        lines = []
        oldpos = self.get_pos()
        self.set_pos(start)
        while self.lineno != end:
            line = self._get_line()
            if line is None:
                break
            lines.append(line)
        self.set_pos(oldpos)
        return lines

    def set(self, f):
        self.f = f
        self.line2pos = [ self.f.tell() ]

class FileInfo(object):
    def __init__(self, name=None, timestr=None, mode=None,
                 copy=False, rename=False):
        self.set_timestr(timestr)
        self.set_name(name)
        self.mode = mode
        self.copy = copy
        self.rename = rename

    def __repr__(self):
        return '%s(name=%s, timestr=%s, mode=%s, copy=%s, rename=%s)' % (
            self.__class__.__name__, repr(self.name), repr(self.timestr),
            oct(self.mode) if self.mode is not None else repr(self.mode),
            repr(self.copy), repr(self.rename))

    def set_name(self, name):
        # If the name is '/dev/null', ignore the name and mark the file
        # as being nonexistent.  The name '/dev/null' appears in patches
        # regardless of how NULL_DEVICE is spelled.
        if name is not None and len(name) > 0:
            if name == '/dev/null':
                name = None
                self.stamp = datetime.datetime.utcfromtimestamp(0)
        self.name = name

    def set_timestr(self, timestr):
        self.timestr = timestr
        self.stamp = None
        if timestr is not None and len(timestr) > 0:
            self.timestr = timestr.rstrip()
            try:
                self.stamp = dateutil.parser.parse(self.timestr)
            except ValueError:
                pass

    def set_spec(self, spec):
        (name, timestr) = parse_name(spec, tabterm=True)
        self.set_timestr(timestr)
        self.set_name(name)

def get_edcmd(line):
    match = re_edcmd.match(line)
    if not match:
        return None

    letter = match.group(1)
    if letter is None:
        letter = match.group(2)
    return letter

class Header(object):
    def __init__(self, old=None, new=None, index=None):
        self.old = FileInfo() if old is None else old
        self.new = FileInfo() if new is None else new
        self.index = index
        self.begin = self.end = None

    def __repr__(self):
        return '%s(old=%s, new=%s, index=%s)' % (
            self.__class__.__name__, repr(self.old), repr(self.new),
            repr(self.index))

class Change(object):
    __slots__ = [ 'op', 'text' ]

    def __init__(self, op, text):
        self.op = op
        self.text = text

    def __repr__(self):
        return '%s(%s, %s)' % (self.__class__.__name__,
                               repr(self.op), repr(self.text))

    def __str__(self):
        return self.op + self.text

class Hunk(object):
    def __init__(self, srcline=None, dstline=None, section=None,
                 src=None, dst=None):
        self.srcline = srcline
        self.dstline = dstline
        self.section = section
        self.src = [] if src is None else src
        self.dst = [] if dst is None else dst
        self.begin = self.end = None

    def __repr__(self):
        return '%s(srcline=%s, dstline=%s, section=%s, src=%s, dst=%s)' % (
            self.__class__.__name__, repr(self.srcline), repr(self.dstline),
            repr(self.section), repr(self.src), repr(self.dst))

    def parse(self, reader):
        return False

class Patch(object):
    """Patch base class."""

    diff_type = ANY_DIFF

    def __init__(self, header=None, hunks=None):
        """Construct a patch from its header and a list of hunks."""
        self.header = Header() if header is None else header
        self.hunks = [] if hunks is None else hunks
        self.begin = self.header.begin
        self.end = None

    def __repr__(self):
        """Return string representation of a patch.

        This looks like 'Patch(header, [<list of hunks>])'.
        """
        return '%s(%s, %s)' % (self.__class__.__name__,
                               self.header, self.hunks)

    def parse(self, reader):
        """Construct a patch by reading hunks from a Reader,
        using metadata from Header.
        """
        if self.begin is None:
            self.begin = reader.get_pos()
        self.hunks = []
        hunk = self.next_hunk()
        while hunk.parse(reader):
            self.hunks.append(hunk)
            hunk = self.next_hunk()
        self.end = reader.get_pos(-1)

class NormalHunk(Hunk):
    def parse(self, reader):
        if not reader.get_line():
            return False
        match = re_cmd.match(reader.line)
        if not match:
            reader.set_pos(reader.get_pos(-1))
            return False
        cmd = match.group(3)
        self.srcline = int(match.group(1))
        ptrn_lines = match.group(2)
        if ptrn_lines is None:
            ptrn_lines = 0 if cmd == 'a' else 1
        else:
            ptrn_lines = int(ptrn_lines) - self.srcline + 1
        self.dstline = int(match.group(4))
        repl_lines = match.group(5)

        return True

class NormalPatch(Patch):
    diff_type = NORMAL_DIFF

    def next_hunk(self):
        return NormalHunk()

class EdHunk(Hunk):
    def parse(self, reader):
        if not reader.get_line():
            return False
        self.begin = reader.get_pos(-1)
        edcmd = get_edcmd(reader.line)
        if edcmd in 'ds':
            self.end = self.begin
            return True
        while reader.get_line(False):
            if reader.line == '.\n':
                self.end = reader.get_pos(-1)
                return True
        return False

class EdPatch(Patch):
    diff_type = ED_DIFF

    def next_hunk(self):
        return EdHunk()

class UniHunk(Hunk):
    def parse(self, reader):
        if not reader.get_line():
            return False
        match = re_unihunk.match(reader.line)
        if not match:
            reader.set_pos(reader.get_pos(-1))
            return False
        self.begin = reader.get_pos(-1)
        self.srcline = int(match.group(1))
        ptrn_lines = match.group(2)
        if ptrn_lines is None:
            ptrn_lines = 1
        else:
            ptrn_lines = int(ptrn_lines)
            if ptrn_lines == 0:
                self.srcline += 1     # append rather than insert
        self.dstline = int(match.group(3))
        repl_lines = match.group(4)
        if repl_lines is None:
            repl_lines = 1
        else:
            repl_lines = int(repl_lines)
            if repl_lines == 0:
                self.dstline += 1     # append rather than insert
        self.section = match.group(5)
        while ptrn_lines > 0 or repl_lines > 0:
            if not reader.get_line() or len(reader.line) < 1:
                if repl_lines < 3:
                    line = ' \n' # assume blank lines got chopped
                else:
                    return False # unexpected EOF
            else:
                line = reader.line

            ch = line[0]
            if ch == '-':
                if ptrn_lines <= 0:
                    return False
                ptrn_lines -= 1

                change = Change(ch, line[1:])
                self.src.append(change)
            elif ch in ' =\t\n':
                if ptrn_lines <= 0 or repl_lines <= 0:
                    return False
                ptrn_lines -= 1
                repl_lines -= 1

                if ch in '\t\n':
                    # assume the space got eaten
                    change = Change(' ', line)
                else:
                    change = Change(' ', line[1:])
                self.src.append(change)
                self.dst.append(change)
            elif ch == '+':
                if repl_lines <= 0:
                    return False
                repl_lines -= 1

                change = Change(ch, line[1:])
                self.dst.append(change)
            else:
                return False
        self.end = reader.get_pos(-1)
        return True

class UniPatch(Patch):
    diff_type = UNI_DIFF

    def next_hunk(self):
        return UniHunk()

class ContextHunk(Hunk):
    def parse(self, reader):
        raise NotImplementedError()

class ContextPatch(Patch):
    diff_type = CONTEXT_DIFF

    def next_hunk(self):
        return ContextHunk()

class NewContextHunk(Hunk):
    def parse(self, reader):
        raise NotImplementedError()

class NewContextPatch(Patch):
    diff_type = NEW_CONTEXT_DIFF

    def next_hunk(self):
        return NewContextHunk()

class GitBinaryPatch(Patch):
    diff_type = GIT_BINARY_DIFF

    def next_hunk(self):
        raise NotImplementedError()

class FileHeader(object):
    def __init__(self, lines=None):
        if lines is None:
            self.lines = []
        else:
            self.lines = lines

    def __repr__(self):
        return '%s(lines=%s)' % (self.__class__.__name__, repr(self.lines))

class PatchFile(object):
    def __init__(self, reader, diff_type=ANY_DIFF, need_header=True):
        self.diff_type = diff_type
        self.header = None
        self.patches = []
        startpos = reader.get_pos()
        while self.add_patch(reader, need_header):
            if self.header is None:
                self.header = FileHeader(
                    reader.get_raw_lines(startpos,
                                         self.patches[-1].header.begin))
        if self.header is None:
            self.header = FileHeader(reader.get_raw_lines(startpos))

    def add_patch(self, reader, need_header=True):
        # Ed and normal format patches don't have filename headers.
        if self.diff_type in (ED_DIFF, NORMAL_DIFF):
            need_header = False

        edcmdpos = None
        git_diff = False
        exthdrs = False

        reader.rfc934_nesting = 0
        hdr = Header()
        patch = None
        while patch is None and reader.get_raw_line():
            indent = reader.strip_indent()
            line = reader.line
            strip_cr = (line[-2:] == '\r\n')
            if (self.diff_type in (ANY_DIFF, NORMAL_DIFF)
                and not need_header
                and re_cmd.match(line)):
                reader.strip_cr = strip_cr

                if not reader.get_raw_line():
                    break
                indent = reader.strip_indent()
                line = reader.line
                if line.startswith('< ') or line.startswith('> '):
                    start = reader.get_pos(-2)
                    reader.indent = indent
                    patch = NormalPatch()
            elif (self.diff_type in (ANY_DIFF, ED_DIFF)
                  and not need_header
                  and edcmdpos is None
                  and get_edcmd(line)):
                edcmdpos = reader.get_pos(-1)
                reader.indent = indent    # assume this for now
                reader.strip_cr = strip_cr
            elif (self.diff_type in (ANY_DIFF, CONTEXT_DIFF, NEW_CONTEXT_DIFF)
                  and line.startswith('*** ')):
                hdr.begin = reader.get_pos(-1)
                # Swap with OLD below.
                hdr.new.set_spec(line[4:])
                need_header = False
            elif line.startswith('+++ '):
                hdr.new.set_spec(line[4:])
                reader.strip_cr = strip_cr
                need_header = False
            elif line.startswith('Index:'):
                if hdr.begin is None:
                    hdr.begin = reader.get_pos(-1)
                hdr.index = line[6:].lstrip()
                if hdr.index.startswith('"'):
                    s = parse_c_name(hdr.index)
                    if s is not None:
                        hdr.index = s
                reader.strip_cr = strip_cr
                need_header = False
            elif line.startswith('Prereq:'):
                if hdr.begin is None:
                    hdr.begin = reader.get_pos(-1)
                revisions = line[7:].lstrip().split()
                if len(revisions) > 0:
                    self.revision = revisions[0]
            elif (self.diff_type in (ANY_DIFF, UNI_DIFF)
                  and line.startswith('diff --git ')):
                if exthdrs:
                    hdr.end = reader.get_pos(-2)
                    start = reader.get_pos(-1)
                    # Patch contains no hunks; any diff type will do.
                    patch = UniPatch(hdr)
                else:
                    hdr.begin = reader.get_pos(-1)
                    hdr.old.name = None
                    hdr.new.name = None
                    (old_name, s) = parse_name(line[11:])
                    if old_name is not None and len(s) > 0:
                        (new_name, s) = parse_name(s.lstrip())
                        if s.isspace():
                            hdr.old.name = old_name
                            hdr.new.name = new_name
                    git_diff = True
                    need_header = False
            elif git_diff and line.startswith('index '):
                match = re_gitindex.match(line[6:])
                if match:
                    mode = match.group(1)
                    if mode is not None:
                        hdr.old.mode = hdr.new.mode = fetchmode(mode)
                    exthdrs = True
            elif git_diff and line.startswith('old mode '):
                hdr.old.mode = fetchmode(line[9:])
                exthdrs = True
            elif git_diff and line.startswith('new mode '):
                hdr.new.mode = fetchmode(line[9:])
                exthdrs = True
            elif git_diff and line.startswith('deleted file mode '):
                hdr.old.mode = fetchmode(line[9:])
                exthdrs = True
            elif git_diff and line.startswith('new file mode '):
                hdr.new.mode = fetchmode(line[14:])
                exthdrs = True
            elif git_diff and line.startswith('rename from '):
                hdr.old.rename = True
                exthdrs = True
            elif git_diff and line.startswith('rename to '):
                hdr.new.rename = True
                exthdrs = True
            elif git_diff and line.startswith('copy from '):
                hdr.old.copy = True
                exthdrs = True
            elif git_diff and line.startswith('copy to '):
                hdr.new.copy = True
                exthdrs = True
            elif git_diff and line.startswith('GIT binary patch'):
                hdr.end = reader.get_pos(-2)
                start = reader.get_pos(-1)
                patch = GitBinaryPatch(hdr)
            else:
                i = 0
                while line.startswith('- ', i):
                    i += 2
                if line.startswith('--- ', i):
                    if hdr.begin is None:
                        hdr.begin = reader.get_pos(-1)
                    hdr.old.set_spec(line[i+4:])
                    if hdr.old.stamp is not None:
                        reader.rfc934_nesting = i // 2
                    reader.strip_cr = strip_cr
                    need_header = False

            if not need_header:
                if edcmdpos is not None and line == '.\n':
                    start = edcmdpos
                    patch = EdPatch()
                elif (self.diff_type in (ANY_DIFF, UNI_DIFF)
                      and line.startswith('@@ -')):
                    reader.indent = indent
                    hdr.end = reader.get_pos(-2)
                    start = reader.get_pos(-1)
                    patch = UniPatch(hdr)
                elif (self.diff_type in (ANY_DIFF, CONTEXT_DIFF, NEW_CONTEXT_DIFF)
                      and line.startswith('********')):
                    previndent = indent
                    if not reader.get_raw_line():
                        break
                    indent = reader.strip_indent()
                    line = reader.line
                    if (previndent == indent
                        and line.startswith('*** ')):
                        # 'new' and 'old' are backwards; swap them.
                        t = hdr.old
                        hdr.old = hdr.new
                        hdr.new = t

                        reader.indent = indent
                        reader.strip_cr = strip_cr
                        hdr.end = reader.get_pos(-2)
                        start = reader.get_pos(-1)
                        # if this is a new context diff the character
                        # just before the newline is a '*'.
                        if re.search(r'\*\r?\n$', line):
                            patch = NewContextPatch(hdr)
                        else:
                            patch = ContextPatch(hdr)

        if patch is None:
            if edcmdpos is not None:
                # nothing but deletes!?
                start = edcmdpos
                patch = EdPatch()
            elif exthdrs:
                hdr.end = reader.get_pos(-1)
                start = reader.get_pos()
                # Patch contains no hunks; any diff type will do.
                patch = UniPatch(hdr)
            else:
                return False

        reader.set_pos(start)
        patch.parse(reader)
        self.end = reader.get_pos(-1)
        self.patches.append(patch)
        return True

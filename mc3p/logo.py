import unittest
import Queue
import lepl


class Command(object):
    pass

class Command0(object):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return 'Command0[%s]' % (self.name)

class Command1(object):
    def __init__(self, name, value=None):
        self.name = name
        self.value = value

    def __repr__(self):
        return 'Command1[%s, %s]' % (self.name, self.value)

class Command2(object):
    def __init__(self, name, value1=None, value2=None):
        self.name = name
        self.value1 = value1
        self.value2 = value2

    def __repr__(self):
        return 'Command2[%s, %s, %s]' % (self.name, self.value1, self.value2)


def NoCase(text):
    return lepl.Regexp(''.join('[{0}{1}]'.format(c.lower(), c.upper()) for c in text))


def constant(x):
    return lambda _: x


def Identifier(*names):
    return lepl.Or(*[NoCase(n) for n in names]) >> constant(names[0])


def Grammar():
    from lepl import *

    number = Real() >> float
    integer = Integer() >> int
    space = ~Space()[1:]

    flat_expr = Delayed()
    expr = flat_expr > List
    instr_list = ~Literal('[') & expr & ~Literal(']')

    cmd_fd = Identifier('forward', 'fd') & Optional(space & number) > args(Command1)
    cmd_bk = Identifier('back', 'bk') & Optional(space & number) > args(Command1)
    cmd_lt = Identifier('left', 'lt') & space & number > args(Command1)
    cmd_rt = Identifier('right', 'rt') & space & number > args(Command1)
    cmd_pu = Identifier('penup', 'pu') > args(Command0)
    cmd_pd = Identifier('pendown', 'pd') > args(Command0)
    cmd_setpen = Identifier('setpen') & space & integer & space & integer > args(Command2)
    cmd_repeat = Identifier('repeat') & space & integer & space & instr_list > args(Command2)

    all_cmd = cmd_fd | cmd_bk | cmd_setpen | cmd_lt | cmd_rt | cmd_repeat | cmd_pu | cmd_pd

    cmd_split = ~Space()[:] & ~Literal(';') & ~Space()[:]
    expr += ~Space()[:] & all_cmd & Optional(cmd_split & flat_expr) & Optional(cmd_split) & ~Space()[:]

    return expr



def CFList(cmd):
    for subcmd in cmd:
        yield subcmd


def CFRepeat(cmd):
    for i in xrange(cmd.value1):
        yield cmd.value2


class Logo(object):
    def __init__(self):
        self.queue = Queue.Queue()
        self.runstack = []
        self.expr = Grammar()

    def parse(self, s):
        ast = self.expr.parse(s)
        self.queue.put(ast[0])

    def run(self, cmd):
        if isinstance(cmd, lepl.List):
            for subcmd in cmd:
                self.run(subcmd)
        else:
            if cmd.name == 'repeat':
                for i in xrange(cmd.value1):
                    self.run(cmd.value2)
            else:
                print 'Running %s...' % cmd.name

    def __iter__(self):
        return self

    def next(self):
        instn = None

        while self.runstack and not instn:
            try:
                instn = self.runstack[-1].next()
            except StopIteration:
                self.runstack.pop()

        if not instn:
            try:
                instn = self.queue.get(False)
            except Queue.Empty:
                raise StopIteration()

        if isinstance(instn, lepl.List):
            self.runstack.append(CFList(instn))
            return self.next()

        if instn.name == 'repeat':
            self.runstack.append(CFRepeat(instn))
            return self.next()

        return instn


class BasicTest(unittest.TestCase):
    def setUp(self):
        self.expr = Grammar()

    def _run(self, s):
        print '-----', s
        d = self.expr.parse(s)
        print d[0]
        assert len(d) == 1

    def testPlop(self):
        self._run('pu')
        self._run('fD')
        self._run('fd  1')
        self._run('fd 1;')
        self._run('bk')
        self._run('bk ')
        self._run('bk -41.1')
        self._run('lt 12')
        self._run('rt 12')
        self._run('setpen 10 11')

        self._run('repeat 42 [ fd ] ')
        self._run('repeat 42 [ fd 1; lt 1 ;] ')

    def testRecursive(self):
        self._run('fd 2; bk 43')
        self._run('fd ; ')

    def testInvalid(self):
        self.assertRaises(lepl.FullFirstMatchException, self.expr.parse, 'setpen 1')
        self.assertRaises(lepl.FullFirstMatchException, self.expr.parse, 'fd a')
        self.assertRaises(lepl.FullFirstMatchException, self.expr.parse, 'rt 2 3')
        self.assertRaises(lepl.FullFirstMatchException, self.expr.parse, 'lt')
        self.assertRaises(lepl.FullFirstMatchException, self.expr.parse, 'repeat a [ fd 1]')


class RunTest(unittest.TestCase):
    def _run(self, s):
        print '-----', s
        d = self.expr.parse(s)
        print d[0]
        assert len(d) == 1

    def testPlop(self):
        l = Logo()
        l.parse('fd 1; repeat 3 [ pu ; repeat 2 [ fd ] ; pd ]')

        for instn in l:
            print 'Running %s ...' % instn


if __name__ == '__main__':
    unittest.main()
    print 'Testing...'

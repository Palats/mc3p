import unittest
import lepl
from lepl import *


def NoCase(text):
    return Regexp(''.join('[{0}{1}]'.format(c.lower(), c.upper()) for c in text))

def constant(x):
    return lambda _: x

def Command(*names):
    return Or(*[NoCase(n) for n in names]) >> constant(names[0])

number = Real() >> float
integer = Integer() >> int

cmd_fd = Command('forward', 'fd') & Optional(~Space()[1:] & number)
cmd_bk = Command('back', 'bk') & Optional(~Space()[1:] & number)
cmd_lt = Command('left', 'lt') & ~Space()[1:] & number
cmd_rt = Command('right', 'rt') & ~Space()[1:] & number
cmd_setpen = NoCase('setpen') & ~Space() & (UnsignedInteger() >> int) & ~Space() & (UnsignedInteger() >> int)

cmd = ~Space()[:] & ( cmd_fd | cmd_bk | cmd_setpen | cmd_lt | cmd_rt ) & ~Space()[:]

expr = Delayed()
expr += cmd & Optional(~Literal(';') & expr)


class BasicTest(unittest.TestCase):
    def testPlop(self):
        print expr.parse('fD')
        print expr.parse('fd  1')
        print expr.parse('bk')
        print expr.parse('bk -41.1')
        print expr.parse('lt 12')
        print expr.parse('rt 12')
        print expr.parse('setpen 10 11')

    def testRecursive(self):
        print expr.parse('fd 2; bk 43')

    def testInvalid(self):
        self.assertRaises(FullFirstMatchException, expr.parse, 'setpen 1')
        self.assertRaises(FullFirstMatchException, expr.parse, 'fd a')
        self.assertRaises(FullFirstMatchException, expr.parse, 'rt 2 3')
        self.assertRaises(FullFirstMatchException, expr.parse, 'lt')


if __name__ == '__main__':
    unittest.main()
    print 'Testing...'

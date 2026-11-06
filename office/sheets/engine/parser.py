"""Recursive-descent parser.

    compare : concat ((EQ | NE | LT | GT | LE | GE) concat)*
    concat  : expr (AMP expr)*
    expr    : term ((PLUS | MINUS) term)*
    term    : power ((MUL | DIV) power)*
    power   : unary (POW power)?          # right-associative
    unary   : (PLUS | MINUS) unary | primary
    primary : NUMBER | STRING | ERROR
            | CELL (COLON CELL)?           # single ref or range
            | IDENT LPAREN args? RPAREN    # function call
            | IDENT                        # TRUE, FALSE, or an unknown name
            | LPAREN compare RPAREN
    args    : compare (COMMA compare)*

The levels follow Excel's precedence: comparisons bind loosest, then &, then
+ and -, then * and /, then ^, and unary minus binds tightest.

Because unary sits *below* power, =-2^2 parses as (-2)^2 = 4, the same as
Excel. Python would give -4. tests/test_parser.py pins this down.
"""
from . import lexer as L
from .ast_nodes import (
    BinOp, Bool, Call, CellRef, ErrorLit, Name, Number, RangeRef, Str, UnaryOp,
)
from .lexer import FormulaSyntaxError, tokenize
from .refs import split_ref


class Parser:
    def __init__(self, text: str):
        self.tokens = tokenize(text)
        self.i = 0

    @property
    def current(self):
        return self.tokens[self.i]

    def eat(self, type_):
        tok = self.current
        if tok.type != type_:
            raise FormulaSyntaxError(f"expected {type_}, got {tok.type} at {tok.pos}")
        self.i += 1
        return tok

    def parse(self):
        node = self.compare()
        if self.current.type != L.EOF_:
            raise FormulaSyntaxError(f"unexpected {self.current.type} at {self.current.pos}")
        return node

    _COMPARISONS = (L.EQ, L.NE, L.LT, L.GT, L.LE, L.GE)

    def compare(self):
        node = self.concat()
        while self.current.type in self._COMPARISONS:
            op = self.eat(self.current.type).value
            node = BinOp(op, node, self.concat())
        return node

    def concat(self):
        node = self.expr()
        while self.current.type == L.AMP:
            self.eat(L.AMP)
            node = BinOp("&", node, self.expr())
        return node

    def expr(self):
        node = self.term()
        while self.current.type in (L.PLUS, L.MINUS):
            op = self.eat(self.current.type).value
            node = BinOp(op, node, self.term())
        return node

    def term(self):
        node = self.power()
        while self.current.type in (L.MUL, L.DIV):
            op = self.eat(self.current.type).value
            node = BinOp(op, node, self.power())
        return node

    def power(self):
        node = self.unary()
        if self.current.type == L.POW:
            self.eat(L.POW)
            node = BinOp("^", node, self.power())
        return node

    def unary(self):
        if self.current.type in (L.PLUS, L.MINUS):
            op = self.eat(self.current.type).value
            return UnaryOp(op, self.unary())
        return self.primary()

    def primary(self):
        tok = self.current
        if tok.type == L.NUMBER:
            self.eat(L.NUMBER)
            return Number(tok.value)
        if tok.type == L.STRING:
            self.eat(L.STRING)
            return Str(tok.value)
        if tok.type == L.ERROR:
            self.eat(L.ERROR)
            return ErrorLit(tok.value)
        if tok.type == L.CELL:
            self.eat(L.CELL)
            start = CellRef(*split_ref(tok.value))
            if self.current.type == L.COLON:
                self.eat(L.COLON)
                end = CellRef(*split_ref(self.eat(L.CELL).value))
                return RangeRef(start, end)
            return start
        if tok.type == L.IDENT:
            self.eat(L.IDENT)
            if self.current.type != L.LPAREN:
                if tok.value in ("TRUE", "FALSE"):
                    return Bool(tok.value == "TRUE")
                return Name(tok.value)
            self.eat(L.LPAREN)
            args = []
            if self.current.type != L.RPAREN:
                args.append(self.compare())
                while self.current.type == L.COMMA:
                    self.eat(L.COMMA)
                    args.append(self.compare())
            self.eat(L.RPAREN)
            return Call(tok.value, tuple(args))
        if tok.type == L.LPAREN:
            self.eat(L.LPAREN)
            node = self.compare()
            self.eat(L.RPAREN)
            return node
        raise FormulaSyntaxError(f"unexpected {tok.type} at {tok.pos}")


def parse(text: str):
    """Parse formula text. Pass it without the leading '='."""
    return Parser(text).parse()

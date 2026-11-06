"""Turn formula text (without the leading '=') into a list of tokens."""
from dataclasses import dataclass

NUMBER = "NUMBER"
STRING = "STRING"
CELL = "CELL"
IDENT = "IDENT"
PLUS, MINUS, MUL, DIV, POW = "PLUS", "MINUS", "MUL", "DIV", "POW"
COLON, COMMA, LPAREN, RPAREN = "COLON", "COMMA", "LPAREN", "RPAREN"
AMP = "AMP"  # & joins text
EQ, NE, LT, GT, LE, GE = "EQ", "NE", "LT", "GT", "LE", "GE"
ERROR = "ERROR"  # an error literal such as #REF!, left behind by copy and paste
EOF_ = "EOF"

ERROR_CODES = ("#DIV/0!", "#NAME?", "#VALUE!", "#REF!", "#NUM!", "#CIRC!", "#ERROR!", "#N/A")

_SINGLE = {
    "+": PLUS, "-": MINUS, "*": MUL, "/": DIV, "^": POW,
    ":": COLON, ",": COMMA, "(": LPAREN, ")": RPAREN, "&": AMP, "=": EQ,
}
# Checked before single characters so "<=" isn't read as "<" then "=".
_DOUBLE = {"<>": NE, "<=": LE, ">=": GE}
_COMPARE_SINGLE = {"<": LT, ">": GT}


class FormulaSyntaxError(Exception):
    """Raised by the lexer and parser. The sheet shows it as #ERROR!."""


@dataclass(frozen=True)
class Token:
    type: str
    value: object
    pos: int


class Lexer:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def _peek(self, offset=0):
        i = self.pos + offset
        return self.text[i] if i < len(self.text) else ""

    def tokens(self) -> list[Token]:
        out = []
        while True:
            tok = self.next_token()
            out.append(tok)
            if tok.type == EOF_:
                return out

    def next_token(self) -> Token:
        while self._peek().isspace():
            self.pos += 1
        start = self.pos
        ch = self._peek()
        if ch == "":
            return Token(EOF_, None, start)
        if ch.isdigit() or (ch == "." and self._peek(1).isdigit()):
            return self._number()
        if ch == '"':
            return self._string()
        if ch.isalpha() or ch == "_" or ch == "$":
            return self._word()
        if ch == "#":
            for code in ERROR_CODES:
                if self.text.startswith(code, start):
                    self.pos += len(code)
                    return Token(ERROR, code, start)
        two = self.text[start:start + 2]
        if two in _DOUBLE:
            self.pos += 2
            return Token(_DOUBLE[two], two, start)
        if ch in _COMPARE_SINGLE:
            self.pos += 1
            return Token(_COMPARE_SINGLE[ch], ch, start)
        if ch in _SINGLE:
            self.pos += 1
            return Token(_SINGLE[ch], ch, start)
        raise FormulaSyntaxError(f"unexpected character {ch!r} at {start}")

    def _number(self) -> Token:
        start = self.pos
        while self._peek().isdigit():
            self.pos += 1
        if self._peek() == ".":
            self.pos += 1
            while self._peek().isdigit():
                self.pos += 1
        # Scientific notation: 1.5E3, 2e-4
        if self._peek() in ("e", "E") and (
            self._peek(1).isdigit() or (self._peek(1) in "+-" and self._peek(2).isdigit())
        ):
            self.pos += 2
            while self._peek().isdigit():
                self.pos += 1
        return Token(NUMBER, float(self.text[start:self.pos]), start)

    def _string(self) -> Token:
        start = self.pos
        self.pos += 1  # opening quote
        chars = []
        while True:
            ch = self._peek()
            if ch == "":
                raise FormulaSyntaxError(f"unterminated string starting at {start}")
            self.pos += 1
            if ch == '"':
                if self._peek() == '"':  # "" is an escaped quote, as in Excel
                    chars.append('"')
                    self.pos += 1
                    continue
                return Token(STRING, "".join(chars), start)
            chars.append(ch)

    def _word(self) -> Token:
        # Letters followed by digits make a cell (A1, $B$2); anything else is a
        # function name. A word followed by '(' is always a function, so LOG10(...)
        # would still lex as IDENT.
        start = self.pos
        if self._peek() == "$":
            self.pos += 1
        while self._peek().isalpha():
            self.pos += 1
        letters_end = self.pos
        if self._peek() == "$":
            self.pos += 1
        digits_start = self.pos
        while self._peek().isdigit():
            self.pos += 1
        has_letters = letters_end > start + (self.text[start] == "$")
        is_cell = has_letters and self.pos > digits_start and not (
            self._peek().isalpha() or self._peek() == "_"
        )
        if is_cell and self._peek() != "(":
            return Token(CELL, self.text[start:self.pos].upper(), start)
        # Not a cell: rewind and read a plain identifier.
        self.pos = start
        if self._peek() == "$":
            raise FormulaSyntaxError(f"unexpected '$' at {start}")
        # Note: "" in "_." is True in Python, so check for end of input first.
        while self._peek() and (self._peek().isalnum() or self._peek() in "_."):
            self.pos += 1
        return Token(IDENT, self.text[start:self.pos].upper(), start)


def tokenize(text: str) -> list[Token]:
    return Lexer(text).tokens()

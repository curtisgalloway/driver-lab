// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::{sandbox::ScratchResolver, Cli, InventoryArgs};
use std::collections::HashMap;
use std::io::Write;

pub fn strip_comments(text: &str) -> String {
    let mut out = String::new();
    let mut chars = text.chars().peekable();
    let mut in_block = false;
    let mut in_line = false;
    let mut in_string = false;
    let mut in_char = false;

    while let Some(c) = chars.next() {
        if in_block {
            if c == '*' && chars.peek() == Some(&'/') {
                chars.next();
                in_block = false;
                out.push(' ');
            }
        } else if in_line {
            if c == '\n' {
                in_line = false;
                out.push(c);
            }
        } else if in_string {
            out.push(c);
            if c == '\\' {
                if let Some(n) = chars.next() {
                    out.push(n);
                }
            } else if c == '"' {
                in_string = false;
            }
        } else if in_char {
            out.push(c);
            if c == '\\' {
                if let Some(n) = chars.next() {
                    out.push(n);
                }
            } else if c == '\'' {
                in_char = false;
            }
        } else {
            if c == '/' && chars.peek() == Some(&'*') {
                chars.next();
                in_block = true;
                out.push(' ');
            } else if c == '/' && chars.peek() == Some(&'/') {
                chars.next();
                in_line = true;
                out.push(' ');
            } else if c == '"' {
                in_string = true;
                out.push(c);
            } else if c == '\'' {
                in_char = true;
                out.push(c);
            } else {
                out.push(c);
            }
        }
    }
    out
}

#[derive(Debug, Clone, PartialEq)]
enum Token {
    Int(u32, bool),
    Name(String),
    Plus,
    Minus,
    Star,
    Slash,
    Percent,
    Shl,
    Shr,
    Amp,
    Pipe,
    Caret,
    Tilde,
    LParen,
    RParen,
    Comma,
}

fn tokenize(source: &str, names: &HashMap<String, u32>) -> Result<Vec<Token>, String> {
    let mut tokens = Vec::new();
    let mut chars = source.char_indices().peekable();

    while let Some(&(_i, c)) = chars.peek() {
        if c.is_ascii_whitespace() {
            chars.next();
            continue;
        }

        if c == '+' {
            chars.next();
            tokens.push(Token::Plus);
            continue;
        }
        if c == '-' {
            chars.next();
            tokens.push(Token::Minus);
            continue;
        }
        if c == '*' {
            chars.next();
            tokens.push(Token::Star);
            continue;
        }
        if c == '/' {
            chars.next();
            tokens.push(Token::Slash);
            continue;
        }
        if c == '%' {
            chars.next();
            tokens.push(Token::Percent);
            continue;
        }
        if c == '~' {
            chars.next();
            tokens.push(Token::Tilde);
            continue;
        }
        if c == '^' {
            chars.next();
            tokens.push(Token::Caret);
            continue;
        }
        if c == '(' {
            chars.next();
            tokens.push(Token::LParen);
            continue;
        }
        if c == ')' {
            chars.next();
            tokens.push(Token::RParen);
            continue;
        }
        if c == ',' {
            chars.next();
            tokens.push(Token::Comma);
            continue;
        }

        if c == '<' {
            chars.next();
            if let Some(&(_, '<')) = chars.peek() {
                chars.next();
                tokens.push(Token::Shl);
            } else {
                return Err("unsupported token: <".into());
            }
            continue;
        }
        if c == '>' {
            chars.next();
            if let Some(&(_, '>')) = chars.peek() {
                chars.next();
                tokens.push(Token::Shr);
            } else {
                return Err("unsupported token: >".into());
            }
            continue;
        }
        if c == '&' {
            chars.next();
            tokens.push(Token::Amp);
            continue;
        }
        if c == '|' {
            chars.next();
            tokens.push(Token::Pipe);
            continue;
        }

        if c.is_ascii_digit() {
            let mut num_str = String::new();
            let mut base = 10;
            if c == '0' {
                num_str.push(c);
                chars.next();
                if let Some(&(_, 'x')) | Some(&(_, 'X')) = chars.peek() {
                    num_str.push(chars.next().unwrap().1);
                    base = 16;
                } else {
                    base = 8;
                }
            }
            while let Some(&(_, ch)) = chars.peek() {
                if ch.is_ascii_alphanumeric() {
                    num_str.push(ch);
                    chars.next();
                } else {
                    break;
                }
            }

            let num_str_lower = num_str.to_lowercase();
            let mut num_part = num_str_lower.as_str();
            let mut unsigned = false;

            if num_part.ends_with("ull") || num_part.ends_with("llu") {
                unsigned = true;
                num_part = &num_part[..num_part.len() - 3];
            } else if num_part.ends_with("ul") || num_part.ends_with("lu") {
                unsigned = true;
                num_part = &num_part[..num_part.len() - 2];
            } else if num_part.ends_with("ll") {
                num_part = &num_part[..num_part.len() - 2];
            } else if num_part.ends_with("l") {
                num_part = &num_part[..num_part.len() - 1];
            } else if num_part.ends_with("u") {
                unsigned = true;
                num_part = &num_part[..num_part.len() - 1];
            }

            let value = if base == 16 {
                if num_part.len() > 2 {
                    i64::from_str_radix(&num_part[2..], 16).map_err(|_| "invalid hex")?
                } else {
                    0
                }
            } else if base == 8 {
                i64::from_str_radix(num_part, 8).map_err(|_| "invalid octal")?
            } else {
                num_part.parse::<i64>().map_err(|_| "invalid decimal")?
            };

            if base != 10 && value > 0x7fffffff {
                unsigned = true;
            }
            if !(0..=0xffffffff).contains(&value) {
                return Err("integer outside unsigned 32-bit range".into());
            }
            tokens.push(Token::Int(value as u32, unsigned));
            continue;
        }

        if c.is_ascii_alphabetic() || c == '_' {
            let mut name = String::new();
            while let Some(&(_, ch)) = chars.peek() {
                if ch.is_ascii_alphanumeric() || ch == '_' {
                    name.push(ch);
                    chars.next();
                } else {
                    break;
                }
            }
            if !names.contains_key(&name)
                && name != "BIT"
                && name != "BIT_ULL"
                && name != "GENMASK"
                && name != "GENMASK_ULL"
            {
                return Err(format!("unsupported name: {}", name));
            }
            tokens.push(Token::Name(name));
            continue;
        }

        return Err(format!("unsupported token: {}", c));
    }
    Ok(tokens)
}

fn precedence(token: &Token) -> u8 {
    match token {
        Token::Pipe => 1,
        Token::Caret => 2,
        Token::Amp => 3,
        Token::Shl | Token::Shr => 4,
        Token::Plus | Token::Minus => 5,
        Token::Star | Token::Slash | Token::Percent => 6,
        _ => 0,
    }
}

struct Parser<'a> {
    tokens: &'a [Token],
    pos: usize,
    names: &'a HashMap<String, u32>,
}

impl<'a> Parser<'a> {
    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.pos)
    }

    fn next(&mut self) -> Option<&Token> {
        let t = self.tokens.get(self.pos);
        if t.is_some() {
            self.pos += 1;
        }
        t
    }

    fn parse_expr(&mut self, prec: u8, depth: usize) -> Result<(i64, bool), String> {
        if depth > 32 {
            return Err("expression nesting".into());
        }
        let mut left = self.parse_prefix(depth)?;

        while let Some(t) = self.peek() {
            let p = precedence(t);
            if p == 0 || p <= prec {
                break;
            }
            let op = self.next().unwrap().clone();
            let right = self.parse_expr(p, depth + 1)?;
            left = self.apply_binop(op, left, right)?;
        }
        Ok(left)
    }

    fn parse_prefix(&mut self, depth: usize) -> Result<(i64, bool), String> {
        if depth > 32 {
            return Err("expression nesting".into());
        }
        let t = self.next().ok_or("unexpected EOF")?.clone();
        match t {
            Token::Int(v, u) => Ok((v as i64, u)),
            Token::Name(n) => {
                if let Some(&Token::LParen) = self.peek() {
                    self.next();
                    let mut args = Vec::new();
                    if self.peek() != Some(&Token::RParen) {
                        loop {
                            args.push(self.parse_expr(0, depth + 1)?);
                            if self.peek() == Some(&Token::Comma) {
                                self.next();
                            } else {
                                break;
                            }
                        }
                    }
                    if self.next() != Some(&Token::RParen) {
                        return Err("expected )".into());
                    }
                    self.eval_call(&n, &args)
                } else {
                    if let Some(&val) = self.names.get(&n) {
                        Ok((val as i64, false))
                    } else if n == "BIT" || n == "BIT_ULL" || n == "GENMASK" || n == "GENMASK_ULL" {
                        Err("locally defined call".into())
                    } else {
                        Err(format!("unsupported name: {}", n))
                    }
                }
            }
            Token::Plus => {
                let v = self.parse_prefix(depth + 1)?;
                Ok(v)
            }
            Token::Minus => {
                let (v, u) = self.parse_prefix(depth + 1)?;
                let val = -v;
                if !(0..=0xffffffff).contains(&val) {
                    return Err("integer outside unsigned 32-bit range".into());
                }
                Ok((val, u))
            }
            Token::Tilde => {
                let (v, u) = self.parse_prefix(depth + 1)?;
                let val = !v;
                if !(0..=0xffffffff).contains(&val) {
                    return Err("integer outside unsigned 32-bit range".into());
                }
                Ok((val, u))
            }
            Token::LParen => {
                let v = self.parse_expr(0, depth + 1)?;
                if self.next() != Some(&Token::RParen) {
                    return Err("expected )".into());
                }
                Ok(v)
            }
            _ => Err(format!("unexpected prefix token: {:?}", t)),
        }
    }

    fn eval_call(&self, name: &str, args: &[(i64, bool)]) -> Result<(i64, bool), String> {
        if name == "BIT" || name == "BIT_ULL" {
            if args.len() == 1 {
                let v = args[0].0;
                if (0..=31).contains(&v) {
                    Ok(((1_i64 << v), true))
                } else {
                    Err("shift bound".into())
                }
            } else {
                Err("unsupported call".into())
            }
        } else if name == "GENMASK" || name == "GENMASK_ULL" {
            if args.len() == 2 {
                let high = args[0].0;
                let low = args[1].0;
                if low >= 0 && low <= high && high <= 31 {
                    Ok((((1_i64 << (high - low + 1)) - 1) << low, true))
                } else {
                    Err("shift bound".into())
                }
            } else {
                Err("unsupported call".into())
            }
        } else {
            Err("unsupported call".into())
        }
    }

    fn apply_binop(
        &self,
        op: Token,
        left: (i64, bool),
        right: (i64, bool),
    ) -> Result<(i64, bool), String> {
        let (lv, lu) = left;
        let (rv, ru) = right;
        let unsigned = match op {
            Token::Shl | Token::Shr => lu,
            _ => lu || ru,
        };

        if matches!(op, Token::Shl | Token::Shr) && !(0..=31).contains(&rv) {
            return Err("shift bound".into());
        }
        if matches!(op, Token::Slash | Token::Percent) && rv == 0 {
            return Err("division by zero".into());
        }

        let val = match op {
            Token::Plus => lv + rv,
            Token::Minus => lv - rv,
            Token::Star => lv * rv,
            Token::Slash => {
                if unsigned {
                    (lv as u32 / rv as u32) as i64
                } else {
                    lv.div_euclid(rv)
                }
            }
            Token::Percent => {
                if unsigned {
                    (lv as u32 % rv as u32) as i64
                } else {
                    lv.rem_euclid(rv)
                }
            }
            Token::Shl => lv << rv,
            Token::Shr => lv >> rv,
            Token::Amp => lv & rv,
            Token::Pipe => lv | rv,
            Token::Caret => lv ^ rv,
            _ => unreachable!(),
        };

        if matches!(op, Token::Plus | Token::Minus | Token::Star | Token::Shl)
            && !unsigned
            && val > 0x7fffffff
        {
            return Err("possible signed overflow".into());
        }

        if !(0..=0xffffffff).contains(&val) {
            return Err("integer outside unsigned 32-bit range".into());
        }

        Ok((val, unsigned))
    }
}

pub fn integer(expression: &str, names: &HashMap<String, u32>) -> Result<Option<u32>, String> {
    let source = expression.replace("\\\r\n", "").replace("\\\n", "");
    let source = strip_comments(&source);
    if source.len() > 4096 {
        return Err("expression length bound".into());
    }

    let tokens = tokenize(&source, names)?;

    if tokens.is_empty() {
        return Ok(None);
    }

    let mut parser = Parser {
        tokens: &tokens,
        pos: 0,
        names,
    };

    match parser.parse_expr(0, 0) {
        Ok((val, _)) => {
            if parser.pos != tokens.len() {
                Err("unparsed tokens".into())
            } else {
                Ok(Some(val as u32))
            }
        }
        Err(e) => Err(e),
    }
}

pub fn run_inventory_cmd(
    _cli: &Cli,
    _args: &InventoryArgs,
    _scratch: &ScratchResolver,
    _stdout: &mut dyn Write,
    _stderr: &mut dyn Write,
) -> i32 {
    0
}

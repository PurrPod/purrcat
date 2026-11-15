/* PurrCat GenUI —— DSL 词法、语法与求值核心 */
(function (g) {
  'use strict';
  var G = g.PurrCatGenUI = g.PurrCatGenUI || {};

  function ParseError(message, pos) { this.name = 'ParseError'; this.message = message; this.pos = pos || 0; }
  ParseError.prototype = Object.create(Error.prototype);

  var KEYWORDS = { true: true, false: false, null: null, undefined: undefined };

  function isIdentStart(ch) { return /[A-Za-z_]/.test(ch); }
  function isIdentPart(ch) { return /[A-Za-z0-9_]/.test(ch); }
  function isDigit(ch) { return ch >= '0' && ch <= '9'; }

  function tokenize(src) {
    var out = [], i = 0, n = src.length;
    while (i < n) {
      var ch = src[i];
      if (ch === '\n' || ch === '\r') {
        if (ch === '\r' && src[i + 1] === '\n') i++;
        out.push({ t: 'nl' }); i++; continue;
      }
      if (ch === ' ' || ch === '\t') { i++; continue; }
      if (ch === '/' && src[i + 1] === '/') {
        while (i < n && src[i] !== '\n') i++;
        continue;
      }
      if (ch === '"' || ch === "'") {
        var quote = ch, buf = '', start = i; i++;
        var closed = false;
        while (i < n) {
          ch = src[i];
          if (ch === quote) { closed = true; i++; break; }
          if (ch === '\\') {
            var esc = src[i + 1];
            if (esc === 'n') buf += '\n';
            else if (esc === 't') buf += '\t';
            else if (esc === 'r') buf += '\r';
            else if (esc === 'b') buf += '\b';
            else if (esc === 'f') buf += '\f';
            else if (esc === 'u') {
              var hex = src.slice(i + 2, i + 6);
              if (/^[0-9a-fA-F]{4}$/.test(hex)) { buf += String.fromCharCode(parseInt(hex, 16)); i += 4; }
              else buf += 'u';
            } else buf += esc == null ? '' : esc;
            i += 2; continue;
          }
          if (ch === '\n') break;
          buf += ch; i++;
        }
        if (!closed) throw new ParseError('字符串未闭合', start);
        out.push({ t: 'str', v: buf, pos: start });
        continue;
      }
      if (isDigit(ch) || (ch === '.' && isDigit(src[i + 1]))) {
        var s = i;
        while (i < n && /[0-9.eE+-]/.test(src[i])) {
          if ((src[i] === '+' || src[i] === '-') && !/[eE]/.test(src[i - 1])) break;
          i++;
        }
        var raw = src.slice(s, i);
        var num = Number(raw);
        if (!isFinite(num)) throw new ParseError('非法数字 ' + raw, s);
        out.push({ t: 'num', v: num, pos: s });
        continue;
      }
      if (ch === '$' || ch === '@') {
        var j = i + 1;
        if (!isIdentStart(src[j] || '')) throw new ParseError('非法标识符', i);
        while (j < n && isIdentPart(src[j])) j++;
        out.push({ t: ch === '$' ? 'var' : 'func', v: src.slice(i + 1, j), pos: i });
        i = j; continue;
      }
      if (isIdentStart(ch)) {
        var k = i;
        while (k < n && isIdentPart(src[k])) k++;
        out.push({ t: 'id', v: src.slice(i, k), pos: i });
        i = k; continue;
      }
      var three = src.slice(i, i + 3);
      var two = src.slice(i, i + 2);
      if (three === '...') { out.push({ t: 'op', v: '...' }); i += 3; continue; }
      if (two === '==' || two === '!=' || two === '>=' || two === '<=' || two === '&&' || two === '||') {
        out.push({ t: 'op', v: two }); i += 2; continue;
      }
      if ('+-*/%()[]{},:.?!=<>'.indexOf(ch) >= 0) { out.push({ t: 'op', v: ch }); i++; continue; }
      throw new ParseError('无法识别的字符 ' + ch, i);
    }
    out.push({ t: 'eof' });
    return out;
  }

  var BIN_PREC = { '||': 1, '&&': 2, '==': 3, '!=': 3, '>': 4, '<': 4, '>=': 4, '<=': 4, '+': 5, '-': 5, '*': 6, '/': 6, '%': 6 };

  function parse(src) {
    var tokens = tokenize(src);
    var defs = new Map();
    var stateDefs = new Map();
    var pos = 0;

    function peek(offset) { return tokens[pos + (offset || 0)]; }
    function next() { return tokens[pos++]; }
    function atOp(v) { var t = peek(); return t && t.t === 'op' && t.v === v; }
    function skipNl() { while (peek() && peek().t === 'nl') pos++; }
    function skipStatement() {
      while (peek() && peek().t !== 'eof') {
        var t = next();
        if (t.t === 'nl') return;
      }
    }

    function parseExpr(minPrec) {
      var left = parseUnary();
      for (;;) {
        var t = peek();
        if (!t || t.t !== 'op') break;
        if (t.v === '?') {
          if ((minPrec || 0) > 0) break;
          next();
          var yes = parseExpr(0);
          if (!atOp(':')) throw new ParseError('三元表达式缺少 :');
          next();
          var no = parseExpr(0);
          left = { n: 'cond', test: left, yes: yes, no: no };
          continue;
        }
        var prec = BIN_PREC[t.v];
        if (prec == null || prec < (minPrec || 0)) break;
        next();
        var right = parseExpr(prec + 1);
        left = { n: 'bin', op: t.v, left: left, right: right };
      }
      return left;
    }

    function parseUnary() {
      var t = peek();
      if (t && t.t === 'op' && (t.v === '!' || t.v === '-' || t.v === '+')) {
        next();
        return { n: 'unary', op: t.v, arg: parseUnary() };
      }
      return parsePostfix(parsePrimary());
    }

    function parsePostfix(node) {
      for (;;) {
        var t = peek();
        if (!t || t.t !== 'op') break;
        if (t.v === '(' && node.n === 'ref') {
          next();
          node = { n: 'call', name: node.name, args: parseArgs() };
          continue;
        }
        if (t.v === '.') {
          next();
          var id = next();
          if (!id || id.t !== 'id') throw new ParseError('成员访问缺少字段名');
          node = { n: 'member', obj: node, key: id.v };
          continue;
        }
        if (t.v === '[') {
          next();
          var idx = parseExpr(0);
          if (!atOp(']')) throw new ParseError('索引缺少 ]');
          next();
          node = { n: 'index', obj: node, index: idx };
          continue;
        }
        break;
      }
      return node;
    }

    function parseArgs() {
      var args = [];
      skipNl();
      if (atOp(')')) { next(); return args; }
      for (;;) {
        skipNl();
        if (atOp(')')) { next(); break; }
        args.push(parseExpr(0));
        skipNl();
        if (atOp(',')) { next(); continue; }
        if (atOp(')')) { next(); break; }
        throw new ParseError('参数列表缺少 , 或 )');
      }
      return args;
    }

    function parsePrimary() {
      var t = next();
      if (!t || t.t === 'eof') throw new ParseError('表达式不完整');
      if (t.t === 'num') return { n: 'num', v: t.v };
      if (t.t === 'str') return { n: 'str', v: t.v };
      if (t.t === 'var') return { n: 'var', name: t.v };
      if (t.t === 'func') {
        if (!atOp('(')) throw new ParseError('@' + t.v + ' 缺少参数');
        next();
        return { n: 'func', name: t.v, args: parseArgs() };
      }
      if (t.t === 'id') {
        if (t.v === 'true') return { n: 'bool', v: true };
        if (t.v === 'false') return { n: 'bool', v: false };
        if (t.v === 'null' || t.v === 'undefined') return { n: 'null' };
        return { n: 'ref', name: t.v };
      }
      if (t.t === 'op' && t.v === '(') {
        var inner = parseExpr(0);
        if (!atOp(')')) throw new ParseError('缺少 )');
        next();
        return inner;
      }
      if (t.t === 'op' && t.v === '[') {
        var items = [];
        for (;;) {
          skipNl();
          if (atOp(']')) { next(); break; }
          if (peek() && peek().t === 'eof') throw new ParseError('数组未闭合');
          items.push(parseExpr(0));
          skipNl();
          if (atOp(',')) { next(); continue; }
          if (atOp(']')) { next(); break; }
          throw new ParseError('数组缺少 , 或 ]');
        }
        return { n: 'arr', items: items };
      }
      if (t.t === 'op' && t.v === '{') {
        var pairs = [];
        for (;;) {
          skipNl();
          if (atOp('}')) { next(); break; }
          var kt = next();
          if (!kt) throw new ParseError('对象未闭合');
          var key = kt.t === 'str' ? kt.v : (kt.t === 'id' ? kt.v : (kt.t === 'num' ? String(kt.v) : null));
          if (key == null) throw new ParseError('对象键非法');
          if (!atOp(':')) throw new ParseError('对象键缺少 :');
          next();
          pairs.push({ key: key, value: parseExpr(0) });
          skipNl();
          if (atOp(',')) { next(); continue; }
          if (atOp('}')) { next(); break; }
          throw new ParseError('对象缺少 , 或 }');
        }
        return { n: 'obj', pairs: pairs };
      }
      throw new ParseError('无法解析的表达式');
    }

    while (peek() && peek().t !== 'eof') {
      if (peek().t === 'nl') { pos++; continue; }
      var start = pos;
      try {
        var t = next();
        var name, isState = false;
        if (t.t === 'var') { name = t.v; isState = true; }
        else if (t.t === 'id') name = t.v;
        else { skipStatement(); continue; }
        if (!atOp('=')) throw new ParseError('语句缺少 =');
        next();
        var expr = parseExpr(0);
        if (peek() && peek().t !== 'nl' && peek().t !== 'eof') throw new ParseError('语句末尾有多余内容');
        if (isState) stateDefs.set(name, expr);
        else defs.set(name, expr);
      } catch (err) {
        pos = start;
        skipStatement();
      }
    }

    return { defs: defs, stateDefs: stateDefs, source: src };
  }

  function Binding(name, state) { this.name = name; this.state = state; }
  Object.defineProperty(Binding.prototype, 'value', {
    get: function () { return this.state ? this.state[this.name] : undefined; }
  });
  Binding.prototype.set = function (v) {
    if (this.state) { this.state[this.name] = v; return true; }
    return false;
  };

  function isNode(v) { return !!(v && typeof v === 'object' && v.__node === true); }

  function formatValue(v) {
    if (v == null) return '';
    if (v instanceof Binding) return formatValue(v.value);
    if (typeof v === 'string') return v;
    if (typeof v === 'number') return String(v);
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    if (Array.isArray(v)) return v.map(formatValue).join(', ');
    try { return JSON.stringify(v); } catch (e) { return String(v); }
  }

  function plain(v) {
    if (v instanceof Binding) return plain(v.value);
    if (Array.isArray(v)) return v.map(plain);
    if (v && typeof v === 'object' && !isNode(v)) {
      if (v.__step || v.__action) return v;
      var out = {};
      Object.keys(v).forEach(function (k) { out[k] = plain(v[k]); });
      return out;
    }
    return v;
  }

  function same(a, b) {
    if (a === b) return true;
    if ((typeof a === 'number' && typeof b === 'string') || (typeof a === 'string' && typeof b === 'number')) return String(a) === String(b);
    if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every(function (x, i) { return same(x, b[i]); });
    if (a && b && typeof a === 'object' && typeof b === 'object') {
      var ak = Object.keys(a), bk = Object.keys(b);
      return ak.length === bk.length && ak.every(function (k) { return Object.prototype.hasOwnProperty.call(b, k) && same(a[k], b[k]); });
    }
    return false;
  }

  function createEvaluator(doc, state, options) {
    options = options || {};
    var functions = options.functions || {};
    var components = options.components || {};
    var memo = new Map();
    var resolving = new Set();
    var locals = [];

    function lookupLocal(name) {
      for (var i = locals.length - 1; i >= 0; i--) {
        if (Object.prototype.hasOwnProperty.call(locals[i], name)) return { hit: true, value: locals[i][name] };
      }
      return { hit: false };
    }

    function evalRef(name) {
      var local = lookupLocal(name);
      if (local.hit) return local.value;
      if (memo.has(name)) return memo.get(name);
      if (!doc.defs.has(name)) return undefined;
      if (resolving.has(name)) return undefined;
      resolving.add(name);
      var value;
      try { value = evalExpr(doc.defs.get(name)); }
      finally { resolving.delete(name); }
      memo.set(name, value);
      return value;
    }

    function evalArgs(args) {
      return args.map(evalExpr);
    }

    function evalFunc(node) {
      var name = node.name;
      if (name === 'Each') {
        var list = plain(evalExpr(node.args[0] || { n: 'null' }));
        var varName = formatValue(evalExpr(node.args[1] || { n: 'null' }));
        var template = node.args[2];
        if (!Array.isArray(list) || !varName || !template) return [];
        return list.map(function (item) {
          var scope = {};
          scope[varName] = item;
          locals.push(scope);
          try { return evalExpr(template); }
          finally { locals.pop(); }
        });
      }
      var fn = functions[name];
      if (typeof fn !== 'function') return undefined;
      var keepBinding = name === 'Set' || name === 'Reset';
      var values = evalArgs(node.args).map(function (v) {
        if (keepBinding && v instanceof Binding) return v;
        return plain(v);
      });
      try { return fn.apply(null, values); }
      catch (e) { return undefined; }
    }

    function evalExpr(node) {
      if (!node) return undefined;
      switch (node.n) {
        case 'num': case 'str': case 'bool': return node.v;
        case 'null': return null;
        case 'ref': return evalRef(node.name);
        case 'var': return new Binding(node.name, state);
        case 'arr': return node.items.map(evalExpr);
        case 'obj': {
          var obj = {};
          node.pairs.forEach(function (p) { obj[p.key] = evalExpr(p.value); });
          return obj;
        }
        case 'unary': {
          var uv = plain(evalExpr(node.arg));
          if (node.op === '!') return !uv;
          if (node.op === '-') return -Number(uv);
          return Number(uv);
        }
        case 'bin': {
          var a = plain(evalExpr(node.left));
          var b = plain(evalExpr(node.right));
          switch (node.op) {
            case '+':
              if (typeof a === 'string' || typeof b === 'string') return formatValue(a) + formatValue(b);
              return Number(a) + Number(b);
            case '-': return Number(a) - Number(b);
            case '*': return Number(a) * Number(b);
            case '/': return Number(b) === 0 ? null : Number(a) / Number(b);
            case '%': return Number(b) === 0 ? null : Number(a) % Number(b);
            case '==': return same(a, b);
            case '!=': return !same(a, b);
            case '>': return a > b;
            case '<': return a < b;
            case '>=': return a >= b;
            case '<=': return a <= b;
            case '&&': return !!a && !!b;
            case '||': return !!a || !!b;
            default: return null;
          }
        }
        case 'cond': return plain(evalExpr(node.test)) ? evalExpr(node.yes) : evalExpr(node.no);
        case 'member': {
          var objv = plain(evalExpr(node.obj));
          if (Array.isArray(objv)) return objv.map(function (item) { return item == null ? undefined : item[node.key]; });
          if (objv && typeof objv === 'object') return objv[node.key];
          return undefined;
        }
        case 'index': {
          var target = plain(evalExpr(node.obj));
          var idx = plain(evalExpr(node.index));
          if (typeof target === 'string') return target[Number(idx)];
          if (Array.isArray(target)) return target[Number(idx)];
          if (target && typeof target === 'object') return target[idx];
          return undefined;
        }
        case 'func': return evalFunc(node);
        case 'call': {
          if (node.name === 'Action') {
            var steps = plain(evalExpr(node.args[0] || { n: 'arr', items: [] }));
            return { __action: Array.isArray(steps) ? steps : [steps] };
          }
          if (!Object.prototype.hasOwnProperty.call(components, node.name) && !options.allowUnknown) {
            return { __node: true, type: node.name, args: [], unknown: true };
          }
          return { __node: true, type: node.name, args: evalArgs(node.args) };
        }
        default: return undefined;
      }
    }

    function initState() {
      doc.stateDefs.forEach(function (expr, name) {
        if (!(name in state)) {
          var v = evalExpr(expr);
          state[name] = v instanceof Binding ? v.value : plain(v);
        }
      });
    }

    return { evalRef: evalRef, evalExpr: evalExpr, initState: initState, memo: memo };
  }

  function evaluate(doc, state, options) {
    var evaluator = createEvaluator(doc, state || {}, options);
    evaluator.initState();
    var root = evaluator.evalRef('root');
    return { root: root, state: state, evaluator: evaluator };
  }

  G.ParseError = ParseError;
  G.tokenize = tokenize;
  G.parse = parse;
  G.evaluate = evaluate;
  G.createEvaluator = createEvaluator;
  G.Binding = Binding;
  G.isNode = isNode;
  G.plain = plain;
  G.same = same;
  G.formatValue = formatValue;
})(typeof globalThis !== 'undefined' ? globalThis : this);
